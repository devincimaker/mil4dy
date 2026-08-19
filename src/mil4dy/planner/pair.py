"""Two-track pair planning for the lab UI.

Does not run beam search. Uses the same cue / transition decision table as a
full set so the pair view is what the mixer would actually do.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from ..schemas import MixPlan, PlanTrack, TimelineEntry, TrackAnalysis
from .camelot import camelot_score
from .cues import TrackGrid, mix_in_window, mix_out_window, tempo_locked_times
from .grid import expected_span_s, grid_ok, window_span_s
from .pulse import PulseLock, lock_beats_to_onsets, onsets_for_track, pulse_warning_line
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
    expected_span_s: float
    out_index_span_s: float
    in_index_span_s: float
    out_grid_ok: bool
    in_grid_ok: bool
    grid_warning: str | None
    pulse_warning: str | None = None
    out_pulse_shift_s: float = 0.0
    in_pulse_shift_s: float = 0.0


def decide_pair(a: TrackAnalysis, b: TrackAnalysis) -> PairDecision:
    """Cue + type decision for (outgoing, incoming). No rendering."""
    a_grid, b_grid = TrackGrid(a), TrackGrid(b)
    a_cue_in = int(a_grid.downbeat_idx[0]) if len(a_grid.downbeat_idx) else 0
    ttype, length, a_anchor, b_anchor = decide_transition(
        a, b, a_grid, b_grid, a_cue_in)

    # Recompute the windows in musical time (same helpers decide_transition
    # used). End = start + length * 60/bpm, snapped. Never beats[i + length].
    a_anchor, length_a, out_start, out_end = mix_out_window(a_grid, a_cue_in, length)
    b_anchor, length_b, in_start, in_end = mix_in_window(b_grid, length)
    length = min(length, length_a, length_b)
    if length < length_a:
        a_anchor, length, out_start, out_end = mix_out_window(a_grid, a_cue_in, length)
    if length < length_b:
        b_anchor, length, in_start, in_end = mix_in_window(b_grid, length)

    tr = make_transition(a, b, ttype, length, a_anchor, b_anchor)
    k = camelot_score(a.camelot, b.camelot)
    vocal_out = a_grid.vocal_in_span(out_start, out_end)
    vocal_in = b_grid.vocal_in_span(in_start, in_end)
    bpm_gap = abs(b.bpm - a.bpm) / max(a.bpm, 1e-6)

    expected = expected_span_s(b.bpm if b.bpm else a.bpm, length)
    out_index_span = window_span_s(a_grid.beats, a_grid.beat_at_time(out_start), length)
    in_index_span = window_span_s(b_grid.beats, b_grid.beat_at_time(in_start), length)
    out_ok = grid_ok(out_index_span, a.bpm, length)
    in_ok = grid_ok(in_index_span, b.bpm, length)
    warning = None
    if not out_ok or not in_ok:
        side = "incoming" if not in_ok else "outgoing"
        span = in_index_span if not in_ok else out_index_span
        warning = (f"{length / 4:g} bars · {span:.1f}s "
                   f"(expected {expected:.1f}s) — grid looks off")

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
                         label_at(a, out_start), label_at(b, in_end),
                         out_ok=out_ok, in_ok=in_ok),
        expected_span_s=expected,
        out_index_span_s=out_index_span,
        in_index_span_s=in_index_span,
        out_grid_ok=out_ok,
        in_grid_ok=in_ok,
        grid_warning=warning,
    )


def plan_pair(a: TrackAnalysis, b: TrackAnalysis, pad_beats: int = WINDOW_PAD_BEATS
              ) -> tuple[MixPlan, PairDecision]:
    """Short MixPlan covering the overlap plus `pad_beats` of context each side."""
    decision = decide_pair(a, b)
    a_grid, b_grid = TrackGrid(a), TrackGrid(b)

    pad_s_a = expected_span_s(a.bpm, pad_beats)
    pad_s_b = expected_span_s(b.bpm, pad_beats)
    a_in_s = max(0.0, decision.out_start_s - pad_s_a)
    a_out_s = decision.out_end_s
    b_in_s = decision.in_start_s
    b_out_s = min(b.duration, decision.in_end_s + pad_s_b)
    if b_out_s <= b_in_s:
        b_out_s = min(b.duration, b_in_s + expected_span_s(b.bpm, max(decision.length_beats, 8)))

    _, ta, out_pulse = _slice_track(
        a, a_grid, a_in_s, a_out_s, "t01",
        lock_start_s=decision.out_start_s, lock_end_s=decision.out_end_s)
    _, tb, in_pulse = _slice_track(
        b, b_grid, b_in_s, b_out_s, "t02",
        lock_start_s=decision.in_start_s, lock_end_s=decision.in_end_s)
    decision = _with_pulse(decision, out_pulse, in_pulse)

    tr = make_transition(
        a, b, decision.type, decision.length_beats,
        _nearest_time_index(ta.beat_times, decision.out_start_s),
        _nearest_time_index(tb.beat_times, decision.in_start_s))
    tr.from_id = ta.id
    tr.to_id = tb.id

    overlap_s = expected_span_s(a.bpm, decision.length_beats)
    a_body_s = a_out_s - a_in_s
    b_body_s = b_out_s - b_in_s
    return MixPlan(
        target_lufs=-10.0,
        target_duration_s=round(a_body_s + b_body_s - overlap_s, 2),
        tracks=[ta, tb],
        transitions=[tr],
        timeline=[
            TimelineEntry(track=ta.id, mix_start_s=0.0, mix_end_s=round(a_body_s, 2)),
            TimelineEntry(track=tb.id, mix_start_s=round(a_body_s - overlap_s, 2),
                          mix_end_s=round(a_body_s - overlap_s + b_body_s, 2)),
        ],
    ), decision


def _nearest_time_index(times: list[float], t: float) -> int:
    if not times:
        return 0
    return int(np.abs(np.asarray(times, dtype=float) - t).argmin())


def _slice_track(rec: TrackAnalysis, grid: TrackGrid, cue_in_s: float, cue_out_s: float,
                 tid: str, *,
                 lock_start_s: float | None = None,
                 lock_end_s: float | None = None) -> tuple[int, PlanTrack, PulseLock]:
    """Embed a beat slice covering the cue window.

    If the detected grid's index window disagrees with musical time, replace
    it with a tempo-locked grid so the renderer stretches 16 bars of audio,
    not 64 irregular ticks. Then shift whatever grid we kept onto the local
    kick so two decks share a pulse after stretch.
    """
    pad_s = expected_span_s(rec.bpm, BEAT_MARGIN)
    start_s = max(0.0, cue_in_s - pad_s)
    end_s = min(rec.duration, cue_out_s + pad_s)
    n_span = max(int(round((end_s - start_s) * rec.bpm / 60.0)), 1)
    i0 = grid.beat_at_time(start_s)
    detected_ok = grid_ok(window_span_s(grid.beats, i0, n_span), rec.bpm, n_span)

    if detected_ok:
        i_in = grid.beat_at_time(cue_in_s)
        i_out = grid.beat_at_time(cue_out_s)
        s = max(0, i_in - BEAT_MARGIN)
        e = min(grid.n_beats - 1, i_out + BEAT_MARGIN)
        raw = np.asarray(grid.beats[s : e + 1], dtype=float)
        times, pulse = _lock_slice(
            rec, raw,
            lock_start_s if lock_start_s is not None else cue_in_s,
            lock_end_s if lock_end_s is not None else cue_out_s,
        )
        downs = [int(d - s) for d in grid.downbeat_idx if s <= d <= e]
        downs = [d for d in downs if 0 <= d < len(times)]
        return s, PlanTrack(
            id=tid,
            path=rec.path, title=rec.title, artist=rec.artist,
            native_bpm=rec.bpm, plateau_bpm=rec.bpm,
            key=rec.key, camelot=rec.camelot,
            lufs_integrated=rec.lufs_integrated,
            gain_db=PER_TRACK_TARGET_LUFS - rec.lufs_integrated,
            cue_in_s=cue_in_s,
            cue_out_s=cue_out_s,
            cue_in_beat=i_in - s,
            cue_out_beat=max(i_out - s, i_in - s + 1),
            beat_times=[float(b) for b in times],
            downbeat_beats=downs,
        ), pulse

    locked = tempo_locked_times(start_s, n_span, rec.bpm)
    times, pulse = _lock_slice(
        rec, locked,
        lock_start_s if lock_start_s is not None else cue_in_s,
        lock_end_s if lock_end_s is not None else cue_out_s,
    )
    period = 60.0 / max(rec.bpm, 1e-6)
    cue_in_beat = int(round((cue_in_s - float(times[0])) / period))
    cue_out_beat = int(round((cue_out_s - float(times[0])) / period))
    cue_in_beat = int(np.clip(cue_in_beat, 0, len(times) - 1))
    cue_out_beat = int(np.clip(cue_out_beat, cue_in_beat + 1, len(times) - 1))
    downs = [i for i in range(len(times)) if (i - cue_in_beat) % 4 == 0]
    return 0, PlanTrack(
        id=tid,
        path=rec.path, title=rec.title, artist=rec.artist,
        native_bpm=rec.bpm, plateau_bpm=rec.bpm,
        key=rec.key, camelot=rec.camelot,
        lufs_integrated=rec.lufs_integrated,
        gain_db=PER_TRACK_TARGET_LUFS - rec.lufs_integrated,
        cue_in_s=cue_in_s,
        cue_out_s=cue_out_s,
        cue_in_beat=cue_in_beat,
        cue_out_beat=cue_out_beat,
        beat_times=[float(t) for t in times],
        downbeat_beats=downs,
    ), pulse


def _lock_slice(rec: TrackAnalysis, beats: np.ndarray, start_s: float,
                end_s: float) -> tuple[np.ndarray, PulseLock]:
    onsets = onsets_for_track(rec.path, start_s, end_s)
    if onsets is None or len(onsets) < 6:
        return np.asarray(beats, dtype=float), PulseLock(0.0, 0.0, 0.0, 0, False)
    return lock_beats_to_onsets(beats, onsets, start_s, end_s, rec.bpm)


def _with_pulse(decision: PairDecision, out_p: PulseLock, in_p: PulseLock
                ) -> PairDecision:
    parts = [w for w in (pulse_warning_line("outgoing", out_p),
                         pulse_warning_line("incoming", in_p)) if w]
    reasons = list(decision.reasons)
    for w in parts:
        if w not in reasons:
            reasons.append(w)
    return replace(
        decision,
        reasons=reasons,
        pulse_warning=" · ".join(parts) if parts else None,
        out_pulse_shift_s=out_p.shift_s,
        in_pulse_shift_s=in_p.shift_s,
    )


def _reasons(a: TrackAnalysis, b: TrackAnalysis, ttype: str, length: int,
             k_fit: float, bpm_gap: float, vocal_out: float, vocal_in: float,
             out_label: str, in_label: str, *,
             out_ok: bool = True, in_ok: bool = True) -> list[str]:
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

    if not in_ok and not out_ok:
        reasons.append("both beat grids look off in the mix window — used musical time")
    elif not in_ok:
        reasons.append("incoming grid looks off in the mix window — used musical time")
    elif not out_ok:
        reasons.append("outgoing grid looks off in the mix window — used musical time")

    return reasons
