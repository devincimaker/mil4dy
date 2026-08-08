"""Structure-aware cue selection: where to mix into and out of each track."""

from __future__ import annotations

import numpy as np

from ..schemas import TrackAnalysis

MIN_BODY_S = 120.0
MAX_BODY_S = 300.0


class TrackGrid:
    """Beat-index bookkeeping for one analyzed track."""

    def __init__(self, rec: TrackAnalysis):
        self.rec = rec
        self.beats = np.asarray(rec.beat_times)
        self.downbeat_idx = np.searchsorted(self.beats, np.asarray(rec.downbeat_times))
        self.downbeat_idx = self.downbeat_idx[self.downbeat_idx < len(self.beats)]
        self.n_beats = len(self.beats)

    def nearest_downbeat(self, beat: int) -> int:
        if not len(self.downbeat_idx):
            return beat
        return int(self.downbeat_idx[np.abs(self.downbeat_idx - beat).argmin()])

    def beat_at_time(self, t: float) -> int:
        return int(np.abs(self.beats - t).argmin())

    def vocal_in_window(self, start_beat: int, end_beat: int) -> float:
        """Duration-weighted vocal likelihood over a beat window."""
        a = self.beats[min(start_beat, self.n_beats - 1)]
        b = self.beats[min(end_beat, self.n_beats - 1)]
        total, acc = 0.0, 0.0
        for seg in self.rec.segments:
            ov = min(seg.end, b) - max(seg.start, a)
            if ov > 0:
                acc += ov * seg.vocal_likelihood
                total += ov
        return acc / total if total > 0 else 0.0


def mix_in_anchor(grid: TrackGrid, transition_beats: int) -> tuple[int, int]:
    """Returns (anchor_beat, usable_transition_beats).

    Prefer entering at the intro so that the transition ends exactly where the
    first non-intro section arrives (on a downbeat). Shrinks the transition if
    the intro is shorter.
    """
    rec = grid.rec
    intro = next((s for s in rec.segments if s.label == "intro"), None)
    first_body = next((s for s in rec.segments if s.label != "intro"), None)

    if intro is not None and first_body is not None:
        arrival = grid.nearest_downbeat(grid.beat_at_time(first_body.start))
        first_db = int(grid.downbeat_idx[0]) if len(grid.downbeat_idx) else 0
        usable = arrival - first_db
        length = _shrink_length(transition_beats, usable)
        return grid.nearest_downbeat(arrival - length), length

    # No intro: first low-vocal 8-bar window in the first quarter of the track
    limit = grid.n_beats // 4
    candidates = [int(d) for d in grid.downbeat_idx if d < limit]
    if candidates:
        best = min(candidates, key=lambda d: grid.vocal_in_window(d, d + 32))
        return best, _shrink_length(transition_beats, grid.n_beats // 4)
    return 0, min(transition_beats, 16)


def mix_out_anchor(grid: TrackGrid, cue_in_beat: int, transition_beats: int) -> tuple[int, int]:
    """Returns (anchor_beat, usable_transition_beats) for leaving the track.

    Prefer the outro, then the last breakdown in the back half, then the phrase
    boundary `transition_beats` before the end. Clamped so the body stays within
    MIN/MAX_BODY_S at native tempo.
    """
    rec = grid.rec
    spb = 60.0 / rec.bpm  # seconds per beat
    min_out = cue_in_beat + int(MIN_BODY_S / spb)
    max_out = cue_in_beat + int(MAX_BODY_S / spb)
    last_usable = grid.n_beats - 2

    anchor = None
    outro = next((s for s in rec.segments if s.label == "outro"), None)
    if outro is not None:
        anchor = grid.nearest_downbeat(grid.beat_at_time(outro.start))
    if anchor is None or anchor > max_out:
        backs = [s for s in rec.segments if s.label == "breakdown"
                 and s.start > rec.duration * 0.5]
        if backs:
            anchor = grid.nearest_downbeat(grid.beat_at_time(backs[-1].start))
    if anchor is None:
        anchor = grid.nearest_downbeat(min(max_out, last_usable - transition_beats))

    anchor = int(np.clip(anchor, min_out, min(max_out, last_usable - 8)))
    anchor = grid.nearest_downbeat(anchor)
    length = _shrink_length(transition_beats, last_usable - anchor)
    return anchor, length


def _shrink_length(want: int, available: int) -> int:
    for length in (want, 64, 32, 16, 8):
        if length <= want and length <= available:
            return length
    return max(min(available, 4), 1)
