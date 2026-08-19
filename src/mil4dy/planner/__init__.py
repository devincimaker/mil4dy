"""plan_mix: analyzed library -> MixPlan (the renderer's input contract)."""

from __future__ import annotations

from ..schemas import MixPlan, PlanTrack, TimelineEntry, TrackAnalysis
from .cues import TrackGrid, mix_out_anchor
from .grid import expected_span_s
from .pair import _slice_track, decide_pair, plan_pair, plan_pair_full
from .selection import order_tracks
from .transitions import decide_transition, make_transition

BEAT_MARGIN = 16  # extra beats embedded around the used span for tails/pre-roll
PER_TRACK_TARGET_LUFS = -16.0

__all__ = [
    "BEAT_MARGIN",
    "PER_TRACK_TARGET_LUFS",
    "decide_pair",
    "plan_mix",
    "plan_pair",
    "plan_pair_full",
]


def plan_mix(analyses: list[TrackAnalysis], minutes: float = 30.0,
             seed: int | None = None, target_lufs: float = -10.0) -> MixPlan:
    target_s = minutes * 60.0
    candidates = order_tracks(analyses, minutes * 1.2, seed)
    all_grids = [TrackGrid(rec) for rec in candidates]

    # Cue pass: consume ordered tracks until the actual duration hits the target
    order: list = [candidates[0]]
    grids: list[TrackGrid] = [all_grids[0]]
    cue_in = [int(all_grids[0].downbeat_idx[0]) if len(all_grids[0].downbeat_idx) else 0]
    cue_out: list[int] = []
    pair_info: list[tuple] = []  # (ttype, length, a_anchor, b_anchor)
    elapsed = 0.0  # seconds up to the current last track's entry

    def close_last() -> int:
        anchor, _ = mix_out_anchor(grids[-1], cue_in[-1], 8)
        return min(anchor + 32, grids[-1].n_beats - 2)

    for nxt_rec, nxt_grid in zip(candidates[1:], all_grids[1:]):
        end_beat = close_last()
        spb = 60.0 / order[-1].bpm
        if elapsed + (end_beat - cue_in[-1]) * spb >= target_s * 0.97 and len(order) >= 4:
            break
        ttype, length, a_anchor, b_anchor = decide_transition(
            order[-1], nxt_rec, grids[-1], nxt_grid, cue_in[-1])
        pair_info.append((ttype, length, a_anchor, b_anchor))
        out_end_s = grids[-1].cue_time(
            grids[-1].time_of(a_anchor) + expected_span_s(order[-1].bpm, length),
            phase_s=grids[-1].time_of(a_anchor))
        cue_out.append(grids[-1].beat_at_time(out_end_s))
        elapsed += (a_anchor - cue_in[-1]) * spb
        order.append(nxt_rec)
        grids.append(nxt_grid)
        cue_in.append(b_anchor)
    cue_out.append(close_last())
    n = len(order)

    # Second pass: build PlanTracks with embedded beat slices
    tracks: list[PlanTrack] = []
    slice_start: list[int] = []
    for i, (rec, grid) in enumerate(zip(order, grids)):
        cue_in_s = float(grid.beats[cue_in[i]])
        cue_out_s = float(grid.beats[cue_out[i]])
        if i < n - 1:
            lock_s = float(grid.beats[min(pair_info[i][2], grid.n_beats - 1)])
            lock_e = cue_out_s
        elif i > 0:
            lock_s = cue_in_s
            lock_e = float(grid.beats[min(
                cue_in[i] + pair_info[i - 1][1], grid.n_beats - 1)])
        else:
            lock_s, lock_e = cue_in_s, cue_out_s
        s, pt, _ = _slice_track(
            rec, grid, cue_in_s, cue_out_s, f"t{i + 1:02d}",
            lock_start_s=lock_s, lock_end_s=lock_e,
        )
        slice_start.append(s)
        tracks.append(pt)

    transitions = []
    for i, (ttype, length, a_anchor, b_anchor) in enumerate(pair_info):
        tr = make_transition(order[i], order[i + 1], ttype, length,
                             a_anchor - slice_start[i], b_anchor - slice_start[i + 1])
        tr.from_id = tracks[i].id
        tr.to_id = tracks[i + 1].id
        transitions.append(tr)

    # QA timeline (approximate: native tempo, ramps ignored)
    timeline: list[TimelineEntry] = []
    t = 0.0
    for i in range(n):
        spb = 60.0 / order[i].bpm
        n_beats = cue_out[i] - cue_in[i]
        timeline.append(TimelineEntry(track=tracks[i].id, mix_start_s=round(t, 2),
                                      mix_end_s=round(t + n_beats * spb, 2)))
        overlap = pair_info[i][1] if i < n - 1 else 0
        t += (n_beats - overlap) * spb

    return MixPlan(
        target_lufs=target_lufs,
        target_duration_s=round(timeline[-1].mix_end_s, 2),
        tracks=tracks, transitions=transitions, timeline=timeline,
    )
