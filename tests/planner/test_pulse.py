"""Pulse lock: mix windows follow the kick, not a phase-slipped detector grid."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from mil4dy.planner.pair import plan_pair
from mil4dy.planner.pulse import (
    beat_phase_peak,
    flux_onsets,
    lock_beats_to_onsets,
    shift_beats,
    shortest_phase_shift,
)
from mil4dy.schemas import TrackAnalysis
from tests.planner.test_pair import _track
from tests.render.synth import SR, click_track, detect_clicks


def test_shortest_phase_wraps_past_half_a_beat():
    period = 0.48
    assert abs(shortest_phase_shift(0.0, period)) < 1e-9
    assert abs(shortest_phase_shift(0.5, period) - 0.24) < 1e-9
    # 50ms before the next beat is a small backward nudge, not +430ms.
    assert abs(shortest_phase_shift(0.95, period) + 0.024) < 1e-9


def test_on_grid_onsets_do_not_move_the_grid():
    bpm = 125.0
    period = 60.0 / bpm
    beats = np.arange(0.0, 32.0) * period
    onsets = beats + 0.004
    locked, info = lock_beats_to_onsets(beats, onsets, 0.0, 15.0, bpm)
    assert not info.applied or abs(info.shift_s) < 0.02
    assert np.allclose(locked, beats, atol=0.02)


def test_offbeat_onsets_shift_the_grid_onto_the_kick():
    bpm = 125.0
    period = 60.0 / bpm
    beats = np.arange(0.0, 65.0) * period
    onsets = beats + 0.24
    locked, info = lock_beats_to_onsets(beats, onsets, 0.0, 30.72, bpm)
    assert info.applied
    assert abs(info.shift_s - 0.24) < 0.03
    # After the shift, every onset sits on a beat.
    phase, ratio = beat_phase_peak(locked, onsets, 0.0, 30.72)
    assert phase < 0.08 or phase > 0.92
    assert ratio >= 1.25
    assert abs(locked[0] - beats[0] - 0.24) < 0.03


def test_late_kick_80ms_is_pulled_onto_the_beat():
    bpm = 125.0
    period = 60.0 / bpm
    beats = np.arange(0.0, 65.0) * period
    onsets = beats + 0.08
    locked, info = lock_beats_to_onsets(beats, onsets, 0.0, 30.72, bpm)
    assert info.applied
    assert 0.05 < info.shift_s < 0.11
    assert np.allclose(locked, shift_beats(beats, info.shift_s))
    # Jitter this small stays silent; 240ms still banners.
    assert info.warning is None


def test_half_beat_slip_still_warns():
    bpm = 125.0
    period = 60.0 / bpm
    beats = np.arange(0.0, 65.0) * period
    onsets = beats + 0.24
    _, info = lock_beats_to_onsets(beats, onsets, 0.0, 30.72, bpm)
    assert info.applied
    assert info.warning
    assert "240ms" in info.warning


def test_sparse_onsets_do_not_guess():
    bpm = 125.0
    beats = np.arange(0.0, 65.0) * (60.0 / bpm)
    onsets = np.array([0.24, 5.0, 12.0])
    locked, info = lock_beats_to_onsets(beats, onsets, 0.0, 30.72, bpm)
    assert not info.applied
    assert np.allclose(locked, beats)


def test_plan_pair_rephases_a_slipped_click_grid(tmp_path: Path):
    """Outgoing clicks sit 240ms after the stored grid. After plan_pair the
    embedded beat_times must have moved onto those clicks so the renderer
    would pin kick-to-kick, not grid-to-grid."""
    bpm = 125.0
    duration = 180.0
    n = int(duration * bpm / 60.0)
    audio, click_samples = click_track(bpm, n, click_hz=80.0)
    wav = tmp_path / "slipped.wav"
    sf.write(wav, audio, SR)

    rec = _track(
        "slipped",
        bpm=bpm,
        duration=duration,
        segments=[
            ("intro", 0.0, 16.0, 0.1),
            ("drop", 16.0, duration - 45.0, 0.2),
            ("outro", duration - 45.0, duration, 0.15),
        ],
    )
    # Detector grid is a half-beat late relative to the actual clicks.
    rec = TrackAnalysis.model_validate(
        rec.model_dump()
        | {
            "path": str(wav),
            "beat_times": [round(t + 0.24, 5) for t in rec.beat_times],
            "downbeat_times": [round(t + 0.24, 5) for t in rec.downbeat_times],
        }
    )
    partner = _track("partner", bpm=bpm, camelot=rec.camelot)
    partner = TrackAnalysis.model_validate(partner.model_dump() | {"path": str(wav)})

    # partner first so `rec` is incoming (intro/drop window has the clicks).
    _, _ = plan_pair(partner, rec)
    plan, decision = plan_pair(rec, partner)

    out_beats = np.asarray(plan.tracks[0].beat_times)
    # Clicks in the outgoing slice should now sit on the plan grid, not 240ms off.
    click_s = click_samples / SR
    # Use the overlap window.
    t0, t1 = decision.out_start_s, decision.out_end_s
    sl = click_s[(click_s >= t0) & (click_s <= t1)]
    if len(sl) < 8:
        sl = click_s[(click_s >= plan.tracks[0].cue_in_s) & (click_s <= plan.tracks[0].cue_out_s)]
    assert len(sl) >= 8
    phase, ratio = beat_phase_peak(out_beats, sl, t0, t1)
    assert ratio >= 1.2
    assert phase < 0.12 or phase > 0.88
    if decision.pulse_warning:
        assert "pulse" in decision.pulse_warning or "kick" in decision.pulse_warning


def test_mixed_window_does_not_keep_opening_phase():
    """On-grid for 3 bars, then +180 ms late: must not keep phase 0."""
    bpm = 125.0
    period = 60.0 / bpm
    beats = np.arange(0.0, 65.0) * period
    onsets = beats.copy()
    late = beats >= 12 * period
    onsets[late] = beats[late] + 0.180
    locked, info = lock_beats_to_onsets(beats, onsets, 0.0, 30.72, bpm)
    assert info.warning or abs(info.shift_s) > 0.05
    assert abs(info.shift_s) > 0.05
    # Followed the late majority, not the opening 3 bars.
    assert abs(info.shift_s - 0.180) < 0.05
    assert not np.allclose(locked, beats)


def test_smeared_late_kicks_do_not_keep_opening_phase():
    """Tight opening at phase 0, then +120–200 ms smear — the real g1rl5 shape."""
    bpm = 125.0
    period = 60.0 / bpm
    beats = np.arange(0.0, 65.0) * period
    onsets = beats.copy()
    for i, t in enumerate(beats):
        if t < 12 * period:
            continue
        frac = (t - 12 * period) / (64 * period - 12 * period)
        onsets[i] = t + 0.120 + 0.080 * frac
    locked, info = lock_beats_to_onsets(beats, onsets, 0.0, 30.72, bpm)
    assert info.warning or abs(info.shift_s) > 0.05
    assert abs(info.shift_s) > 0.05
    assert not np.allclose(locked, beats)


def test_flux_onsets_finds_kick_clicks():
    audio, samples = click_track(125.0, 32, click_hz=70.0)
    onsets = flux_onsets(audio.mean(axis=1), SR, t0=0.0)
    clicks = samples / SR
    assert len(onsets) >= 16
    errs = [abs(onsets - c).min() for c in clicks[:20]]
    assert float(np.median(errs)) < 0.03
