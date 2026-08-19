"""Regression: 16 bars is musical time, not 64 indexes on a broken grid."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from mil4dy.planner.grid import expected_span_s, grid_ok, window_span_s
from mil4dy.planner.pair import decide_pair
from mil4dy.schemas import Segment, TrackAnalysis
from tests.planner.test_pair import _track

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "walk_with_me_grid.json"
SPAN_125_64 = 64 * 60.0 / 125.0  # 30.72


def _outgoing_125(**kwargs) -> TrackAnalysis:
    """Outgoing 125, no outro (so the table stays at 16 bars, not 32).

    Duration stays at 6 minutes so MAX_BODY_S (300s) still leaves 64 beats
    of tail. A 304s body like the real Underground is too tight after snap.
    """
    kw = dict(
        bpm=125.0,
        duration=360.0,
        camelot="8A",
        segments=[
            ("drop", 0.0, 280.0, 0.15),
            ("verse", 280.0, 360.0, 0.2),
        ],
    )
    kw.update(kwargs)
    return _track("underground", **kw)


def _broken_intro_track() -> TrackAnalysis:
    """Perfect 125 body; intro ticks so that 64 indexes span ~23.6s."""
    bpm = 125.0
    duration = 360.0
    period = 60.0 / bpm
    intro_end = 91.0
    pattern = [0.22, 0.36, 0.48, 0.72]
    times = [0.0]
    t = 0.0
    i = 0
    while t < intro_end:
        t += pattern[i % len(pattern)]
        i += 1
        if t < intro_end:
            times.append(round(t, 5))
    # Scale the last 64 intro steps to the canary 23.6s if needed.
    if len(times) > 64:
        head, tail = times[:-64], times[-64:]
        span = tail[-1] - tail[0]
        if span > 0:
            scale = 23.6 / span
            origin = tail[0]
            tail = [origin + (x - origin) * scale for x in tail]
            # keep monotonic vs head
            if head and tail[0] < head[-1]:
                shift = head[-1] + 0.05 - tail[0]
                tail = [x + shift for x in tail]
        times = head + tail
        intro_end = times[-1]
    body = [round(intro_end + k * period, 5)
            for k in range(1, int((duration - intro_end) / period))]
    beats = times + body
    downs = beats[::4]
    return TrackAnalysis(
        path="/tmp/broken_intro.wav",
        fingerprint="broken_intro",
        title="broken intro",
        artist="Test",
        duration=duration,
        bpm=bpm,
        beat_times=beats,
        downbeat_times=downs,
        phrase_starts=downs[::8],
        key="A",
        scale="minor",
        camelot="8A",
        key_confidence=0.9,
        energy=0.6,
        segments=[
            Segment(label="intro", start=0.0, end=intro_end, confidence=0.8,
                    energy=0.4, bass_ratio=0.3, vocal_likelihood=0.1, lufs_short=-12.0),
            Segment(label="drop", start=intro_end, end=duration - 45.0, confidence=0.8,
                    energy=0.6, bass_ratio=0.4, vocal_likelihood=0.2, lufs_short=-12.0),
            Segment(label="outro", start=duration - 45.0, end=duration, confidence=0.8,
                    energy=0.4, bass_ratio=0.3, vocal_likelihood=0.15, lufs_short=-12.0),
        ],
    )


def test_healthy_pair_windows_are_sixteen_bars_of_time():
    out = _outgoing_125()
    inn = _track(
        "inn",
        bpm=125.0,
        camelot="8A",
        segments=[
            ("intro", 0.0, 32.0, 0.1),
            ("drop", 32.0, 315.0, 0.2),
            ("outro", 315.0, 360.0, 0.15),
        ],
    )
    d = decide_pair(out, inn)
    assert d.length_beats == 64
    assert abs((d.out_end_s - d.out_start_s) - SPAN_125_64) < 0.6
    assert abs((d.in_end_s - d.in_start_s) - SPAN_125_64) < 0.6
    assert d.out_grid_ok
    assert d.in_grid_ok


def test_broken_incoming_intro_still_gets_sixteen_bars_of_time():
    out = _outgoing_125()
    inn = _broken_intro_track()
    # Pin the old index-window bug on the synthetic incoming.
    i0 = int(np.abs(np.asarray(inn.beat_times) - 67.4).argmin())
    span_idx = window_span_s(inn.beat_times, i0, 64)
    # Either this start or some intro start must be the short index window.
    if span_idx >= 25:
        # find a 64-step window inside the intro that is short
        arr = np.asarray(inn.beat_times)
        intro = arr[arr <= 95]
        found = False
        for i in range(max(len(intro) - 64, 1)):
            if window_span_s(intro, i, 64) < 25:
                found = True
                break
        assert found
    d = decide_pair(out, inn)
    assert d.length_beats == 64
    assert abs((d.in_end_s - d.in_start_s) - SPAN_125_64) < 1.5
    assert abs((d.out_end_s - d.out_start_s) - SPAN_125_64) < 1.5
    assert not d.in_grid_ok
    assert d.grid_warning
    assert any("grid" in r.lower() for r in d.reasons)


def _nearest(times: list[float], t: float) -> int:
    return int(np.abs(np.asarray(times) - t).argmin())


def test_walk_with_me_intro_window_is_16_bars_of_time():
    rec = TrackAnalysis.model_validate_json(FIXTURE.read_text())
    i0 = _nearest(rec.beat_times, 67.4)
    i1 = _nearest(rec.beat_times, 90.96)
    assert i1 - i0 == 64
    assert rec.beat_times[i1] - rec.beat_times[i0] < 25  # today's broken span
    out = _outgoing_125(camelot=rec.camelot or "8A")
    d = decide_pair(out, rec)
    assert abs((d.in_end_s - d.in_start_s) - expected_span_s(rec.bpm, 64)) < 1.5
    assert not grid_ok(rec.beat_times[i1] - rec.beat_times[i0], rec.bpm, 64)
    assert not d.in_grid_ok
