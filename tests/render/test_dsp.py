"""Synthetic-signal verification of filters, automation, and mastering."""

import numpy as np
import pytest

from mil4dy.render.filters import lr4_split, svf_sweep, tempo_delay
from mil4dy.render.master import limit, master_chain, measure_lufs, true_peak_db
from mil4dy.schemas import AutomationLane, PlanTransition, TempoRamp
from mil4dy.render.automation import apply_deck_automation

from .synth import SR, tone


def goertzel_db(x: np.ndarray, freq: float, sr: int = SR) -> float:
    """Power of one frequency bin, dBFS-ish."""
    mono = x.mean(axis=1) if x.ndim == 2 else x
    n = len(mono)
    t = np.arange(n) / sr
    c = mono @ np.exp(-2j * np.pi * freq * t)
    return 20 * np.log10(max(abs(c) * 2 / n, 1e-12))


def test_lr4_crossover_flat_resum():
    rng = np.random.default_rng(1)
    noise = rng.standard_normal((SR * 2, 2)).astype(np.float32) * 0.1
    low, high = lr4_split(noise)
    resum = low + high
    # Compare magnitude spectra over 40 Hz - 15 kHz
    f_in = np.abs(np.fft.rfft(noise[:, 0]))
    f_out = np.abs(np.fft.rfft(resum[:, 0]))
    freqs = np.fft.rfftfreq(len(noise), 1 / SR)
    band = (freqs > 40) & (freqs < 15000)
    # Smooth in octave-ish chunks to compare responses, not bin noise
    ratio_db = 20 * np.log10(f_out[band] / np.maximum(f_in[band], 1e-12))
    chunks = np.array_split(ratio_db, 50)
    means = np.array([c.mean() for c in chunks])
    assert np.abs(means).max() < 0.5, f"crossover resum not flat: {np.abs(means).max():.2f} dB"


def test_bass_swap_automation():
    # Incoming deck: 55 Hz + 1 kHz. low_gain_db opens at swap beat 16 of 32.
    bpm = 128.0
    spb = 60.0 / bpm
    length = 32
    n = int(length * spb * SR)
    audio = tone([55.0, 1000.0], length * spb)
    tr = PlanTransition(
        from_id="a", to_id="b", type="long_blend_bass_swap", length_beats=length,
        out_start_beat=0, in_start_beat=0, swap_beat=16.0,
        tempo_ramp=TempoRamp(from_bpm=bpm, to_bpm=bpm),
        automation=[
            AutomationLane(target="in.low_gain_db",
                           points=[(0.0, -80.0), (15.5, -80.0), (16.5, 0.0)]),
        ],
    )
    beat_pos = np.arange(n) / (spb * SR)
    buf = audio.copy()
    apply_deck_automation(buf, 0, n, beat_pos, tr, "in")

    def window(b0, b1):
        return buf[int(b0 * spb * SR) : int(b1 * spb * SR)]

    before_55 = goertzel_db(window(4, 14), 55.0)
    after_55 = goertzel_db(window(18, 30), 55.0)
    ref_55 = goertzel_db(audio[int(18 * spb * SR) : int(30 * spb * SR)], 55.0)
    before_1k = goertzel_db(window(4, 14), 1000.0)
    ref_1k = goertzel_db(audio[int(4 * spb * SR) : int(14 * spb * SR)], 1000.0)

    # LR4 highpass leakage bounds the kill at ~27 dB @ 55 Hz — same ballpark as
    # a hardware DJ mixer's low kill (~-26 dB), so that's the assertion target.
    assert before_55 < ref_55 - 25, f"bass not suppressed before swap: {before_55:.1f} vs {ref_55:.1f}"
    assert abs(after_55 - ref_55) < 1.0, f"bass not restored after swap: {after_55:.1f} vs {ref_55:.1f}"
    assert abs(before_1k - ref_1k) < 1.5, f"highs damaged before swap: {before_1k:.1f} vs {ref_1k:.1f}"


def test_lpf_sweep_attenuates():
    audio = tone([8000.0], 4.0)
    n = len(audio)
    tr = PlanTransition(
        from_id="a", to_id="b", type="filter_sweep", length_beats=8,
        out_start_beat=0, in_start_beat=0,
        tempo_ramp=TempoRamp(from_bpm=120, to_bpm=120),
        automation=[AutomationLane(target="out.lpf_hz",
                                   points=[(0.0, 18000.0), (8.0, 150.0)])],
    )
    beat_pos = np.linspace(0, 8, n, endpoint=False)
    buf = audio.copy()
    apply_deck_automation(buf, 0, n, beat_pos, tr, "out")
    early = goertzel_db(buf[: n // 8], 8000.0)
    late = goertzel_db(buf[-n // 8 :], 8000.0)
    assert early - late > 20, f"sweep attenuation only {early - late:.1f} dB"


def test_master_chain_targets():
    rng = np.random.default_rng(2)
    # Pink-ish program material at a hot level
    noise = rng.standard_normal((SR * 12, 2)).astype(np.float32)
    from scipy import signal as sp

    b, a = sp.butter(1, 2000, fs=SR)
    audio = sp.lfilter(b, a, noise, axis=0).astype(np.float32) * 0.5
    mastered, report = master_chain(audio, target_lufs=-10.0)
    assert abs(report["final_lufs"] - (-10.0)) < 1.0, report
    assert report["final_true_peak_dbtp"] <= -0.8, report


def test_limiter_ceiling():
    t = np.arange(SR * 2) / SR
    y = (np.sin(2 * np.pi * 300 * t) * 1.8).astype(np.float32)
    audio = np.stack([y, y], axis=1)
    out = limit(audio, ceiling_db=-1.0)
    assert true_peak_db(out) <= -0.8


def test_limiter_ceiling_first_lookahead_window():
    # Regression (M4D-6): the sliding-min window was never seeded, so peaks in
    # the first `lookahead` samples (~5 ms) escaped the limiter entirely.
    audio = np.zeros((SR, 2), dtype=np.float32)
    audio[100:110, :] = 2.0
    audio[SR // 2 : SR // 2 + 10, :] = 2.0
    out = limit(audio, ceiling_db=-1.0)
    early = true_peak_db(out[: SR // 4])
    late = true_peak_db(out[SR // 4 :])
    assert early <= -0.8, f"peak in first lookahead window escaped: {early:.2f} dBTP"
    assert late <= -0.8, f"late peak escaped: {late:.2f} dBTP"


def test_tempo_delay_decays():
    audio = tone([440.0], 0.2, amp=0.8)
    tail = tempo_delay(audio, delay_samples=int(0.2 * SR))
    peaks = [np.abs(tail[int(i * 0.2 * SR) : int((i + 1) * 0.2 * SR)]).max() for i in range(1, 5)]
    assert all(peaks[i] > peaks[i + 1] for i in range(len(peaks) - 1)), peaks
