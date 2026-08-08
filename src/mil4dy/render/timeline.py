"""Plan -> scheduled, stretched, sample-placed per-track buffers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..analysis.decode import RENDER_SAMPLE_RATE
from ..schemas import MixPlan, PlanTrack
from .audio_io import decode_stereo
from .clock import OutputClock, build_set_bpms
from .envelopes import db_to_amp
from .stretch import piecewise_stretch, plan_anchors


@dataclass
class ScheduledTrack:
    plan: PlanTrack
    audio: np.ndarray  # stretched float32 (n, 2), starts at output sample `offset`
    offset: int  # output sample where audio[0] sits (== clock sample of cue_in beat)
    beat_out_samples: np.ndarray  # output-absolute sample of each played beat
    n_beats: int  # audible beats (cue_out - cue_in)


def build_clock(plan: MixPlan) -> tuple[OutputClock, list[int]]:
    spans = []
    for i, t in enumerate(plan.tracks):
        overlap_out = plan.transitions[i].length_beats if i < len(plan.transitions) else 0
        spans.append({
            "bpm": t.plateau_bpm,
            "n_beats": t.cue_out_beat - t.cue_in_beat,
            "overlap_out": overlap_out,
        })
    bpms, entries = build_set_bpms(spans)
    return OutputClock(bpms), entries


def schedule_track(plan: MixPlan, i: int, clock: OutputClock, entries: list[int],
                   sr: int = RENDER_SAMPLE_RATE) -> ScheduledTrack:
    t = plan.tracks[i]
    audio = decode_stereo(Path(t.path))
    audio *= np.float32(db_to_amp(t.gain_db))

    n_beats = t.cue_out_beat - t.cue_in_beat
    beat_times = np.asarray(t.beat_times)
    in_samples = np.round(beat_times[t.cue_in_beat : t.cue_out_beat + 1] * sr).astype(np.int64)
    out_samples = clock.beat_samples[entries[i] : entries[i] + n_beats + 1]

    dense: list[tuple[int, int]] = []
    if i > 0:
        ramp = plan.transitions[i - 1]
        if abs(ramp.tempo_ramp.from_bpm - ramp.tempo_ramp.to_bpm) > 0.01:
            dense.append((0, ramp.length_beats))
    if i < len(plan.transitions):
        tr = plan.transitions[i]
        if abs(tr.tempo_ramp.from_bpm - tr.tempo_ramp.to_bpm) > 0.01:
            dense.append((n_beats - tr.length_beats, n_beats))

    anchors = plan_anchors(in_samples, out_samples, dense)
    stretched = piecewise_stretch(audio, in_samples[anchors], out_samples[anchors], sr)
    return ScheduledTrack(
        plan=t, audio=stretched, offset=int(out_samples[0]),
        beat_out_samples=out_samples, n_beats=n_beats,
    )
