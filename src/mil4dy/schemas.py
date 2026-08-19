"""Shared data contracts: TrackAnalysis (analysis cache) and MixPlan (planner -> renderer)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ANALYSIS_VERSION = 4
PLAN_VERSION = 2

SegmentLabel = Literal["intro", "build", "drop", "breakdown", "verse", "outro"]
TransitionType = Literal["long_blend_bass_swap", "filter_sweep", "quick_cut", "breakdown_blend"]


class Segment(BaseModel):
    label: SegmentLabel
    start: float  # seconds
    end: float
    confidence: float
    energy: float  # 0-1, library-normalized
    bass_ratio: float
    vocal_likelihood: float
    lufs_short: float


class TrackAnalysis(BaseModel):
    analysis_version: int = ANALYSIS_VERSION
    path: str
    fingerprint: str
    title: str = ""
    artist: str = ""
    genre: str = ""
    duration: float

    bpm: float
    beats_per_bar: int = 4
    beat_times: list[float]
    downbeat_times: list[float]
    phrase_starts: list[float] = Field(default_factory=list)  # 8-bar grid
    downbeat_confidence: float = 1.0
    intro_grid_ok: bool = True
    intro_bpm: float = 0.0
    beats_engine: str = "beat_this-1.1.0"

    key: str = ""
    scale: str = ""
    camelot: str = ""
    key_confidence: float = 0.0
    key_engine: str = "essentia-edma"

    lufs_integrated: float = -14.0
    energy: float = 0.5  # track aggregate, library-normalized
    segments: list[Segment] = Field(default_factory=list)
    bass_profile: list[float] = Field(default_factory=list)  # one value per bar

    def segments_with(self, label: str) -> list[Segment]:
        return [s for s in self.segments if s.label == label]


class TempoRamp(BaseModel):
    from_bpm: float
    to_bpm: float
    shape: Literal["linear"] = "linear"


class AutomationLane(BaseModel):
    """Planner hint: beat offsets relative to overlap start -> values (dB or Hz)."""

    target: str  # e.g. "in.low_gain_db", "out.gain_db", "in.hpf_hz"
    points: list[tuple[float, float]]


class PlanTrack(BaseModel):
    id: str
    path: str
    title: str = ""
    artist: str = ""
    native_bpm: float
    plateau_bpm: float  # playback BPM between its transitions (== native, per plan design)
    key: str = ""
    camelot: str = ""
    lufs_integrated: float
    gain_db: float = 0.0  # pregain toward per-track normalization target
    cue_in_s: float
    cue_out_s: float
    cue_in_beat: int  # index into beat_times
    cue_out_beat: int
    beat_times: list[float]  # source-time seconds; used span + transition margins
    downbeat_beats: list[int]  # indices into beat_times that are downbeats


class PlanTransition(BaseModel):
    from_id: str
    to_id: str
    type: TransitionType
    length_beats: int
    out_start_beat: int  # in the outgoing track's beat grid (start of overlap)
    in_start_beat: int  # in the incoming track's grid (incoming audible from here)
    swap_beat: float = 0.0  # beat offset in overlap where bass swap / arrival happens
    tempo_ramp: TempoRamp
    automation: list[AutomationLane] = Field(default_factory=list)
    fx: list[str] = Field(default_factory=list)  # e.g. ["echo_out", "noise_riser"]


class TimelineEntry(BaseModel):
    track: str
    mix_start_s: float
    mix_end_s: float


class MixPlan(BaseModel):
    plan_version: int = PLAN_VERSION
    target_lufs: float = -10.0
    target_duration_s: float
    tracks: list[PlanTrack]
    transitions: list[PlanTransition]
    timeline: list[TimelineEntry] = Field(default_factory=list)

    def track_by_id(self, tid: str) -> PlanTrack:
        for t in self.tracks:
            if t.id == tid:
                return t
        raise KeyError(tid)
