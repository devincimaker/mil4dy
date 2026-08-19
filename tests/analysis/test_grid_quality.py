"""Grid-quality helpers — synthetic arrays only, no audio."""

from __future__ import annotations

import numpy as np

from mil4dy.analysis.beats import fit_pulse, regularize_beats, robust_bpm
from mil4dy.planner.grid import (
    beat_count_ok,
    expected_span_s,
    grid_ok,
    local_bpm,
    window_span_s,
)


def _regular(bpm: float, n: int, t0: float = 0.0) -> np.ndarray:
    return t0 + np.arange(n) * (60.0 / bpm)


def test_regular_125_window_is_ok():
    beats = _regular(125.0, 65)
    span = window_span_s(beats, 0, 64)
    assert abs(span - 30.72) < 1e-6
    assert abs(expected_span_s(125.0, 64) - 30.72) < 1e-6
    assert grid_ok(span, 125.0, 64)


def test_walk_with_me_shaped_intro_fails_grid_ok():
    # 64 intervals drawn from the observed intro set, mean ~0.37s → 23.6s.
    pattern = np.array([0.22, 0.36, 0.48, 0.72])
    rng = np.random.default_rng(7)
    iv = rng.choice(pattern, size=64)
    # Force the mean the ticket cites so the span is the canary 23.6s.
    iv = iv * (23.6 / iv.sum())
    beats = np.concatenate([[0.0], np.cumsum(iv)])
    span = window_span_s(beats, 0, 64)
    assert abs(span - 23.6) < 0.05
    assert abs(expected_span_s(125.0, 64) - 30.72) < 1e-6
    assert not grid_ok(span, 125.0, 64)


def test_whole_track_beat_count_rejects_extra_ticks():
    duration = 361.9
    bpm = 125.0
    expected = duration * bpm / 60.0
    assert abs(expected - 754) < 2
    assert beat_count_ok(754, duration, bpm)
    assert not beat_count_ok(787, duration, bpm)


def _snapped_grid(bpm: float, n: int, quantum: float = 0.02) -> np.ndarray:
    """True pulse at `bpm`, then snapped onto a 20 ms rail like beat_this."""
    times = np.arange(n, dtype=float) * (60.0 / bpm)
    return np.round(times / quantum) * quantum


def test_snapped_127_is_125_under_median_not_under_the_fit():
    beats = _snapped_grid(127.0, 405)
    n = len(beats)
    lo, hi = int(n * 0.1), max(int(n * 0.9), int(n * 0.1) + 2)
    median_bpm = 60.0 / float(np.median(np.diff(beats[lo:hi])))
    assert abs(median_bpm - 125.0) < 0.15
    assert abs(robust_bpm(beats) - 127.0) < 0.15
    assert fit_pulse(beats).rms < 0.015


def test_snapped_124_is_125_under_median_not_under_the_fit():
    beats = _snapped_grid(124.0, 501)
    n = len(beats)
    lo, hi = int(n * 0.1), max(int(n * 0.9), int(n * 0.1) + 2)
    median_bpm = 60.0 / float(np.median(np.diff(beats[lo:hi])))
    assert abs(median_bpm - 125.0) < 0.15
    assert abs(robust_bpm(beats) - 124.0) < 0.15
    assert fit_pulse(beats).rms < 0.015


def test_snapped_127_rebuilds_to_a_constant_period():
    beats = _snapped_grid(127.0, 405)
    duration = float(beats[-1] + 60.0 / 127.0)
    reg, *_ = regularize_beats(beats, beats[::4], duration)
    ibi = np.diff(reg)
    assert len(ibi) > 16
    assert float(np.max(ibi) - np.min(ibi)) < 1e-9
    bpm = robust_bpm(beats)
    assert grid_ok(window_span_s(reg, 0, 64), bpm, 64)


def test_robust_bpm_ignores_garbage_intro_but_local_bpm_does_not():
    bpm = 125.0
    period = 60.0 / bpm
    # ~90s of extra ticks, then a clean body long enough to dominate the middle 80%.
    intro = [0.0]
    t = 0.0
    pattern = [0.22, 0.36, 0.48, 0.72]
    i = 0
    while t < 90.0:
        t += pattern[i % len(pattern)]
        i += 1
        intro.append(t)
    body = [90.0 + k * period for k in range(1, 500)]
    beats = np.asarray(intro + body, dtype=float)
    assert abs(robust_bpm(beats) - 125.0) < 2.0
    intro_local = local_bpm(beats, 0.0, 90.0)
    assert intro_local > 0
    assert abs(intro_local - 125.0) > 8.0
