"""Song-structure segmentation: beat-synced SSM + Foote novelty, EDM-rule labels."""

from __future__ import annotations

import numpy as np

from ..schemas import Segment
from .features import FrameFeatures, lufs_of_span, raw_energy


def _beat_sync(matrix: np.ndarray, frame_times: np.ndarray, beat_times: np.ndarray) -> np.ndarray:
    """Average frames within each beat interval -> (features, n_beats-1)."""
    idx = np.searchsorted(frame_times, beat_times)
    cols = []
    for a, b in zip(idx[:-1], idx[1:]):
        b = max(b, a + 1)
        cols.append(matrix[:, a:b].mean(axis=1))
    return np.stack(cols, axis=1)


def novelty_curve(ff: FrameFeatures, beat_times: np.ndarray, kernel_beats: int = 32) -> np.ndarray:
    """Foote checkerboard novelty over a beat-synchronous self-similarity matrix."""
    feats = np.vstack([
        _beat_sync(ff.mfcc, ff.times, beat_times),
        _beat_sync(ff.chroma, ff.times, beat_times),
        _beat_sync(ff.contrast, ff.times, beat_times),
        _beat_sync(ff.rms[None, :], ff.times, beat_times),
    ])
    feats = (feats - feats.mean(axis=1, keepdims=True)) / (feats.std(axis=1, keepdims=True) + 1e-9)
    norms = np.linalg.norm(feats, axis=0) + 1e-9
    ssm = (feats.T @ feats) / np.outer(norms, norms)

    k = kernel_beats // 2
    sign = np.outer(np.r_[-np.ones(k), np.ones(k)], np.r_[-np.ones(k), np.ones(k)])
    gauss = np.exp(-0.5 * (np.linspace(-2, 2, 2 * k) ** 2))
    kernel = sign * np.outer(gauss, gauss)

    n = ssm.shape[0]
    nov = np.zeros(n)
    for i in range(k, n - k):
        nov[i] = (ssm[i - k : i + k, i - k : i + k] * kernel).sum()
    nov -= nov.min()
    if nov.max() > 0:
        nov /= nov.max()
    return nov


def _pick_boundaries(nov: np.ndarray, beat_times: np.ndarray, downbeat_times: np.ndarray,
                     min_gap_beats: int = 32) -> list[float]:
    """Novelty peaks -> boundary times snapped to the nearest downbeat."""
    order = np.argsort(nov)[::-1]
    chosen: list[int] = []
    for i in order:
        if nov[i] < 0.25:
            break
        if all(abs(i - j) >= min_gap_beats for j in chosen):
            chosen.append(int(i))
    times = []
    for i in sorted(chosen):
        t = beat_times[i]
        snapped = downbeat_times[np.abs(downbeat_times - t).argmin()]
        times.append(float(snapped))
    return sorted(set(times))


def segment_track(y: np.ndarray, sr: int, ff: FrameFeatures, beat_times: np.ndarray,
                  downbeat_times: np.ndarray, duration: float) -> tuple[list[Segment], np.ndarray]:
    """Returns (labeled segments, novelty boundary times used for phrase phasing)."""
    if len(beat_times) < 64 or len(downbeat_times) < 8:
        stats = ff.span_stats(0, duration)
        seg = Segment(label="verse", start=0.0, end=duration, confidence=0.2,
                      energy=raw_energy(stats), bass_ratio=stats["bass_ratio"],
                      vocal_likelihood=stats["vocal_likelihood"],
                      lufs_short=lufs_of_span(y, sr, 0, duration))
        return [seg], np.array([])

    nov = novelty_curve(ff, beat_times)
    bounds = _pick_boundaries(nov, beat_times[:-1], downbeat_times)
    edges = [0.0, *[b for b in bounds if 5.0 < b < duration - 5.0], duration]
    edges = sorted(set(edges))
    # Enforce min segment length of 8 bars (~15 s at 128 BPM): merge short ones forward
    bar = float(np.median(np.diff(downbeat_times)))
    min_len = 8 * bar
    merged = [edges[0]]
    for e in edges[1:-1]:
        if e - merged[-1] >= min_len:
            merged.append(e)
    merged.append(edges[-1])
    if len(merged) >= 3 and merged[-1] - merged[-2] < min_len:
        merged.pop(-2)

    spans = list(zip(merged[:-1], merged[1:]))
    stats = [ff.span_stats(a, b) for a, b in spans]
    return _label(spans, stats, y, sr), np.array(bounds)


def _label(spans: list[tuple[float, float]], stats: list[dict],
           y: np.ndarray, sr: int) -> list[Segment]:
    n = len(spans)
    rms = np.array([s["rms"] for s in stats])
    bass = np.array([s["bass_ratio"] for s in stats])
    rms_max = rms.max() + 1e-12
    bass_med = np.median(bass) + 1e-12

    labels: list[str] = ["verse"] * n
    scores: list[float] = [0.5] * n

    for i in range(n):
        margin = 0.5
        if i == 0 and rms[i] < 0.65 * rms_max:
            labels[i] = "intro"
            margin = 1.0 - rms[i] / (0.65 * rms_max)
        elif i == n - 1 and rms[i] < 0.65 * rms_max:
            labels[i] = "outro"
            margin = 1.0 - rms[i] / (0.65 * rms_max)
        elif 0 < i and bass[i] < 0.5 * bass_med and rms[i] < 0.8 * rms_max:
            labels[i] = "breakdown"
            margin = 1.0 - bass[i] / (0.5 * bass_med)
        elif rms[i] > 0.85 * rms_max and bass[i] >= bass_med:
            labels[i] = "drop"
            margin = rms[i] / rms_max
        scores[i] = float(np.clip(margin, 0.1, 1.0))

    # A verse directly before a drop with rising rms is a build
    for i in range(1, n):
        if labels[i] == "drop" and labels[i - 1] == "verse" and rms[i - 1] < rms[i]:
            labels[i - 1] = "build"

    return [
        Segment(label=labels[i], start=spans[i][0], end=spans[i][1], confidence=scores[i],
                energy=raw_energy(stats[i]), bass_ratio=stats[i]["bass_ratio"],
                vocal_likelihood=stats[i]["vocal_likelihood"],
                lufs_short=lufs_of_span(y, sr, spans[i][0], spans[i][1]))
        for i in range(n)
    ]
