"""Track ordering: beam search over energy arc + tempo journey + harmony."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from ..schemas import TrackAnalysis
from .camelot import key_term

MAX_BPM_GAP = 0.06  # adjacency hard limit (each side stretches <= ~3%)
BEAM_WIDTH = 8
EXPAND_TOP = 5
JOURNEY_DRIFT = 6.0  # BPM rise across the set
EST_OVERLAP_S = 15.0


def energy_target(p: float) -> float:
    """Warm-up 0.30 -> peak 0.90 at 70% -> hold -> cooldown 0.55."""
    if p < 0.7:
        return 0.30 + (0.90 - 0.30) * (p / 0.7)
    if p < 0.85:
        return 0.90
    return 0.90 - (0.90 - 0.55) * ((p - 0.85) / 0.15)


def estimated_body_s(rec: TrackAnalysis) -> float:
    return float(min(max(rec.duration - 60.0, 120.0), 300.0))


@dataclass
class _State:
    order: list[TrackAnalysis]
    used: set[str]
    elapsed: float
    score_sum: float
    start_bpm: float
    jitter: float = field(default=0.0)

    def mean_score(self) -> float:
        return self.score_sum / max(len(self.order) - 1, 1)


def _step_score(prev: TrackAnalysis, cand: TrackAnalysis, p: float,
                journey_bpm: float, rng: random.Random | None) -> float | None:
    gap = abs(cand.bpm - prev.bpm) / prev.bpm
    if gap > MAX_BPM_GAP:
        return None
    e_fit = 1.0 - abs(cand.energy - energy_target(p))
    t_fit = 1.0 - gap / MAX_BPM_GAP
    journey = 1.0 - min(abs(cand.bpm - journey_bpm) / journey_bpm * 8.0, 1.0)
    k = key_term(prev.camelot, cand.camelot, prev.key_confidence, cand.key_confidence)

    structure_bonus = 0.0
    if any(s.label == "intro" for s in cand.segments) and any(
            s.label in ("outro", "breakdown") for s in prev.segments):
        structure_bonus = 0.1

    diversity = 0.0
    if cand.artist and cand.artist == prev.artist:
        diversity = -0.5

    score = 0.40 * e_fit + 0.20 * t_fit + 0.10 * journey + 0.20 * k + structure_bonus + diversity
    if rng is not None:
        score += rng.uniform(-0.03, 0.03)
    return score


def order_tracks(tracks: list[TrackAnalysis], minutes: float,
                 seed: int | None = None) -> list[TrackAnalysis]:
    target_s = minutes * 60.0
    rng = random.Random(seed) if seed is not None else None
    usable = [t for t in tracks if t.bpm > 60 and len(t.beat_times) > 64
              and t.duration > 150]
    if len(usable) < 4:
        raise SystemExit(f"not enough usable tracks ({len(usable)}); need at least 4")

    # Seed the beam with the best warm-up candidates
    warmup = sorted(usable, key=lambda t: abs(t.energy - energy_target(0.0)))
    beams = [
        _State(order=[t], used={t.path}, elapsed=estimated_body_s(t),
               score_sum=0.0, start_bpm=t.bpm)
        for t in warmup[:BEAM_WIDTH * 2]
    ]

    finished: list[_State] = []
    while beams:
        next_beams: list[_State] = []
        for state in beams:
            if state.elapsed >= target_s * 0.95:
                finished.append(state)
                continue
            prev = state.order[-1]
            p = state.elapsed / target_s
            journey_bpm = state.start_bpm + JOURNEY_DRIFT * p
            scored = []
            for cand in usable:
                if cand.path in state.used:
                    continue
                s = _step_score(prev, cand, p, journey_bpm, rng)
                if s is not None:
                    scored.append((s, cand))
            scored.sort(key=lambda x: -x[0])
            for s, cand in scored[:EXPAND_TOP]:
                next_beams.append(_State(
                    order=[*state.order, cand],
                    used=state.used | {cand.path},
                    elapsed=state.elapsed + estimated_body_s(cand) - EST_OVERLAP_S,
                    score_sum=state.score_sum + s,
                    start_bpm=state.start_bpm,
                ))
            if not scored:  # dead end: accept as-is
                finished.append(state)
        next_beams.sort(key=lambda st: -st.mean_score())
        beams = next_beams[:BEAM_WIDTH]

    if not finished:
        raise SystemExit("planner could not assemble a mix (tempo graph too sparse?)")

    def final_score(st: _State) -> float:
        length_pen = abs(st.elapsed - target_s) / target_s
        end_bonus = 0.15 if st.order[-1].energy <= 0.6 else 0.0
        return st.mean_score() + end_bonus - 0.5 * length_pen

    return max(finished, key=final_score).order
