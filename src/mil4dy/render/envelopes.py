"""Breakpoint automation envelopes rendered to per-sample arrays."""

from __future__ import annotations

import numpy as np

DB_FLOOR = -80.0


def db_to_amp(db: np.ndarray | float) -> np.ndarray | float:
    return 10.0 ** (np.maximum(db, DB_FLOOR) / 20.0)


class Envelope:
    """Sparse breakpoints -> per-sample values over a region.

    Interpolation is linear in the breakpoint domain (dB for gains, log-Hz for
    filter cutoffs when built via log_hz=True). Values before the first / after
    the last breakpoint hold constant.
    """

    def __init__(self, points: list[tuple[float, float]], log_domain: bool = False):
        if not points:
            raise ValueError("empty envelope")
        pts = sorted(points)
        self.x = np.array([p[0] for p in pts], dtype=np.float64)
        y = np.array([p[1] for p in pts], dtype=np.float64)
        self.log_domain = log_domain
        self.y = np.log(np.maximum(y, 1e-6)) if log_domain else y

    def render(self, positions: np.ndarray) -> np.ndarray:
        vals = np.interp(positions, self.x, self.y)
        return np.exp(vals) if self.log_domain else vals

    def render_samples(self, start: float, end: float, n: int) -> np.ndarray:
        return self.render(np.linspace(start, end, n, endpoint=False))


def equal_power_pair(n: int) -> tuple[np.ndarray, np.ndarray]:
    """(fade_out, fade_in) amplitude curves, equal power, length n."""
    x = (np.arange(n) + 0.5) / n
    return np.cos(0.5 * np.pi * x), np.sin(0.5 * np.pi * x)
