"""Musical-time grid checks. Indexes on beat_times are not bars."""

from __future__ import annotations

import numpy as np

GRID_TOL = 0.12


def expected_span_s(bpm: float, n_beats: int) -> float:
    """Duration of `n_beats` pulses at `bpm`."""
    if bpm <= 0 or n_beats <= 0:
        return 0.0
    return n_beats * 60.0 / bpm


def window_span_s(beats: np.ndarray | list[float], start_i: int, n_beats: int) -> float:
    """Elapsed time from `beats[start_i]` across `n_beats` steps.

    `n_beats` is a step count (like `length_beats`), so the end index is
    `start_i + n_beats`. Short/clipped windows return whatever span exists.
    """
    arr = np.asarray(beats, dtype=float)
    if len(arr) < 2 or n_beats <= 0:
        return 0.0
    i0 = int(np.clip(start_i, 0, len(arr) - 1))
    i1 = int(np.clip(i0 + n_beats, 0, len(arr) - 1))
    if i1 <= i0:
        return 0.0
    return float(arr[i1] - arr[i0])


def grid_ok(span_s: float, bpm: float, n_beats: int, *, tol: float = GRID_TOL) -> bool:
    """True when a window's elapsed time matches `n_beats` at `bpm`."""
    exp = expected_span_s(bpm, n_beats)
    if exp <= 0 or span_s <= 0:
        return False
    return abs(span_s - exp) / exp <= tol


def local_bpm(beat_times: np.ndarray | list[float], t0: float | None = None,
              t1: float | None = None) -> float:
    """Count-based local tempo: (n-1) * 60 / span. Not a median.

    Kick-light intros with extra ticks read faster than `robust_bpm` (middle
    80% pulse fit), which is the point — Walk with me's intro is ~163 here and
    125 from the body pulse.
    """
    arr = np.asarray(beat_times, dtype=float)
    if t0 is not None:
        arr = arr[arr >= t0]
    if t1 is not None:
        arr = arr[arr <= t1]
    if len(arr) < 2:
        return 0.0
    span = float(arr[-1] - arr[0])
    if span <= 1e-9:
        return 0.0
    return float((len(arr) - 1) * 60.0 / span)


def beat_count_error(n_beats: int, duration: float, bpm: float) -> float:
    """|detected - expected| / expected for a whole-track (or span) count."""
    expected = duration * bpm / 60.0 if bpm > 0 and duration > 0 else 0.0
    if expected <= 0:
        return 1.0
    return abs(n_beats - expected) / expected


def beat_count_ok(n_beats: int, duration: float, bpm: float, *, tol: float = 0.04
                  ) -> bool:
    return beat_count_error(n_beats, duration, bpm) <= tol
