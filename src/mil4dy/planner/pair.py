"""Two-track pair planning for the lab UI.

Does not run beam search. Uses the same cue / transition decision table as a
full set so the pair view is what the mixer would actually do.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..schemas import MixPlan, PlanTrack, TimelineEntry, TrackAnalysis
from .camelot import camelot_score
from .cues import TrackGrid
from .transitions import decide_transition, label_at, make_transition

BEAT_MARGIN = 16
PER_TRACK_TARGET_LUFS = -16.0

# Extra phrases around the overlap so "hear the blend" has context.
WINDOW_PAD_BEATS = 32


@dataclass(frozen=True)
class PairDecision:
    type: str
    length_beats: int
    a_anchor: int
    b_anchor: int
    out_start_s: float
    in_start_s: float
    out_end_s: float
    in_end_s: float
    out_label: str
    in_arrival_label: str
    swap_beat: float
    bpm_gap: float
    camelot_score: float
    vocal_out: float
    vocal_in: float
    fx: list[str]
    reasons: list[str]


def decide_pair(a: TrackAnalysis, b: TrackAnalysis) -> PairDecision:
    """Cue + type decision for (outgoing, incoming). No rendering."""
    a_grid, b_grid = TrackGrid(a), TrackGrid(b)
    a_cue_in = int(a_grid.downbeat_idx[0]) if len(a_grid.downbeat_idx) else 0
    ttype, length, a_anchor, b_anchor = decide_transition(
        a, b, a_grid, b_grid, a_cue_in)

    out_start = float(a_grid.beats[min(a_anchor, a_grid.n_beats - 1)])
    in_start = float(b_grid.beats[min(b_anchor, b_grid.n_beats - 1)])
    a_end_i = min(a_anchor + length, a_grid.n_beats - 1)
    b_end_i = min(b_anchor + length, b_grid.n_beats - 1)
    out_end = float(a_grid.beats[a_end_i])
    in_end = float(b_grid.beats[b_end_i])

    tr = make_transition(a, b, ttype, length, a_anchor, b_anchor)
    k = camelot_score(a.camelot, b.camelot)
    vocal_out = a_grid.vocal_in_window(a_anchor, a_anchor + length)
    vocal_in = b_grid.vocal_in_window(b_anchor, b_anchor + length)
    bpm_gap = abs(b.bpm - a.bpm) / max(a.bpm, 1e-6)

    return PairDecision(
        type=ttype,
        length_beats=length,
        a_anchor=a_anchor,
        b_anchor=b_anchor,
        out_start_s=out_start,
        in_start_s=in_start,
        out_end_s=out_end,
        in_end_s=in_end,
        out_label=label_at(a, out_start),
        in_arrival_label=label_at(b, in_end),
        swap_beat=tr.swap_beat,
        bpm_gap=bpm_gap,
        camelot_score=k,
        vocal_out=vocal_out,
        vocal_in=vocal_in,
        fx=list(tr.fx),
        reasons=_reasons(a, b, ttype, length, k, bpm_gap, vocal_out, vocal_in,
                         label_at(a, out_start), label_at(b, in_end)),
    )


def plan_pair(a: TrackAnalysis, b: TrackAnalysis, pad_beats: int = WINDOW_PAD_BEATS
              ) -> tuple[MixPlan, PairDecision]:
    """Short MixPlan covering the overlap plus `pad_beats` of context each side."""
    decision = decide_pair(a, b)
    a_grid, b_grid = TrackGrid(a), TrackGrid(b)

    a_in = a_grid.nearest_downbeat(max(0, decision.a_anchor - pad_beats))
    a_out = min(a_grid.n_beats - 2, decision.a_anchor + decision.length_beats)
    b_in = decision.b_anchor
    b_out = b_grid.nearest_downbeat(
        min(b_grid.n_beats - 2, decision.b_anchor + decision.length_beats + pad_beats))
    if b_out <= b_in:
        b_out = min(b_grid.n_beats - 2, b_in + max(decision.length_beats, 8))
    return _plan_window(a, b, a_grid, b_grid, decision, a_in, a_out, b_in, b_out), decision


def plan_pair_full(a: TrackAnalysis, b: TrackAnalysis) -> tuple[MixPlan, PairDecision]:
    """Two-song mix: outgoing from the start through the send, incoming from mix-in to the end."""
    decision = decide_pair(a, b)
    a_grid, b_grid = TrackGrid(a), TrackGrid(b)

    a_in = 0
    a_out = min(a_grid.n_beats - 2, decision.a_anchor + decision.length_beats)
    if a_out <= a_in:
        a_out = min(a_grid.n_beats - 2, a_in + max(decision.length_beats, 8))
    b_in = decision.b_anchor
    b_out = max(b_in + 1, b_grid.n_beats - 2)
    return _plan_window(a, b, a_grid, b_grid, decision, a_in, a_out, b_in, b_out), decision


def _plan_window(
    a: TrackAnalysis, b: TrackAnalysis, a_grid: TrackGrid, b_grid: TrackGrid,
    decision: PairDecision, a_in: int, a_out: int, b_in: int, b_out: int,
) -> MixPlan:
    a_slice, ta = _slice_track(a, a_grid, a_in, a_out, "t01")
    b_slice, tb = _slice_track(b, b_grid, b_in, b_out, "t02")

    tr = make_transition(
        a, b, decision.type, decision.length_beats,
        decision.a_anchor - a_slice, decision.b_anchor - b_slice)
    tr.from_id = ta.id
    tr.to_id = tb.id

    spb_a = 60.0 / max(a.bpm, 1.0)
    overlap_s = decision.length_beats * spb_a
    a_body_s = (a_out - a_in) * spb_a
    return MixPlan(
        target_lufs=-10.0,
        target_duration_s=round(a_body_s + (b_out - b_in) * (60.0 / max(b.bpm, 1.0))
                                - overlap_s, 2),
        tracks=[ta, tb],
        transitions=[tr],
        timeline=[
            TimelineEntry(track=ta.id, mix_start_s=0.0, mix_end_s=round(a_body_s, 2)),
            TimelineEntry(track=tb.id, mix_start_s=round(a_body_s - overlap_s, 2),
                          mix_end_s=round(a_body_s - overlap_s
                                          + (b_out - b_in) * (60.0 / max(b.bpm, 1.0)), 2)),
        ],
    )


def _slice_track(rec: TrackAnalysis, grid: TrackGrid, cue_in: int, cue_out: int,
                 tid: str) -> tuple[int, PlanTrack]:
    s = max(0, cue_in - BEAT_MARGIN)
    e = min(grid.n_beats - 1, cue_out + BEAT_MARGIN)
    return s, PlanTrack(
        id=tid,
        path=rec.path, title=rec.title, artist=rec.artist,
        native_bpm=rec.bpm, plateau_bpm=rec.bpm,
        key=rec.key, camelot=rec.camelot,
        lufs_integrated=rec.lufs_integrated,
        gain_db=PER_TRACK_TARGET_LUFS - rec.lufs_integrated,
        cue_in_s=float(grid.beats[cue_in]),
        cue_out_s=float(grid.beats[min(cue_out, grid.n_beats - 1)]),
        cue_in_beat=cue_in - s,
        cue_out_beat=cue_out - s,
        beat_times=[float(b) for b in grid.beats[s : e + 1]],
        downbeat_beats=[int(d - s) for d in grid.downbeat_idx if s <= d <= e],
    )


def _reasons(a: TrackAnalysis, b: TrackAnalysis, ttype: str, length: int,
             k_fit: float, bpm_gap: float, vocal_out: float, vocal_in: float,
             out_label: str, in_label: str) -> list[str]:
    bars = max(length / 4.0, 0.25)
    pretty = ttype.replace("_", " ")
    reasons = [f"{bars:g} bars · {pretty}"]

    if k_fit >= 0.9:
        reasons.append(f"{a.camelot or '?'} → {b.camelot or '?'} is a close key")
    elif k_fit >= 0.75:
        reasons.append(f"{a.camelot or '?'} → {b.camelot or '?'} is mixable")
    elif k_fit >= 0.6:
        reasons.append(f"{a.camelot or '?'} → {b.camelot or '?'} is a stretch")
    else:
        reasons.append(f"{a.camelot or '?'} → {b.camelot or '?'} will clash — kept short")

    gap_bpm = bpm_gap * a.bpm
    if bpm_gap <= 0.02:
        reasons.append(f"tempos sit {gap_bpm:.1f} BPM apart")
    else:
        reasons.append(f"tempos differ by {gap_bpm:.1f} BPM — will ramp")

    reasons.append(f"leave the {out_label}, arrive on the {in_label}")

    if vocal_out > 0.72 and vocal_in > 0.72:
        reasons.append("both windows are vocal-heavy — cutting instead of blending")
    elif max(vocal_out, vocal_in) > 0.5:
        reasons.append(
            f"vocals in the overlap (out {vocal_out:.0%}, in {vocal_in:.0%})")
    else:
        reasons.append("overlap looks instrumental enough to blend")

    return reasons
