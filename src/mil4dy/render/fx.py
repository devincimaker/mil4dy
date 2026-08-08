"""Transition FX layers, rendered additively into the master buffer."""

from __future__ import annotations

import numpy as np

from ..analysis.decode import RENDER_SAMPLE_RATE
from .envelopes import db_to_amp
from .filters import tempo_delay


def echo_out(master: np.ndarray, source: np.ndarray, at_sample: int, bpm: float,
             sr: int = RENDER_SAMPLE_RATE, level_db: float = -6.0) -> None:
    """Dotted-eighth feedback echo of `source` (the outgoing last beat), summed
    into master starting at `at_sample`."""
    delay = int(round(60.0 / bpm * 0.75 * sr))  # dotted eighth = 3/4 beat
    tail = tempo_delay(source, delay) * np.float32(db_to_amp(level_db))
    end = min(at_sample + len(tail), len(master))
    if end > at_sample:
        master[at_sample:end] += tail[: end - at_sample]
