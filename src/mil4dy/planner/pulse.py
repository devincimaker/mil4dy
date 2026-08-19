"""Lock a mix-window beat grid to the local pulse.

`grid_ok` only asks whether N indexes span the right duration. A perfectly
regular 125 grid that sits on the off-beat still passes — then the renderer
pins those timestamps to the output clock and the real kicks land between
beats. Two decks with different kick phases become a flam.

This module measures onset phase against the detector grid and shifts the
grid so the strongest hit in the window sits on a beat. No track names, no
crate-specific BPM. Same path for every pair.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.signal import lfilter

# Half a 125-BPM beat is 240ms. Shifts smaller than this are still audible
# as a late kick; we apply anything we can measure once the peak is clear.
_MIN_SEP_S = 0.34
# peak-bin / mean-bin. Uniform onsets ≈ 1. A single cluster ≈ n_bins.
_PEAK_RATIO = 2.5
_BINS = 24
# Don't guess a 180° flip from a handful of clicks.
_MIN_ONSETS = 6
# Announce only musically large slips. ~60ms is tracker jitter / kick bloom
# (1/8 beat at 125). A 16th is 120ms; warn from 100ms.
_WARN_SHIFT_S = 0.100
# 2-bar chunks. A 16-bar histogram can vote phase 0 from a tight opening
# while the rest of the overlap is +120–200 ms late.
_CHUNK_BEATS = 8
_MIXED_SHIFT_S = 0.050


@dataclass(frozen=True)
class PulseLock:
    shift_s: float
    phase: float
    peak_ratio: float
    n_onsets: int
    applied: bool
    mixed: bool = False

    @property
    def warning(self) -> str | None:
        if self.mixed:
            if self.applied:
                return "kick slips mid-window — locked to the later pulse"
            return "kick slips mid-window"
        if not self.applied or abs(self.shift_s) < _WARN_SHIFT_S:
            return None
        ms = abs(self.shift_s) * 1000.0
        return f"grid was {ms:.0f}ms off the kick — locked the pulse"


def shortest_phase_shift(phase: float, period: float) -> float:
    """Map onset-phase in [0, 1) to a signed shift in seconds.

    Phase 0 = already on the beat. Phase 0.5 = half a beat late. Values
    past 0.5 wrap backward so we never jump more than half a period.
    """
    ph = float(phase) % 1.0
    delta = ph * period
    if delta > period * 0.5:
        delta -= period
    return delta


def beat_phase_peak(beats: np.ndarray | list[float],
                    onsets: np.ndarray | list[float],
                    t0: float, t1: float, *,
                    bins: int = _BINS) -> tuple[float, float]:
    """Strongest onset cluster vs the grid.

    Returns (phase, peak_ratio). Phase is 0 when onsets sit on beats, 0.5
    when they sit on the off-beat. `peak_ratio` is peak-bin / mean-bin;
    uniform onsets sit near 1, a single cluster near `bins`.
    """
    b = np.asarray(beats, dtype=float)
    o = np.asarray(onsets, dtype=float)
    o = o[(o >= t0 - 0.05) & (o <= t1 + 0.05)]
    if len(b) < 2 or len(o) < 2 or bins < 4:
        return 0.0, 0.0
    hist = np.zeros(bins, dtype=float)
    for t in o:
        j = int(np.searchsorted(b, t) - 1)
        if j < 0 or j >= len(b) - 1:
            continue
        span = b[j + 1] - b[j]
        if span <= 1e-6:
            continue
        ph = (t - b[j]) / span
        hist[int(ph * bins) % bins] += 1.0
    if hist.sum() <= 0:
        return 0.0, 0.0
    peak = int(np.argmax(hist))
    mean = float(hist.mean())
    ratio = float(hist[peak] / mean) if mean > 1e-9 else 0.0
    return peak / bins, ratio


def shift_beats(beats: np.ndarray | list[float], delta_s: float) -> np.ndarray:
    arr = np.asarray(beats, dtype=float)
    if abs(delta_s) < 1e-9:
        return arr.copy()
    return arr + float(delta_s)


def _chunk_shifts(beats: np.ndarray, onsets: np.ndarray,
                  t0: float, t1: float, period: float) -> list[float]:
    """Per-chunk shortest phase shifts. Skips sparse or smeared slices."""
    chunk_s = _CHUNK_BEATS * period
    if chunk_s <= 1e-6 or t1 <= t0:
        return []
    shifts: list[float] = []
    t = float(t0)
    while t < t1 - period:
        te = min(t + chunk_s, t1)
        n = int(np.sum((onsets >= t - 0.05) & (onsets <= te + 0.05)))
        if n >= _MIN_ONSETS:
            ph, ratio = beat_phase_peak(beats, onsets, t, te)
            if ratio >= _PEAK_RATIO:
                shifts.append(shortest_phase_shift(ph, period))
        t += chunk_s
    return shifts


def lock_beats_to_onsets(beats: np.ndarray | list[float],
                         onsets: np.ndarray | list[float],
                         t0: float, t1: float,
                         bpm: float) -> tuple[np.ndarray, PulseLock]:
    """Shift `beats` so the window's kick lands on a beat.

    One histogram over 16 bars can vote phase 0 from a tight opening while
    later kicks sit +120–200 ms late. Chunk the overlap; if phases disagree,
    follow the later pulse and warn instead of keeping the opening vote.
    """
    arr = np.asarray(beats, dtype=float)
    o = np.asarray(onsets, dtype=float)
    if len(arr) < 2 or len(o) < _MIN_ONSETS:
        return arr.copy(), PulseLock(0.0, 0.0, 0.0, int(len(o)), False)

    period = 60.0 / bpm if bpm > 0 else float(np.median(np.diff(arr)))
    if period <= 1e-6:
        return arr.copy(), PulseLock(0.0, 0.0, 0.0, int(len(o)), False)

    n = int(np.sum((o >= t0 - 0.05) & (o <= t1 + 0.05)))
    chunks = _chunk_shifts(arr, o, t0, t1, period)
    if len(chunks) >= 2:
        spread = float(np.max(chunks) - np.min(chunks))
        if spread > _MIXED_SHIFT_S:
            delta = float(np.median(chunks))
            phase = (delta / period) % 1.0
            applied = abs(delta) >= 0.008
            lock = PulseLock(delta, phase, 0.0, n, applied, mixed=True)
            return shift_beats(arr, delta), lock

    phase, ratio = beat_phase_peak(arr, o, t0, t1)
    if ratio < _PEAK_RATIO or n < _MIN_ONSETS:
        return arr.copy(), PulseLock(0.0, phase, ratio, n, False)

    delta = shortest_phase_shift(phase, period)
    locked = PulseLock(delta, phase, ratio, n, abs(delta) >= 0.008)
    return shift_beats(arr, delta), locked


def _one_pole(x: np.ndarray, sr: float, hz: float) -> np.ndarray:
    rc = 1.0 / (2.0 * np.pi * hz)
    dt = 1.0 / sr
    a = dt / (rc + dt)
    return lfilter([a], [1.0, a - 1.0], x)


def flux_onsets(y: np.ndarray, sr: float, *,
                t0: float = 0.0, min_sep: float = _MIN_SEP_S) -> np.ndarray:
    """Peak-pick a low-passed flux. One hit per beat-ish, not every hat."""
    if y.ndim > 1:
        y = y.mean(axis=-1)
    y = np.asarray(y, dtype=float)
    if len(y) < int(sr * 0.05):
        return np.zeros(0)

    lp120 = _one_pole(y, sr, 120.0)
    lp35 = _one_pole(y, sr, 35.0)
    band = lp120 - lp35
    env = _one_pole(np.abs(band), sr, 45.0)
    # Prefer bass; if the band is quiet (click tracks, thin outros) use full-band.
    if float(np.sqrt(np.mean(band ** 2))) < 1e-4:
        env = _one_pole(np.abs(y), sr, 45.0)

    hop = max(int(sr * 0.005), 1)
    flux = np.maximum(np.diff(env[::hop]), 0.0)
    if len(flux) < 8:
        return np.zeros(0)
    med = float(np.median(flux))
    mad = float(np.median(np.abs(flux - med))) + 1e-12
    thr = med + 4.0 * mad
    times = t0 + (np.arange(1, len(flux) + 1) * hop) / sr

    peaks: list[float] = []
    last = -1e9
    for i in range(1, len(flux) - 1):
        if flux[i] < thr or flux[i] < flux[i - 1] or flux[i] < flux[i + 1]:
            continue
        t = float(times[i])
        if t - last < min_sep:
            if peaks and flux[i] > flux[max(1, int((last - t0) * sr / hop) - 1)]:
                peaks[-1] = t
                last = t
            continue
        peaks.append(t)
        last = t
    return np.asarray(peaks, dtype=float)


def onsets_from_path(path: Path, t0: float, t1: float) -> np.ndarray:
    """Onsets in `[t0, t1]` from a file. Empty if the path is missing."""
    import soundfile as sf

    if not path.is_file() or t1 <= t0:
        return np.zeros(0)
    info = sf.info(path)
    sr = float(info.samplerate)
    pad = 0.25
    start = max(0, int((t0 - pad) * sr))
    stop = min(int(info.frames), int((t1 + pad) * sr))
    if stop - start < sr * 0.05:
        return np.zeros(0)
    audio, _ = sf.read(path, start=start, stop=stop, always_2d=True)
    return flux_onsets(audio.mean(axis=1), sr, t0=start / sr)


def onsets_for_track(path: str, t0: float, t1: float) -> np.ndarray | None:
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return onsets_from_path(p, t0, t1)
    except Exception:
        return None


def pulse_warning_line(side: str, lock: PulseLock) -> str | None:
    w = lock.warning
    if w is None:
        return None
    return f"{side} {w}"
