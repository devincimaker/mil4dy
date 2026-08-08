"""The critical de-risking test: clock integration + piecewise stretch + placement.

Two synthetic click tracks at different BPMs go through a tempo-ramped set plan;
every rendered click must land within 1 ms of the OutputClock's prediction, and
overlap clicks from both decks must coincide.
"""

import numpy as np

from mil4dy.render.clock import OutputClock, build_set_bpms
from mil4dy.render.stretch import piecewise_stretch, plan_anchors

from .synth import SR, click_track, detect_clicks

TOL = int(0.001 * SR)  # 1 ms


def stretch_track_to_clock(audio, beat_samples, entry_set_beat, n_beats, clock,
                           dense_ranges=()):
    """Map track beats [0, n_beats] onto set beats [entry, entry+n_beats]."""
    in_samples = beat_samples[: n_beats + 1]
    out_samples = clock.beat_samples[entry_set_beat : entry_set_beat + n_beats + 1]
    anchors = plan_anchors(in_samples, out_samples, list(dense_ranges))
    stretched = piecewise_stretch(audio, in_samples[anchors], out_samples[anchors])
    return stretched, int(out_samples[0])


def test_constant_tempo_alignment():
    # 128 BPM source pinned to a 124 BPM clock: every segment needs stretching.
    audio, beats = click_track(128.0, 34)
    bpms, entries = build_set_bpms([{"bpm": 124.0, "n_beats": 32, "overlap_out": 0}])
    clock = OutputClock(bpms)
    stretched, offset = stretch_track_to_clock(audio, beats, 0, 32, clock)
    clicks = detect_clicks(stretched)
    expected = clock.beat_samples[:32]
    assert len(clicks) == 32, f"expected 32 clicks, found {len(clicks)}"
    err = np.abs(clicks - expected)
    assert err.max() <= TOL, f"max alignment error {err.max()} samples ({err.max()/SR*1000:.2f} ms)"


def test_native_tempo_direct_copy():
    # Clock at the track's own BPM: direct-copy fast path, still sample-pinned.
    audio, beats = click_track(126.0, 34)
    bpms, _ = build_set_bpms([{"bpm": 126.0, "n_beats": 32, "overlap_out": 0}])
    clock = OutputClock(bpms)
    stretched, _ = stretch_track_to_clock(audio, beats, 0, 32, clock)
    clicks = detect_clicks(stretched)
    err = np.abs(clicks - clock.beat_samples[:32])
    assert len(clicks) == 32
    assert err.max() <= 4, f"direct-copy error {err.max()} samples"


def test_tempo_ramp_two_deck_alignment():
    # Track A at 124 BPM, track B at 130 BPM, 16-beat overlap with tempo ramp.
    a_audio, a_beats = click_track(124.0, 50)
    b_audio, b_beats = click_track(130.0, 50)
    spans = [
        {"bpm": 124.0, "n_beats": 48, "overlap_out": 16},
        {"bpm": 130.0, "n_beats": 48, "overlap_out": 0},
    ]
    bpms, entries = build_set_bpms(spans)
    clock = OutputClock(bpms)

    # Ramp occupies set beats 32..48 == A beats 32..48 == B beats 0..16
    a_str, a_off = stretch_track_to_clock(a_audio, a_beats, entries[0], 48, clock,
                                          dense_ranges=[(32, 48)])
    b_str, b_off = stretch_track_to_clock(b_audio, b_beats, entries[1], 48, clock,
                                          dense_ranges=[(0, 16)])

    a_clicks = detect_clicks(a_str) + a_off
    b_clicks = detect_clicks(b_str) + b_off

    assert len(a_clicks) == 48
    assert len(b_clicks) == 48

    a_err = np.abs(a_clicks - clock.beat_samples[entries[0] : entries[0] + 48])
    b_err = np.abs(b_clicks - clock.beat_samples[entries[1] : entries[1] + 48])
    assert a_err.max() <= TOL, f"deck A max err {a_err.max()/SR*1000:.2f} ms"
    assert b_err.max() <= TOL, f"deck B max err {b_err.max()/SR*1000:.2f} ms"

    # Overlap: A's beats 32..47 must coincide with B's beats 0..15
    coincide = np.abs(a_clicks[32:48] - b_clicks[0:16])
    assert coincide.max() <= TOL, f"deck coincidence max err {coincide.max()/SR*1000:.2f} ms"


def test_clock_ramp_integration():
    # BPM ramp beats must be monotonically shorter going 120 -> 130
    spans = [
        {"bpm": 120.0, "n_beats": 16, "overlap_out": 8},
        {"bpm": 130.0, "n_beats": 16, "overlap_out": 0},
    ]
    bpms, entries = build_set_bpms(spans)
    assert entries == [0, 8]
    assert len(bpms) == 16 + 8 + 1  # A solo 8 + overlap 8 + B remaining 8, +1 closing
    clock = OutputClock(bpms)
    intervals = np.diff(clock.beat_times)
    ramp = intervals[8:16]
    assert np.all(np.diff(ramp) < 0), "ramp intervals should shrink as BPM rises"
    np.testing.assert_allclose(intervals[:8], 60 / 120.0, rtol=1e-9)
    np.testing.assert_allclose(intervals[-8:], 60 / 130.0, rtol=1e-9)
