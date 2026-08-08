"""OutputClock: the set's beat grid on the output timeline.

Built from a per-set-beat BPM array; integrates beat durations to give the
output sample position of every set beat. This is the single source of truth
for where a beat lands — both decks in a transition are stretched to it, so
alignment is exact by construction.
"""

from __future__ import annotations

import numpy as np

from ..analysis.decode import RENDER_SAMPLE_RATE


class OutputClock:
    def __init__(self, bpms: np.ndarray, sample_rate: int = RENDER_SAMPLE_RATE):
        """bpms[k] = instantaneous BPM at set beat k (length = total beats + 1)."""
        bpms = np.asarray(bpms, dtype=np.float64)
        if len(bpms) < 2:
            raise ValueError("need at least 2 beat BPM values")
        if np.any(bpms <= 0):
            raise ValueError("BPM values must be positive")
        self.sample_rate = sample_rate
        self.bpms = bpms
        # Trapezoidal integration: interval k->k+1 lasts 60 / mean(bpm_k, bpm_k+1)
        interval = 60.0 / ((bpms[:-1] + bpms[1:]) / 2.0)
        times = np.concatenate([[0.0], np.cumsum(interval)])
        self.beat_times = times
        self.beat_samples = np.round(times * sample_rate).astype(np.int64)

    @property
    def n_beats(self) -> int:
        return len(self.beat_samples)

    @property
    def total_samples(self) -> int:
        return int(self.beat_samples[-1])

    def sample_of(self, set_beat: float) -> int:
        """Output sample of a (possibly fractional) set beat."""
        return int(round(float(np.interp(set_beat, np.arange(self.n_beats), self.beat_samples))))


def build_set_bpms(spans: list[dict]) -> tuple[np.ndarray, list[int]]:
    """Build the per-set-beat BPM array from plan track spans.

    Each span: {"bpm": plateau bpm,
                "n_beats": audible beats (cue_out_beat - cue_in_beat),
                "overlap_out": outgoing transition length in beats (0 for last)}

    Track i+1 enters at the set beat where track i's outgoing overlap starts;
    during the overlap the two grids coincide beat-for-beat and the BPM ramps
    linearly from span i's plateau to span i+1's.

    Returns (bpms array of length total_beats+1, entry set-beat of each track).
    """
    entries: list[int] = []
    pos = 0
    for span in spans:
        entries.append(pos)
        pos += span["n_beats"] - span["overlap_out"]
    total_beats = entries[-1] + spans[-1]["n_beats"]

    bpms = np.empty(total_beats + 1, dtype=np.float64)
    for i, span in enumerate(spans):
        bpms[entries[i] : entries[i] + span["n_beats"] + 1] = span["bpm"]
    for i in range(len(spans) - 1):
        length = spans[i]["overlap_out"]
        s = entries[i + 1]
        bpms[s : s + length + 1] = np.linspace(spans[i]["bpm"], spans[i + 1]["bpm"], length + 1)
    return bpms, entries
