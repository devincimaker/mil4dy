"""Structure-aware cue selection: where to mix into and out of each track."""

from __future__ import annotations

import numpy as np

from ..schemas import TrackAnalysis
from .grid import expected_span_s, grid_ok, window_span_s

MIN_BODY_S = 120.0
MAX_BODY_S = 300.0


class TrackGrid:
    """Beat-index bookkeeping for one analyzed track.

    Indexes are for snapping and slicing only. Musical length is always
    `n_beats * 60 / bpm`, never `beats[i + n] - beats[i]`.
    """

    def __init__(self, rec: TrackAnalysis):
        self.rec = rec
        self.beats = np.asarray(rec.beat_times, dtype=float)
        self.downbeat_idx = np.searchsorted(self.beats, np.asarray(rec.downbeat_times))
        self.downbeat_idx = self.downbeat_idx[self.downbeat_idx < len(self.beats)]
        self.n_beats = len(self.beats)

    def nearest_downbeat(self, beat: int) -> int:
        if not len(self.downbeat_idx):
            return beat
        return int(self.downbeat_idx[np.abs(self.downbeat_idx - beat).argmin()])

    def beat_at_time(self, t: float) -> int:
        if self.n_beats == 0:
            return 0
        return int(np.abs(self.beats - t).argmin())

    def time_of(self, beat: int) -> float:
        if self.n_beats == 0:
            return 0.0
        return float(self.beats[min(max(int(beat), 0), self.n_beats - 1)])

    def snap_downbeat_time(self, t: float) -> float:
        downs = np.asarray(self.rec.downbeat_times, dtype=float)
        if len(downs):
            return float(downs[np.abs(downs - t).argmin()])
        if self.n_beats == 0:
            return float(t)
        return self.time_of(self.beat_at_time(t))

    def snap_beat_time(self, t: float) -> float:
        if self.n_beats == 0:
            return float(t)
        return self.time_of(self.beat_at_time(t))

    def local_grid_ok(self, t: float, n_beats: int = 16) -> bool:
        if self.n_beats < 3 or n_beats <= 0:
            return False
        i = self.beat_at_time(t)
        i = min(i, max(self.n_beats - 1 - n_beats, 0))
        span = window_span_s(self.beats, i, n_beats)
        return grid_ok(span, self.rec.bpm, n_beats)

    def cue_time(self, t: float, *, phase_s: float | None = None,
                 bars: bool = True) -> float:
        """Snap `t` onto the musical grid.

        Bar-aligned when `bars` (16-bar blends). Beat-aligned otherwise —
        a 1-beat cut must not collapse to the same downbeat as its arrival.
        Broken local grids lock to `bpm` using `phase_s`.
        """
        t = float(np.clip(t, 0.0, max(self.rec.duration, 0.0)))
        check_n = 16 if bars else 8
        if self.local_grid_ok(t, n_beats=check_n):
            return self.snap_downbeat_time(t) if bars else self.snap_beat_time(t)
        bpm = max(self.rec.bpm, 1e-6)
        step = (4.0 if bars else 1.0) * 60.0 / bpm
        if phase_s is not None:
            phase = self.snap_downbeat_time(phase_s) if bars else self.snap_beat_time(phase_s)
        else:
            phase = t
        n = round((t - phase) / step)
        return float(np.clip(phase + n * step, 0.0, self.rec.duration))

    def vocal_in_span(self, start_s: float, end_s: float) -> float:
        """Duration-weighted vocal likelihood over a time window."""
        a, b = (start_s, end_s) if end_s >= start_s else (end_s, start_s)
        total, acc = 0.0, 0.0
        for seg in self.rec.segments:
            ov = min(seg.end, b) - max(seg.start, a)
            if ov > 0:
                acc += ov * seg.vocal_likelihood
                total += ov
        return acc / total if total > 0 else 0.0

    def vocal_in_window(self, start_beat: int, end_beat: int) -> float:
        """Vocal likelihood over a musical-time window from `start_beat`.

        `end_beat - start_beat` is treated as a beat *count* (tempo), not as
        an index span on a possibly broken grid.
        """
        n = max(int(end_beat) - int(start_beat), 0)
        a = self.time_of(start_beat)
        b = self.cue_time(a + expected_span_s(self.rec.bpm, n), phase_s=a,
                          bars=n % 4 == 0)
        return self.vocal_in_span(a, b)

    def index_span_s(self, start_s: float, n_beats: int) -> float:
        return window_span_s(self.beats, self.beat_at_time(start_s), n_beats)

    def window_grid_ok(self, start_s: float, n_beats: int) -> bool:
        return grid_ok(self.index_span_s(start_s, n_beats), self.rec.bpm, n_beats)


def arrival_time(grid: TrackGrid) -> float | None:
    """First moment that must play clean: first drop or vocal-heavy body."""
    rec = grid.rec
    intro = next((s for s in rec.segments if s.label == "intro"), None)
    if intro is None:
        return None
    arrival_seg = next(
        (s for s in rec.segments if s.label != "intro"
         and (s.label == "drop" or s.vocal_likelihood > 0.6)),
        next((s for s in rec.segments if s.label != "intro"), None),
    )
    if arrival_seg is None:
        return None
    return grid.snap_downbeat_time(arrival_seg.start)


