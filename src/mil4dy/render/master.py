"""Mastering: LUFS measurement/normalization and true-peak lookahead limiting."""

from __future__ import annotations

import numpy as np

from ..analysis.decode import RENDER_SAMPLE_RATE

try:
    from numba import njit

    HAVE_NUMBA = True
except Exception:  # pragma: no cover
    HAVE_NUMBA = False

    def njit(*args, **kwargs):
        def deco(f):
            return f
        return deco(args[0]) if args and callable(args[0]) else deco


def measure_lufs(audio: np.ndarray, sr: int = RENDER_SAMPLE_RATE) -> float:
    import pyloudnorm

    meter = pyloudnorm.Meter(sr)
    val = meter.integrated_loudness(audio.astype(np.float64))
    return float(val) if np.isfinite(val) else -70.0


def true_peak_db(audio: np.ndarray, sr: int = RENDER_SAMPLE_RATE) -> float:
    import soxr

    over = soxr.resample(audio, sr, sr * 4)
    peak = np.abs(over).max()
    return float(20 * np.log10(max(peak, 1e-12)))


@njit(cache=True)
def _limiter_gain(required: np.ndarray, lookahead: int, release_coeff: float
                  ) -> np.ndarray:  # pragma: no cover - numba
    """Lookahead gain smoothing: sliding minimum over the lookahead window
    (monotonic deque), then one-pole release toward 1.0."""
    n = len(required)
    smin = np.empty(n)
    deque_idx = np.empty(n, dtype=np.int64)
    head, tail = 0, 0
    for i in range(n):
        end = min(i + lookahead, n - 1)
        while tail > head and required[deque_idx[tail - 1]] >= required[end]:
            tail -= 1
        deque_idx[tail] = end
        tail += 1
        while deque_idx[head] < i:
            head += 1
        smin[i] = required[deque_idx[head]]
    gain = np.empty(n)
    g = 1.0
    for i in range(n):
        target = smin[i]
        if target < g:
            g = target  # instant attack (lookahead provides the ramp headroom)
        else:
            g = target + (g - target) * release_coeff
            if g > 1.0:
                g = 1.0
        gain[i] = g
    return gain


def limit(audio: np.ndarray, ceiling_db: float = -1.0, lookahead_ms: float = 5.0,
          release_ms: float = 200.0, sr: int = RENDER_SAMPLE_RATE) -> np.ndarray:
    """True-peak-aware lookahead limiter.

    Detection runs on the 4x-oversampled signal (decimated back to 1x positions);
    gain is applied at 1x. Good enough for a -1 dBTP ceiling.
    """
    import soxr

    ceiling = 10.0 ** (ceiling_db / 20.0)
    over = soxr.resample(audio.astype(np.float32), sr, sr * 4)
    peak_env = np.abs(over).max(axis=1)
    n = len(audio)
    idx = np.clip((np.arange(n) * 4), 0, len(peak_env) - 4)
    peak_1x = np.maximum.reduce([peak_env[idx], peak_env[idx + 1],
                                 peak_env[idx + 2], peak_env[idx + 3]])
    required = np.minimum(ceiling / np.maximum(peak_1x, 1e-12), 1.0)
    lookahead = int(lookahead_ms / 1000 * sr)
    release_coeff = float(np.exp(-1.0 / (release_ms / 1000 * sr)))
    gain = _limiter_gain(required.astype(np.float64), lookahead, release_coeff)
    # Attack ramp: causal trailing average of the lookahead sliding-min. Every
    # term in the window [i-L, i] has its own min-window covering sample i, so
    # the smoothed gain can never exceed the gain the peak at i requires.
    kernel = np.ones(lookahead) / lookahead
    gain = np.convolve(gain, kernel, mode="full")[: len(gain)]
    return (audio * gain[:, None].astype(np.float32)).astype(np.float32)


def master_chain(audio: np.ndarray, target_lufs: float,
                 sr: int = RENDER_SAMPLE_RATE) -> tuple[np.ndarray, dict]:
    measured = measure_lufs(audio, sr)
    gain_db = target_lufs - measured
    out = audio * np.float32(10.0 ** (gain_db / 20.0))
    out = limit(out, sr=sr)
    report = {
        "pre_master_lufs": round(measured, 2),
        "master_gain_db": round(gain_db, 2),
        "final_lufs": round(measure_lufs(out, sr), 2),
        "final_true_peak_dbtp": round(true_peak_db(out, sr), 2),
    }
    return out, report
