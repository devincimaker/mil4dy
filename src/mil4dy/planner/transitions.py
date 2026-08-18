"""Transition decisions: type, length, anchors, tempo ramps, automation hints."""

from __future__ import annotations

from ..schemas import AutomationLane, PlanTransition, TempoRamp, TrackAnalysis
from .camelot import camelot_score
from .cues import TrackGrid, mix_in_anchor, mix_out_anchor

VOCAL_CLASH = 0.72


def decide_transition(a: TrackAnalysis, b: TrackAnalysis, a_grid: TrackGrid,
                      b_grid: TrackGrid, a_cue_in: int) -> tuple[str, int, int, int]:
    """Returns (type, length_beats, a_out_anchor, b_in_anchor)."""
    a_outro = next((s for s in a.segments if s.label == "outro"), None)
    b_intro = next((s for s in b.segments if s.label == "intro"), None)
    k_fit = camelot_score(a.camelot, b.camelot)
    k_conf = min(a.key_confidence, b.key_confidence)

    # Base length: 16 bars (64 beats); 32 bars when both sides have generous
    # mixable structure and keys are compatible (or unreliable enough to
    # ignore). Poor confirmed key match -> keep it to 8 bars.
    length = 64
    if a_outro is not None and b_intro is not None:
        a_bars = (a_outro.end - a_outro.start) / (4 * 60.0 / a.bpm)
        b_bars = (b_intro.end - b_intro.start) / (4 * 60.0 / b.bpm)
        if a_bars >= 12 and b_bars >= 12 and (k_fit >= 0.75 or k_conf < 0.4):
            length = 128
    if k_fit < 0.6 and k_conf >= 0.6:
        length = 32

    b_anchor, length_b = mix_in_anchor(b_grid, length)
    a_anchor, length_a = mix_out_anchor(a_grid, a_cue_in, length)
    length = min(length_a, length_b)
    # Re-anchor B so its arrival still lands at the transition end
    if length < length_b:
        b_anchor, length = mix_in_anchor(b_grid, length)

    # Vocal clash check over the overlap windows
    a_vocal = a_grid.vocal_in_window(a_anchor, a_anchor + length)
    b_vocal = b_grid.vocal_in_window(b_anchor, b_anchor + length)
    if a_vocal > VOCAL_CLASH and b_vocal > VOCAL_CLASH and length > 32:
        length = 32
        b_anchor, length = mix_in_anchor(b_grid, length)
        a_vocal = a_grid.vocal_in_window(a_anchor, a_anchor + length)
        b_vocal = b_grid.vocal_in_window(b_anchor, b_anchor + length)

    # Type decision
    if a_vocal > VOCAL_CLASH and b_vocal > VOCAL_CLASH:
        ttype = "quick_cut"
        length = 1
        b_anchor, length = mix_in_anchor(b_grid, length)
    else:
        b_first_body = next((s for s in b.segments if s.label != "intro"), None)
        a_leaving = label_at(a, a_grid.beats[min(a_anchor, a_grid.n_beats - 1)])
        if (b_first_body is not None and b_first_body.label == "drop"
                and a_leaving in ("breakdown", "outro")):
            ttype = "breakdown_blend"
        elif a_leaving == "drop" and length <= 32:
            # Short exit straight out of a drop: sweep it away. Longer overlaps
            # read better as a proper blend even when they start in the drop.
            ttype = "filter_sweep"
        else:
            ttype = "long_blend_bass_swap"
    return ttype, length, a_anchor, b_anchor


def label_at(rec: TrackAnalysis, t: float) -> str:
    for s in rec.segments:
        if s.start <= t < s.end:
            return s.label
    return "verse"


def build_automation(ttype: str, length: int) -> tuple[float, list[AutomationLane]]:
    """Returns (swap_beat, automation lanes). Beat offsets relative to overlap start."""
    if ttype == "quick_cut":
        return 0.0, [
            AutomationLane(target="out.gain_db", points=[(0.0, 0.0), (1.0, -60.0)]),
        ]

    if ttype == "filter_sweep":
        swap = float(_snap_bar(length * 0.6))
        return swap, [
            AutomationLane(target="out.lpf_hz", points=[(0.0, 18000.0), (float(length), 150.0)]),
            AutomationLane(target="out.gain_db",
                           points=[(length * 0.75, 0.0), (float(length), -60.0)]),
            AutomationLane(target="in.gain_db", points=[(0.0, -6.0), (length * 0.5, 0.0)]),
            AutomationLane(target="in.low_gain_db",
                           points=[(0.0, -80.0), (swap - 0.5, -80.0), (swap + 0.5, 0.0)]),
        ]

    if ttype == "breakdown_blend":
        swap = float(length)
        return swap, [
            AutomationLane(target="in.gain_db", points=[(0.0, -8.0), (length * 0.4, 0.0)]),
            AutomationLane(target="in.hpf_hz", points=[(0.0, 320.0), (length * 0.6, 30.0)]),
            AutomationLane(target="in.low_gain_db",
                           points=[(0.0, -80.0), (float(length) - 0.5, -80.0),
                                   (float(length), 0.0)]),
            AutomationLane(target="out.gain_db",
                           points=[(float(length) - 2.0, 0.0), (float(length), -60.0)]),
        ]

    # long_blend_bass_swap
    swap = float(_snap_bar(length / 2))
    return swap, [
        AutomationLane(target="in.gain_db", points=[(0.0, -8.0), (length * 0.25, 0.0)]),
        AutomationLane(target="in.hpf_hz", points=[(0.0, 320.0), (length * 0.5, 30.0)]),
        AutomationLane(target="in.low_gain_db",
                       points=[(0.0, -80.0), (swap - 0.5, -80.0), (swap + 0.5, 0.0)]),
        AutomationLane(target="out.low_gain_db",
                       points=[(swap - 0.5, 0.0), (swap + 0.5, -80.0)]),
        AutomationLane(target="out.gain_db",
                       points=[(float(length) * 0.6, 0.0), (float(length), -60.0)]),
    ]


def _snap_bar(beats: float) -> int:
    return max(int(round(beats / 4.0)) * 4, 4)


def make_transition(a: TrackAnalysis, b: TrackAnalysis, ttype: str, length: int,
                    a_anchor_rel: int, b_anchor_rel: int) -> PlanTransition:
    swap, lanes = build_automation(ttype, length)
    fx = ["echo_out"] if ttype == "quick_cut" else []
    return PlanTransition(
        from_id="", to_id="",  # filled by caller
        type=ttype, length_beats=length,
        out_start_beat=a_anchor_rel, in_start_beat=b_anchor_rel,
        swap_beat=swap,
        tempo_ramp=TempoRamp(from_bpm=a.bpm, to_bpm=b.bpm),
        automation=lanes, fx=fx,
    )
