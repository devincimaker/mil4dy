"""plan_mix: analyzed library -> MixPlan (the renderer's input contract)."""

from __future__ import annotations

from ..schemas import MixPlan, PlanTrack, TimelineEntry, TrackAnalysis
from .cues import TrackGrid, mix_out_anchor
from .selection import order_tracks
from .transitions import decide_transition, make_transition

BEAT_MARGIN = 16  # extra beats embedded around the used span for tails/pre-roll
PER_TRACK_TARGET_LUFS = -16.0


def plan_mix(analyses: list[TrackAnalysis], minutes: float = 30.0,
             seed: int | None = None, target_lufs: float = -10.0) -> MixPlan:
    order = order_tracks(analyses, minutes, seed)
    grids = [TrackGrid(rec) for rec in order]
    n = len(order)

    # First pass: cue decisions per adjacent pair
    cue_in = [0] * n
    cue_out = [0] * n
    pair_info = []  # (ttype, length, a_anchor, b_anchor)
    cue_in[0] = int(grids[0].downbeat_idx[0]) if len(grids[0].downbeat_idx) else 0
    for i in range(n - 1):
        ttype, length, a_anchor, b_anchor = decide_transition(
            order[i], order[i + 1], grids[i], grids[i + 1], cue_in[i])
        pair_info.append((ttype, length, a_anchor, b_anchor))
        cue_out[i] = a_anchor + length
        cue_in[i + 1] = b_anchor
    last_anchor, last_len = mix_out_anchor(grids[-1], cue_in[-1], 8)
    cue_out[-1] = min(last_anchor + 32, grids[-1].n_beats - 2)

    # Second pass: build PlanTracks with embedded beat slices
    tracks: list[PlanTrack] = []
    slice_start: list[int] = []
    for i, (rec, grid) in enumerate(zip(order, grids)):
        s = max(0, cue_in[i] - BEAT_MARGIN)
        e = min(grid.n_beats - 1, cue_out[i] + BEAT_MARGIN)
        slice_start.append(s)
        tracks.append(PlanTrack(
            id=f"t{i + 1:02d}",
            path=rec.path, title=rec.title, artist=rec.artist,
            native_bpm=rec.bpm, plateau_bpm=rec.bpm,
            key=rec.key, camelot=rec.camelot,
            lufs_integrated=rec.lufs_integrated,
            gain_db=PER_TRACK_TARGET_LUFS - rec.lufs_integrated,
            cue_in_s=float(grid.beats[cue_in[i]]),
            cue_out_s=float(grid.beats[cue_out[i]]),
            cue_in_beat=cue_in[i] - s,
            cue_out_beat=cue_out[i] - s,
            beat_times=[float(b) for b in grid.beats[s : e + 1]],
            downbeat_beats=[int(d - s) for d in grid.downbeat_idx if s <= d <= e],
        ))

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
