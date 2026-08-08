"""Filter DSP: LR4 crossover, time-varying SVF sweeps, tempo-synced delay."""

from __future__ import annotations

import numpy as np
from scipy import signal

from ..analysis.decode import RENDER_SAMPLE_RATE

CROSSOVER_HZ = 120.0

try:
    from numba import njit

    HAVE_NUMBA = True
except Exception:  # pragma: no cover
    HAVE_NUMBA = False

    def njit(*args, **kwargs):
        def deco(f):
            return f
        return deco(args[0]) if args and callable(args[0]) else deco


def lr4_split(audio: np.ndarray, sr: int = RENDER_SAMPLE_RATE,
              fc: float = CROSSOVER_HZ) -> tuple[np.ndarray, np.ndarray]:
    """Linkwitz-Riley 4th-order crossover: returns (low, high), low+high ~= input.

    LR4 = two cascaded 2nd-order Butterworths; the LP and HP outputs sum to an
    allpass version of the input (flat magnitude), which is what a DJ EQ bass
    swap needs.
    """
    sos_lp = signal.butter(2, fc, btype="low", fs=sr, output="sos")
    sos_hp = signal.butter(2, fc, btype="high", fs=sr, output="sos")
    low = signal.sosfilt(sos_lp, signal.sosfilt(sos_lp, audio, axis=0), axis=0)
    high = signal.sosfilt(sos_hp, signal.sosfilt(sos_hp, audio, axis=0), axis=0)
    return low.astype(np.float32), high.astype(np.float32)


@njit(cache=True)
def _svf_loop(x: np.ndarray, g_arr: np.ndarray, k_arr: np.ndarray,
              mode: int) -> np.ndarray:  # pragma: no cover - numba
    """TPT (Zavalishin) state-variable filter, per-sample coefficients.

    mode: 0 = lowpass, 1 = highpass. x: (n, ch). Stable under audio-rate
    modulation; per-sample coefficient update means no zipper noise.
    """
    n, ch = x.shape
    out = np.empty_like(x)
    for c in range(ch):
        ic1 = 0.0
        ic2 = 0.0
        for i in range(n):
            g = g_arr[i]
            k = k_arr[i]
            a1 = 1.0 / (1.0 + g * (g + k))
            a2 = g * a1
            a3 = g * a2
            v0 = x[i, c]
            v3 = v0 - ic2
            v1 = a1 * ic1 + a2 * v3
            v2 = ic2 + a2 * ic1 + a3 * v3
            ic1 = 2.0 * v1 - ic1
            ic2 = 2.0 * v2 - ic2
            if mode == 0:
                out[i, c] = v2
            else:
                out[i, c] = v0 - k * v1 - v2
    return out


def svf_sweep(audio: np.ndarray, cutoff_hz: np.ndarray, q: np.ndarray | float,
              mode: str, sr: int = RENDER_SAMPLE_RATE) -> np.ndarray:
    """Time-varying low/highpass sweep. cutoff_hz: per-sample cutoff array."""
    n = len(audio)
    cutoff = np.clip(np.asarray(cutoff_hz, dtype=np.float64), 20.0, sr * 0.45)
    if np.isscalar(q):
        q = np.full(n, float(q))
    g = np.tan(np.pi * cutoff / sr)
    k = 1.0 / np.asarray(q, dtype=np.float64)
    x = audio.astype(np.float64)
    if x.ndim == 1:
        x = x[:, None]
    out = _svf_loop(np.ascontiguousarray(x), g, k, 0 if mode == "lp" else 1)
    return out.astype(np.float32).reshape(audio.shape)


def tempo_delay(audio: np.ndarray, delay_samples: int, feedback: float = 0.45,
                n_repeats: int = 12, sr: int = RENDER_SAMPLE_RATE) -> np.ndarray:
    """Feedback delay tail for echo-out: returns wet tail (len = delay*n_repeats).

    Each repeat passes through a 4 kHz one-pole lowpass and 200 Hz highpass,
    the classic dub-style darkening echo.
    """
    tail_len = delay_samples * n_repeats + len(audio)
    tail = np.zeros((tail_len, 2), np.float32)
    sos_lp = signal.butter(1, 4000, btype="low", fs=sr, output="sos")
    sos_hp = signal.butter(1, 200, btype="high", fs=sr, output="sos")
    current = audio.copy()
    pos = 0
    for _ in range(n_repeats):
        pos += delay_samples
        current = signal.sosfilt(sos_lp, current, axis=0)
        current = signal.sosfilt(sos_hp, current, axis=0)
        current = (current * feedback).astype(np.float32)
        end = min(pos + len(current), tail_len)
        tail[pos:end] += current[: end - pos]
        if np.abs(current).max() < 1e-4:
            break
    return tail
