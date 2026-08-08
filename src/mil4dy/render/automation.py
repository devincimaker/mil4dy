"""Apply a transition's automation lanes to one deck's buffer region."""

from __future__ import annotations

import numpy as np

from ..schemas import PlanTransition
from .envelopes import Envelope, db_to_amp
from .filters import lr4_split, svf_sweep


def _lane(tr: PlanTransition, name: str) -> list[tuple[float, float]] | None:
    for lane in tr.automation:
        if lane.target == name:
            return lane.points
    return None


def apply_deck_automation(buf: np.ndarray, r0: int, r1: int,
                          beat_positions: np.ndarray, tr: PlanTransition,
                          side: str) -> None:
    """Mutate buf[r0:r1] according to the `side.` lanes of transition `tr`.

    beat_positions: float beat offset within the overlap, per sample of the
    region. side: "in" or "out".
    """
    r1 = min(r1, len(buf))
    if r1 <= r0:
        return
    region = buf[r0:r1]
    pos = beat_positions[: r1 - r0]

    low_pts = _lane(tr, f"{side}.low_gain_db")
    hpf_pts = _lane(tr, f"{side}.hpf_hz")
    lpf_pts = _lane(tr, f"{side}.lpf_hz")
    gain_pts = _lane(tr, f"{side}.gain_db")

    if low_pts is not None or hpf_pts is not None:
        low, high = lr4_split(region)
        if low_pts is not None:
            low *= db_to_amp(Envelope(low_pts).render(pos)).astype(np.float32)[:, None]
        if hpf_pts is not None:
            cutoff = Envelope(hpf_pts, log_domain=True).render(pos)
            high = svf_sweep(high, cutoff, q=0.71, mode="hp")
        region = low + high

    if lpf_pts is not None:
        cutoff = Envelope(lpf_pts, log_domain=True).render(pos)
        # Slight resonant color rising as the sweep closes (Q 0.8 -> 1.1)
        span = pos / max(pos[-1], 1e-9)
        q = 0.8 + 0.3 * span
        region = svf_sweep(region, cutoff, q=q, mode="lp")

    if gain_pts is not None:
        region = region * db_to_amp(Envelope(gain_pts).render(pos)).astype(np.float32)[:, None]

    buf[r0:r1] = region