def mix_in_window(grid: TrackGrid, transition_beats: int
                  ) -> tuple[int, int, float, float]:
    """Returns (anchor_beat, length, start_s, end_s).

    End is the arrival. Start is `end - length * 60/bpm`, snapped. A dense
    intro cannot shrink the window: 16 bars is always ~that many seconds.
    """
    rec = grid.rec
    arrival = arrival_time(grid)
    if arrival is not None:
        first_s = float(rec.downbeat_times[0]) if rec.downbeat_times else 0.0
        usable = int((arrival - first_s) * rec.bpm / 60.0) if rec.bpm else 0
        length = _shrink_length(transition_beats, max(usable, 1))
        bars = length % 4 == 0
        start_s = grid.cue_time(arrival - expected_span_s(rec.bpm, length),
                                phase_s=arrival, bars=bars)
        start_s = max(0.0, start_s)
        return grid.beat_at_time(start_s), length, start_s, arrival

    # No intro: first low-vocal 8-bar window in the first quarter of the track
    limit = grid.n_beats // 4
    candidates = [int(d) for d in grid.downbeat_idx if d < limit]
    length = _shrink_length(transition_beats, max(grid.n_beats // 4, 1))
    if candidates:
        best = min(candidates, key=lambda d: grid.vocal_in_window(d, d + 32))
        start_s = grid.time_of(best)
        end_s = grid.cue_time(start_s + expected_span_s(rec.bpm, length),
                              phase_s=start_s, bars=length % 4 == 0)
        return best, length, start_s, end_s
    length = min(transition_beats, 16)
    start_s = grid.time_of(0)
    end_s = grid.cue_time(start_s + expected_span_s(rec.bpm, length),
                          phase_s=start_s, bars=length % 4 == 0)
    return 0, length, start_s, end_s


def mix_out_window(grid: TrackGrid, cue_in_beat: int, transition_beats: int
                   ) -> tuple[int, int, float, float]:
    """Returns (anchor_beat, length, start_s, end_s) for leaving the track."""
    rec = grid.rec
    cue_in_s = grid.time_of(cue_in_beat)
    min_out_s = cue_in_s + MIN_BODY_S
    max_out_s = cue_in_s + MAX_BODY_S
    last_s = grid.time_of(grid.n_beats - 2) if grid.n_beats > 2 else rec.duration

    anchor_s = None
    outro = next((s for s in rec.segments if s.label == "outro"), None)
    if outro is not None:
        anchor_s = grid.snap_downbeat_time(outro.start)
    if anchor_s is None or anchor_s > max_out_s:
        backs = [s for s in rec.segments if s.label == "breakdown"
                 and s.start > rec.duration * 0.5]
        if backs:
            anchor_s = grid.snap_downbeat_time(backs[-1].start)
    if anchor_s is None:
        want = min(max_out_s, last_s - expected_span_s(rec.bpm, transition_beats))
        anchor_s = grid.snap_downbeat_time(want)

    lo = min_out_s
    hi = min(max_out_s, last_s - expected_span_s(rec.bpm, 8))
    if hi < lo:
        hi = max(lo, last_s * 0.5)
    anchor_s = float(np.clip(anchor_s, lo, hi))
    anchor_s = grid.snap_downbeat_time(anchor_s)

    available_beats = int((last_s - anchor_s) * rec.bpm / 60.0) if rec.bpm else 0
    if available_beats < transition_beats:
        shift_s = expected_span_s(rec.bpm, transition_beats - max(available_beats, 0))
        earlier = grid.snap_downbeat_time(max(anchor_s - shift_s, min_out_s))
        if earlier < anchor_s and grid.vocal_in_span(earlier, anchor_s) < 0.6:
            anchor_s = earlier
            available_beats = int((last_s - anchor_s) * rec.bpm / 60.0) if rec.bpm else 0
    length = _shrink_length(transition_beats, max(available_beats, 1))
    end_s = grid.cue_time(anchor_s + expected_span_s(rec.bpm, length),
                          phase_s=anchor_s, bars=length % 4 == 0)
    return grid.beat_at_time(anchor_s), length, anchor_s, end_s


def mix_in_anchor(grid: TrackGrid, transition_beats: int) -> tuple[int, int]:
    """Returns (anchor_beat, usable_transition_beats)."""
    beat, length, _, _ = mix_in_window(grid, transition_beats)
    return beat, length


def mix_out_anchor(grid: TrackGrid, cue_in_beat: int, transition_beats: int) -> tuple[int, int]:
    """Returns (anchor_beat, usable_transition_beats) for leaving the track."""
    beat, length, _, _ = mix_out_window(grid, cue_in_beat, transition_beats)
    return beat, length


def tempo_locked_times(start_s: float, n_beats: int, bpm: float) -> np.ndarray:
    """Uniform beat times covering `n_beats` steps from `start_s` (inclusive end)."""
    if n_beats <= 0 or bpm <= 0:
        return np.asarray([start_s], dtype=float)
    period = 60.0 / bpm
    return start_s + np.arange(n_beats + 1) * period


def _shrink_length(want: int, available: int) -> int:
    for length in (want, 128, 96, 64, 48, 32, 24, 16, 8):
        if length <= want and length <= available:
            return length
    return max(min(available, 4), 1)
