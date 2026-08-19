"""Beat and downbeat detection: beat_this primary, librosa fallback."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .decode import ANALYSIS_SAMPLE_RATE


class BeatEngine:
    """Lazy-loading beat/downbeat detector. One instance per process."""

    def __init__(self, device: str | None = None):
        self._a2b = None
        self._device = device
        self.name = "uninitialized"
        self.dbn = False

    def _load(self):
        if self._a2b is not None:
            return
        try:
            from beat_this.inference import Audio2Beats

            device = self._device
            if device is None:
                import torch

                device = "mps" if torch.backends.mps.is_available() else "cpu"
            self._a2b, self.dbn = _load_audio2beats(device)
            self.name = "beat_this-1.1.0-dbn" if self.dbn else "beat_this-1.1.0"
        except Exception:
            self._a2b = False
            self.dbn = False
            self.name = "librosa-fallback"

    def detect(self, y: np.ndarray, sr: int = ANALYSIS_SAMPLE_RATE
               ) -> tuple[np.ndarray, np.ndarray, float, float, bool]:
        """Returns (beat_times, downbeats, confidence, intro_bpm, intro_ok).

        Confidence is computed from interval regularity + beat-count error.
        It is never a hardcoded 0.9. Intro stats are scored on the raw
        detector output, before any uniform-grid rebuild.
        """
        self._load()
        duration = len(y) / float(sr) if sr else 0.0
        if self._a2b:
            try:
                beats, downbeats = self._a2b(y, sr)
                beats = np.asarray(beats, dtype=float)
                downbeats = np.asarray(downbeats, dtype=float)
                if len(beats) >= 16 and len(downbeats) >= 4:
                    return regularize_beats(beats, downbeats, duration)
            except Exception:
                pass
        return _librosa_beats(y, sr)


def _load_audio2beats(device: str):
    """Prefer DBN (steady pulse). Fall back to dbn=False only if load fails."""
    from beat_this.inference import Audio2Beats

    for dev in (device, "cpu"):
        try:
            return Audio2Beats(checkpoint_path="final0", device=dev, dbn=True), True
        except Exception:
            continue
    for dev in (device, "cpu"):
        try:
            return Audio2Beats(checkpoint_path="final0", device=dev, dbn=False), False
        except Exception:
            continue
    raise RuntimeError("Audio2Beats failed to load")


def _librosa_beats(y: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray, float]:
    """Fallback: librosa beat grid + bass-onset downbeat phase estimation."""
    import librosa

    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=512, trim=False)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=512)
    duration = len(y) / float(sr) if sr else 0.0
    if len(beat_times) < 16:
        return beat_times, beat_times[:0], 0.0, 0.0, True

    # Downbeat phase: bass-band onset strength should peak on beat 1 of the bar.
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512, fmax=200)
    strengths = np.interp(beat_times, librosa.times_like(onset, sr=sr, hop_length=512), onset)
    phase_scores = [strengths[p::4].mean() for p in range(4)]
    phase = int(np.argmax(phase_scores))
    downbeat_times = beat_times[phase::4]
    return regularize_beats(np.asarray(beat_times, dtype=float),
                            np.asarray(downbeat_times, dtype=float), duration)


@dataclass(frozen=True)
class PulseFit:
    """Least-squares pulse: t ≈ phase + n × period on stored beat times."""

    bpm: float
    period: float
    phase: float
    rms: float

    @property
    def ok(self) -> bool:
        return self.bpm > 0.0 and self.period > 1e-6


def fit_pulse(beat_times: np.ndarray | list[float],
              lo_frac: float = 0.1, hi_frac: float = 0.9) -> PulseFit:
    """Fit a line through beat times. `phase` is the implied time of beat 0.

    Median of 20 ms–quantized gaps collapses house at 124–128 to 125. The
    slope through the same ticks recovers 124 / 127 because the snap averages
    out over a long span. Middle 80% ignores garbage intros.
    """
    arr = np.asarray(beat_times, dtype=float)
    n = len(arr)
    if n < 3:
        return PulseFit(0.0, 0.0, 0.0, 0.0)
    lo = int(n * lo_frac)
    hi = max(int(n * hi_frac), lo + 3)
    hi = min(hi, n)
    sl = arr[lo:hi]
    if len(sl) < 3:
        sl = arr
        lo = 0
    idx = np.arange(lo, lo + len(sl), dtype=float)
    design = np.column_stack((np.ones(len(idx)), idx))
    try:
        intercept, period = np.linalg.lstsq(design, sl, rcond=None)[0]
    except Exception:
        return PulseFit(0.0, 0.0, 0.0, 0.0)
    if not np.isfinite(period) or period <= 1e-6:
        return PulseFit(0.0, 0.0, 0.0, 0.0)
    pred = intercept + idx * period
    rms = float(np.sqrt(np.mean((sl - pred) ** 2)))
    bpm = float(60.0 / period)
    if not np.isfinite(bpm) or bpm <= 0.0:
        return PulseFit(0.0, 0.0, float(intercept), rms)
    return PulseFit(bpm, float(period), float(intercept), rms)


def robust_bpm(beat_times: np.ndarray | list[float]) -> float:
    """BPM from a least-squares pulse fit through beat times."""
    return fit_pulse(beat_times).bpm


def interval_cv(beat_times: np.ndarray, lo_frac: float = 0.1, hi_frac: float = 0.9
                ) -> float:
    """Coefficient of variation of inter-beat intervals (middle slice)."""
    arr = np.asarray(beat_times, dtype=float)
    if len(arr) < 4:
        return 1.0
    n = len(arr)
    lo, hi = int(n * lo_frac), max(int(n * hi_frac), int(n * lo_frac) + 2)
    iv = np.diff(arr[lo:hi])
    iv = iv[iv > 1e-6]
    if len(iv) < 2:
        return 1.0
    mean = float(np.mean(iv))
    if mean <= 1e-9:
        return 1.0
    return float(np.std(iv) / mean)


def beat_count_error(n_beats: int, duration: float, bpm: float) -> float:
    expected = duration * bpm / 60.0 if bpm > 0 and duration > 0 else 0.0
    if expected <= 0:
        return 1.0
    return abs(n_beats - expected) / expected


def beat_confidence(beat_times: np.ndarray | list[float], duration: float,
                    bpm: float | None = None) -> float:
    """Real grid score in [0, 1]. Regular house ≈ high; jittery intros ≈ low.

    Combines interval CV on the middle 80% with whole-span beat-count error.
    """
    arr = np.asarray(beat_times, dtype=float)
    if len(arr) < 16 or duration <= 0:
        return 0.0
    if bpm is None:
        bpm = robust_bpm(arr)
    if bpm <= 0:
        return 0.0
    cv = interval_cv(arr)
    err = beat_count_error(len(arr), duration, bpm)
    score = 1.0 - min(1.0, 2.5 * cv) - min(0.5, 4.0 * err)
    return float(np.clip(score, 0.0, 1.0))


def rebuild_uniform_grid(duration: float, bpm: float,
                         downbeat_times: np.ndarray | list[float] | None = None,
                         phase: float | None = None
                         ) -> tuple[np.ndarray, np.ndarray]:
    """Tempo-locked grid: arange(first, duration, 60/bpm), downbeats every 4.

    `phase` is the time of beat 0 from `fit_pulse`. Without it, the first
    stored downbeat sets the pulse.
    """
    if duration <= 0 or bpm <= 0:
        return np.zeros(0), np.zeros(0)
    period = 60.0 / bpm
    downs = np.asarray(downbeat_times if downbeat_times is not None else [], dtype=float)
    if phase is not None:
        first = float(phase)
        if first < 0.0:
            first += np.ceil(-first / period) * period
        if first >= duration:
            first = first % period
    elif len(downs):
        db0 = float(downs[0])
        first = db0 - np.floor(db0 / period) * period
        if first < 0:
            first += period
    else:
        first = 0.0
    if len(downs):
        db_phase = int(round((float(downs[0]) - first) / period)) % 4
    else:
        db_phase = 0
    beats = np.arange(first, duration, period)
    if len(beats) == 0:
        beats = np.asarray([first], dtype=float)
    return beats, beats[db_phase::4]


def score_intro(beat_times: np.ndarray | list[float], duration: float,
                bpm: float, intro_end: float | None = None) -> tuple[float, bool]:
    """Count-based intro tempo + whether that slice matches `bpm`."""
    from ..planner.grid import grid_ok, local_bpm

    arr = np.asarray(beat_times, dtype=float)
    end = intro_end if intro_end is not None else min(90.0, max(duration * 0.25, 0.0))
    sl = arr[(arr >= 0.0) & (arr <= end)]
    intro_local = local_bpm(sl)
    if len(sl) < 8 or bpm <= 0:
        return intro_local, True
    ok = grid_ok(float(sl[-1] - sl[0]), bpm, len(sl) - 1)
    return intro_local, ok


def regularize_beats(beats: np.ndarray, downbeats: np.ndarray, duration: float
                     ) -> tuple[np.ndarray, np.ndarray, float, float, bool]:
    """Score the raw grid, then replace ticks with the fitted pulse.

    House does not speed up 20 ms and slow down 20 ms every other beat.
    We rebuild because we know the period, not only when CV looks drunk.
    Confidence and intro stats stay on the raw detector output.
    """
    fit = fit_pulse(beats)
    bpm = fit.bpm
    conf = beat_confidence(beats, duration, bpm)
    intro_bpm, intro_ok = score_intro(beats, duration, bpm)
    if fit.ok and duration > 0:
        beats, downbeats = rebuild_uniform_grid(
            duration, bpm, downbeats, phase=fit.phase)
    return (np.asarray(beats, dtype=float), np.asarray(downbeats, dtype=float),
            conf, intro_bpm, intro_ok)


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
