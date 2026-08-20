"""Pair planner: cue + type decisions without audio."""

from __future__ import annotations

from mil4dy.planner.pair import decide_pair, plan_pair, plan_pair_full
from mil4dy.schemas import Segment, TrackAnalysis


def _track(
    name: str,
    *,
    bpm: float = 128.0,
    duration: float = 360.0,
    camelot: str = "8A",
    energy: float = 0.6,
    segments: list[tuple[str, float, float, float]] | None = None,
) -> TrackAnalysis:
    n = int(duration * bpm / 60.0)
    beats = [round(i * 60.0 / bpm, 5) for i in range(n)]
    downs = beats[::4]
    if segments is None:
        # 30s intro, long drop, 45s outro
        segments = [
            ("intro", 0.0, 30.0, 0.1),
            ("drop", 30.0, duration - 45.0, 0.2),
            ("outro", duration - 45.0, duration, 0.15),
        ]
    segs = [
        Segment(label=lab, start=a, end=b, confidence=0.8,
                energy=0.5, bass_ratio=0.4, vocal_likelihood=voc, lufs_short=-12.0)
        for lab, a, b, voc in segments
    ]
    return TrackAnalysis(
        path=f"/tmp/{name}.wav",
        fingerprint=name,
        title=name,
        artist="Test",
        duration=duration,
        bpm=bpm,
        beat_times=beats,
        downbeat_times=downs,
        phrase_starts=downs[::8],
        key="A",
        scale="minor",
        camelot=camelot,
        key_confidence=0.9,
        energy=energy,
        segments=segs,
    )


def test_compatible_pair_blends_outro_into_intro():
    a = _track("out")
    b = _track("inn", camelot="8A")
    d = decide_pair(a, b)
    assert d.type in {"long_blend_bass_swap", "breakdown_blend", "filter_sweep"}
    assert d.length_beats >= 32
    assert d.out_label in {"outro", "breakdown", "drop", "verse"}
    assert d.in_start_s < 40.0
    assert d.camelot_score >= 0.9
    assert "clash" not in " ".join(d.reasons)


def test_clashing_keys_keep_the_blend_short():
    a = _track("out", camelot="8A")
    b = _track("inn", camelot="3A")  # tritone-ish on the wheel
    d = decide_pair(a, b)
    assert d.length_beats <= 32
    assert d.camelot_score < 0.6


def test_double_vocal_overlap_becomes_quick_cut():
    a = _track("out", segments=[
        ("intro", 0, 16, 0.1),
        ("drop", 16, 280, 0.85),
        ("outro", 280, 360, 0.9),
    ])
    b = _track("inn", segments=[
        ("intro", 0, 8, 0.85),
        ("drop", 8, 300, 0.85),
        ("outro", 300, 360, 0.2),
    ])
    d = decide_pair(a, b)
    assert d.type == "quick_cut"
    assert d.length_beats <= 8
    assert any("vocal" in r for r in d.reasons)


def test_plan_pair_is_a_short_two_track_mix():
    a = _track("out")
    b = _track("inn")
    plan, d = plan_pair(a, b)
    assert len(plan.tracks) == 2
    assert len(plan.transitions) == 1
    assert plan.transitions[0].type == d.type
    assert plan.transitions[0].length_beats == d.length_beats
    # Window should be overlap + pad, not the full 6-minute bodies
    assert plan.target_duration_s < 180
    assert plan.tracks[0].cue_out_s - plan.tracks[0].cue_in_s < 120


def test_plan_pair_full_is_both_records_joined_on_the_same_transition():
    a = _track("out")
    b = _track("inn")
    window, d = plan_pair(a, b)
    plan, full_d = plan_pair_full(a, b)
    assert full_d.type == d.type
    assert full_d.length_beats == d.length_beats
    assert full_d.a_anchor == d.a_anchor
    assert plan.tracks[0].cue_in_s == 0.0
    assert abs(plan.tracks[0].cue_out_s - d.out_end_s) < 0.05
    assert abs(plan.tracks[1].cue_in_s - d.in_start_s) < 0.05
    assert plan.tracks[1].cue_out_s > b.duration - 5.0
    assert plan.target_duration_s > window.target_duration_s + 100
    assert plan.target_duration_s > 300
