"""JSON shapes the pair-lab UI consumes. Not the renderer's MixPlan."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from ..planner.pair import PairDecision
from ..schemas import Segment, TrackAnalysis


class SegmentView(BaseModel):
    label: str
    start: float
    end: float
    energy: float
    vocal_likelihood: float
    bass_ratio: float
    confidence: float


class TrackView(BaseModel):
    id: str
    path: str
    title: str
    artist: str
    genre: str
    duration: float
    bpm: float
    key: str
    scale: str
    camelot: str
    key_confidence: float
    energy: float
    lufs_integrated: float
    downbeat_confidence: float
    beats_engine: str
    n_beats: int
    segments: list[SegmentView]
    phrase_starts: list[float] = Field(default_factory=list)


class DecisionView(BaseModel):
    type: str
    length_beats: int
    length_bars: float
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
    window_duration_s: float
    window_expected_s: float
    out_index_span_s: float
    in_index_span_s: float
    out_grid_ok: bool
    in_grid_ok: bool
    grid_warning: str | None = None
    pulse_warning: str | None = None
    out_pulse_shift_s: float = 0.0
    in_pulse_shift_s: float = 0.0
    blend_start_s: float = 0.0
    blend_end_s: float = 0.0


class PairResponse(BaseModel):
    a: TrackView
    b: TrackView
    decision: DecisionView


class PairRequest(BaseModel):
    a: str
    b: str


def segment_view(s: Segment) -> SegmentView:
    return SegmentView(
        label=s.label, start=s.start, end=s.end, energy=s.energy,
        vocal_likelihood=s.vocal_likelihood, bass_ratio=s.bass_ratio,
        confidence=s.confidence,
    )


def track_view(rec: TrackAnalysis) -> TrackView:
    title = rec.title or Path(rec.path).stem
    artist = rec.artist or "Unknown"
    return TrackView(
        id=rec.fingerprint,
        path=rec.path,
        title=title,
        artist=artist,
        genre=rec.genre,
        duration=rec.duration,
        bpm=round(rec.bpm, 2),
        key=rec.key,
        scale=rec.scale,
        camelot=rec.camelot,
        key_confidence=round(rec.key_confidence, 3),
        energy=round(rec.energy, 3),
        lufs_integrated=round(rec.lufs_integrated, 2),
        downbeat_confidence=round(rec.downbeat_confidence, 3),
        beats_engine=rec.beats_engine,
        n_beats=len(rec.beat_times),
        segments=[segment_view(s) for s in rec.segments],
        phrase_starts=[round(t, 3) for t in rec.phrase_starts],
    )


def decision_view(d: PairDecision, window_duration_s: float,
                  blend_start_s: float = 0.0, blend_end_s: float = 0.0
                  ) -> DecisionView:
    return DecisionView(
        type=d.type,
        length_beats=d.length_beats,
        length_bars=round(d.length_beats / 4.0, 2),
        out_start_s=round(d.out_start_s, 3),
        in_start_s=round(d.in_start_s, 3),
        out_end_s=round(d.out_end_s, 3),
        in_end_s=round(d.in_end_s, 3),
        out_label=d.out_label,
        in_arrival_label=d.in_arrival_label,
        swap_beat=d.swap_beat,
        bpm_gap=round(d.bpm_gap, 4),
        camelot_score=round(d.camelot_score, 3),
        vocal_out=round(d.vocal_out, 3),
        vocal_in=round(d.vocal_in, 3),
        fx=d.fx,
        reasons=d.reasons,
        window_duration_s=round(window_duration_s, 2),
        window_expected_s=round(d.expected_span_s, 3),
        out_index_span_s=round(d.out_index_span_s, 3),
        in_index_span_s=round(d.in_index_span_s, 3),
        out_grid_ok=d.out_grid_ok,
        in_grid_ok=d.in_grid_ok,
        grid_warning=d.grid_warning,
        pulse_warning=d.pulse_warning,
        out_pulse_shift_s=round(d.out_pulse_shift_s, 4),
        in_pulse_shift_s=round(d.in_pulse_shift_s, 4),
        blend_start_s=round(blend_start_s, 3),
        blend_end_s=round(blend_end_s, 3),
    )
