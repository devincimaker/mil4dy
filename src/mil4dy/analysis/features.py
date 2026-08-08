"""Loudness, energy, and spectral features driving planner decisions."""

from __future__ import annotations

import numpy as np

from .decode import ANALYSIS_SAMPLE_RATE

HOP = 512


def integrated_lufs(y: np.ndarray, sr: int) -> float:
    import pyloudnorm

    meter = pyloudnorm.Meter(sr)
    data = y if y.ndim == 1 else y
    lufs = meter.integrated_loudness(data.astype(np.float64))
    return float(lufs) if np.isfinite(lufs) else -70.0


def lufs_of_span(y: np.ndarray, sr: int, start_s: float, end_s: float) -> float:
    a, b = int(start_s * sr), int(end_s * sr)
    span = y[a:b]
    if len(span) < sr:  # pyloudnorm needs >= 400ms; be generous
        return -70.0
    return integrated_lufs(span, sr)


class FrameFeatures:
    """Per-frame features at HOP resolution, computed once per track."""

    def __init__(self, y: np.ndarray, sr: int = ANALYSIS_SAMPLE_RATE):
        import librosa

        self.sr = sr
        stft = np.abs(librosa.stft(y, n_fft=2048, hop_length=HOP))
        freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
        power = stft**2
        total = power.sum(axis=0) + 1e-12

        self.times = librosa.times_like(stft[0], sr=sr, hop_length=HOP)
        self.rms = librosa.feature.rms(S=stft, hop_length=HOP)[0]
        self.bass_ratio = power[freqs < 150].sum(axis=0) / total
        self.centroid = librosa.feature.spectral_centroid(S=stft, sr=sr)[0]
        self.onset = librosa.onset.onset_strength(S=librosa.amplitude_to_db(stft), sr=sr)
        # Vocal band: energy share 300-3000 Hz, weighted by spectral flatness inverse
        # (vocals are harmonic -> low flatness in that band).
        vocal_band = power[(freqs >= 300) & (freqs <= 3000)]
        self.vocal_ratio = vocal_band.sum(axis=0) / total
        flatness = librosa.feature.spectral_flatness(S=stft[(freqs >= 300) & (freqs <= 3000)])[0]
        self.vocal_likelihood_frames = self.vocal_ratio * (1.0 - np.clip(flatness * 4, 0, 1))

        # Beat-sync-able matrices for structure analysis
        self.mfcc = librosa.feature.mfcc(S=librosa.power_to_db(
            librosa.feature.melspectrogram(S=power, sr=sr)), n_mfcc=20)
        self.chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=HOP)
        self.contrast = librosa.feature.spectral_contrast(S=stft, sr=sr)

    def span_stats(self, start_s: float, end_s: float) -> dict:
        m = (self.times >= start_s) & (self.times < end_s)
        if not m.any():
            m = np.zeros_like(m)
            m[np.searchsorted(self.times, start_s).clip(0, len(m) - 1)] = True
        return {
            "rms": float(self.rms[m].mean()),
            "bass_ratio": float(self.bass_ratio[m].mean()),
            "onset_rate": float(self.onset[m].mean()),
            "centroid": float(self.centroid[m].mean()),
            "vocal_likelihood": float(np.clip(self.vocal_likelihood_frames[m].mean() * 3.0, 0, 1)),
        }

    def bass_profile_per_bar(self, downbeat_times: np.ndarray) -> list[float]:
        out = []
        for a, b in zip(downbeat_times[:-1], downbeat_times[1:]):
            m = (self.times >= a) & (self.times < b)
            out.append(float(self.bass_ratio[m].mean()) if m.any() else 0.0)
        return out


def raw_energy(stats: dict) -> float:
    """Unnormalized energy blend for a span; normalized across the library later."""
    return (0.4 * stats["rms"] + 0.25 * stats["onset_rate"] / 10.0
            + 0.2 * stats["bass_ratio"] + 0.15 * stats["centroid"] / 4000.0)


def normalize_energies(values: list[float]) -> list[float]:
    """Map raw energies to 0-1 percentile ranks across the library."""
    arr = np.asarray(values)
    if len(arr) < 2:
        return [0.5] * len(arr)
    order = arr.argsort().argsort()
    return (order / (len(arr) - 1)).tolist()
