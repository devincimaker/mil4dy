"""Synthetic signal generators for renderer tests."""

from __future__ import annotations

import numpy as np

SR = 44100


def click_track(bpm: float, n_beats: int, sr: int = SR, click_hz: float = 3000.0,
                amp: float = 0.8) -> tuple[np.ndarray, np.ndarray]:
    """Stereo click track. Returns (audio (n,2), beat_sample_positions).

    Clicks are short enveloped tone bursts (2 ms) — survive resampling/stretching
    better than single-sample impulses.
    """
    beat_interval = 60.0 / bpm
    beat_samples = np.round(np.arange(n_beats) * beat_interval * sr).astype(np.int64)
    total = int(beat_samples[-1] + sr * beat_interval)
    audio = np.zeros((total, 2), np.float32)
    dur = int(0.002 * sr)
    t = np.arange(dur) / sr
    burst = (amp * np.sin(2 * np.pi * click_hz * t) * np.hanning(dur * 2)[dur:]).astype(np.float32)
    for b in beat_samples:
        audio[b : b + dur, 0] += burst
        audio[b : b + dur, 1] += burst
    return audio, beat_samples


def detect_clicks(audio: np.ndarray, sr: int = SR, thresh_ratio: float = 0.3) -> np.ndarray:
    """Return sample positions of click onsets (envelope threshold crossings)."""
    mono = np.abs(audio).max(axis=1) if audio.ndim == 2 else np.abs(audio)
    thresh = mono.max() * thresh_ratio
    above = mono > thresh
    # Rising edges, then suppress edges within 50 ms of the previous onset
    edges = np.flatnonzero(above[1:] & ~above[:-1]) + 1
    if len(edges) == 0:
        return edges
    keep = [edges[0]]
    min_gap = int(0.05 * sr)
    for e in edges[1:]:
        if e - keep[-1] > min_gap:
            keep.append(e)
    return np.array(keep)


def tone(freqs: list[float], seconds: float, sr: int = SR, amp: float = 0.3) -> np.ndarray:
    """Stereo sum of sines."""
    t = np.arange(int(seconds * sr)) / sr
    y = sum(np.sin(2 * np.pi * f * t) for f in freqs) * (amp / max(len(freqs), 1))
    return np.stack([y, y], axis=1).astype(np.float32)
