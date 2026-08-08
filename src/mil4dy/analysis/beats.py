"""Beat and downbeat detection: beat_this primary, librosa fallback."""

from __future__ import annotations

import numpy as np

from .decode import ANALYSIS_SAMPLE_RATE


class BeatEngine:
    """Lazy-loading beat/downbeat detector. One instance per process."""

    def __init__(self, device: str | None = None):
        self._a2b = None
        self._device = device
        self.name = "uninitialized"

    def _load(self):
        if self._a2b is not None:
            return
        try:
            from beat_this.inference import Audio2Beats

            device = self._device
            if device is None:
                import torch

                device = "mps" if torch.backends.mps.is_available() else "cpu"
            try:
                self._a2b = Audio2Beats(checkpoint_path="final0", device=device, dbn=False)
            except Exception:
                self._a2b = Audio2Beats(checkpoint_path="final0", device="cpu", dbn=False)
            self.name = "beat_this-1.1.0"
        except Exception:
            self._a2b = False
            self.name = "librosa-fallback"

    def detect(self, y: np.ndarray, sr: int = ANALYSIS_SAMPLE_RATE
               ) -> tuple[np.ndarray, np.ndarray, float]:
        """Returns (beat_times, downbeat_times, confidence)."""
        self._load()
        if self._a2b:
            try:
                beats, downbeats = self._a2b(y, sr)
                if len(beats) >= 16 and len(downbeats) >= 4:
                    return np.asarray(beats), np.asarray(downbeats), 0.9
            except Exception:
                pass
        return _librosa_beats(y, sr)


def _librosa_beats(y: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray, float]:
    """Fallback: librosa beat grid + bass-onset downbeat phase estimation."""
    import librosa

    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=512, trim=False)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=512)
    if len(beat_times) < 16:
        return beat_times, beat_times[:0], 0.0

    # Downbeat phase: bass-band onset strength should peak on beat 1 of the bar.
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512, fmax=200)
    strengths = np.interp(beat_times, librosa.times_like(onset, sr=sr, hop_length=512), onset)
    phase_scores = [strengths[p::4].mean() for p in range(4)]
    phase = int(np.argmax(phase_scores))
    downbeat_times = beat_times[phase::4]
    return beat_times, downbeat_times, 0.3


def robust_bpm(beat_times: np.ndarray) -> float:
    """BPM from the median beat interval over the middle 80% of the track."""
    if len(beat_times) < 3:
        return 0.0
    n = len(beat_times)
    lo, hi = int(n * 0.1), max(int(n * 0.9), int(n * 0.1) + 2)
    return float(60.0 / np.median(np.diff(beat_times[lo:hi])))


def phrase_grid(downbeat_times: np.ndarray, novelty_times: np.ndarray | None = None,
                bars_per_phrase: int = 8) -> np.ndarray:
    """8-bar phrase boundaries, phased to align with structural novelty peaks.

    Picks the bar offset (0..bars_per_phrase-1) that puts phrase boundaries
    closest to novelty peaks; without novelty, phase 0.
    """
    if len(downbeat_times) < bars_per_phrase:
        return downbeat_times[:1]
    best_phase = 0
    if novelty_times is not None and len(novelty_times):
        scores = []
        for phase in range(bars_per_phrase):
            starts = downbeat_times[phase::bars_per_phrase]
            dists = [np.abs(starts - t).min() for t in novelty_times if len(starts)]
            scores.append(np.mean(dists) if dists else np.inf)
        best_phase = int(np.argmin(scores))
    return downbeat_times[best_phase::bars_per_phrase]
