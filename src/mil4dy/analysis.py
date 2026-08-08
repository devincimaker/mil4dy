from __future__ import annotations

import html
import json
import os
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import librosa
import numpy as np


ANALYSIS_VERSION = 1
SAMPLE_RATE = 22_050
HOP_LENGTH = 512

MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
)
MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
)
KEY_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def discover_tracks(music_dir: Path) -> list[Path]:
    return sorted(
        (path.resolve() for path in music_dir.rglob("*") if path.suffix.lower() == ".mp3"),
        key=lambda path: str(path).lower(),
    )


def _run_json(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def _probe(path: Path) -> tuple[float, dict[str, str]]:
    payload = _run_json(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:format_tags=title,artist,album,genre",
            "-of",
            "json",
            str(path),
        ]
    )
    format_data = payload.get("format", {})
    duration = float(format_data.get("duration", 0.0))
    tags = {str(key).lower(): str(value) for key, value in format_data.get("tags", {}).items()}
    return duration, tags


def _decode_mono(path: Path) -> np.ndarray:
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-vn",
            "-sn",
            "-dn",
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            "-f",
            "f32le",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    )
    audio = np.frombuffer(result.stdout, dtype="<f4")
    if audio.size == 0:
        raise ValueError("decoded audio is empty")
    return audio


def _fallback_identity(path: Path) -> tuple[str, str]:
    stem = html.unescape(path.stem.replace("_amp_", "&"))
    parts = stem.split("-", 2)
    if len(parts) == 3 and parts[0].isdigit():
        return parts[2].strip(), parts[1].strip()
    return stem, "Unknown Artist"


def _estimate_key(chroma: np.ndarray) -> tuple[str, float]:
    chroma_mean = np.median(chroma, axis=1)
    norm = float(np.linalg.norm(chroma_mean))
    if norm == 0:
        return "C", 0.0
    chroma_mean = chroma_mean / norm

    candidates: list[tuple[float, str]] = []
    for tonic, name in enumerate(KEY_NAMES):
        major = np.roll(MAJOR_PROFILE, tonic)
        minor = np.roll(MINOR_PROFILE, tonic)
        major_score = float(np.dot(chroma_mean, major / np.linalg.norm(major)))
        minor_score = float(np.dot(chroma_mean, minor / np.linalg.norm(minor)))
        candidates.append((major_score, name))
        candidates.append((minor_score, f"{name}m"))

    candidates.sort(reverse=True)
    best_score, best_key = candidates[0]
    second_score = candidates[1][0]
    confidence = float(np.clip((best_score - second_score) * 8.0, 0.0, 1.0))
    return best_key, confidence


def analyze_track(path_string: str) -> dict[str, Any]:
    path = Path(path_string)
    stat = path.stat()
    duration, tags = _probe(path)
    audio = _decode_mono(path)

    onset_envelope = librosa.onset.onset_strength(
        y=audio, sr=SAMPLE_RATE, hop_length=HOP_LENGTH
    )
    tempo_value, beat_frames = librosa.beat.beat_track(
        onset_envelope=onset_envelope,
        sr=SAMPLE_RATE,
        hop_length=HOP_LENGTH,
    )
    tempo = float(np.asarray(tempo_value).reshape(-1)[0])
    beat_times = librosa.frames_to_time(
        beat_frames, sr=SAMPLE_RATE, hop_length=HOP_LENGTH
    )

    magnitude = np.abs(librosa.stft(audio, n_fft=2048, hop_length=HOP_LENGTH))
    power = magnitude**2
    rms = librosa.feature.rms(S=magnitude, frame_length=2048, hop_length=HOP_LENGTH)[0]
    rms_db = librosa.amplitude_to_db(np.maximum(rms, 1e-10), ref=1.0)
    centroid = librosa.feature.spectral_centroid(
        S=magnitude, sr=SAMPLE_RATE
    )[0]
    chroma = librosa.feature.chroma_stft(
        S=power, sr=SAMPLE_RATE, hop_length=HOP_LENGTH
    )
    key, key_confidence = _estimate_key(chroma)

    onset_frames = librosa.onset.onset_detect(
        onset_envelope=onset_envelope,
        sr=SAMPLE_RATE,
        hop_length=HOP_LENGTH,
    )
    frequencies = librosa.fft_frequencies(sr=SAMPLE_RATE, n_fft=2048)
    total_power = float(np.sum(power))
    bass_power = float(np.sum(power[frequencies < 250]))

    fallback_title, fallback_artist = _fallback_identity(path)
    return {
        "path": str(path),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "title": tags.get("title", fallback_title),
        "artist": tags.get("artist", fallback_artist),
        "album": tags.get("album", ""),
        "genre": tags.get("genre", ""),
        "duration": duration,
        "bpm": tempo,
        "beats": [round(float(value), 6) for value in beat_times],
        "key": key,
        "key_confidence": key_confidence,
        "features": {
            "loudness_db": float(np.median(rms_db)),
            "onset_rate": float(len(onset_frames) / max(duration, 1.0)),
            "onset_strength": float(np.percentile(onset_envelope, 75)),
            "brightness": float(np.median(centroid) / (SAMPLE_RATE / 2)),
            "bass_ratio": bass_power / max(total_power, 1e-12),
        },
    }


def _write_cache(cache_path: Path, tracks: dict[str, dict[str, Any]]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {"analysis_version": ANALYSIS_VERSION, "tracks": tracks},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(cache_path)


def _normalized_values(records: list[dict[str, Any]], feature: str) -> np.ndarray:
    values = np.array([record["features"][feature] for record in records], dtype=float)
    lower, upper = np.percentile(values, [10, 90])
    if upper <= lower:
        return np.full(values.shape, 0.5)
    return np.clip((values - lower) / (upper - lower), 0.0, 1.0)


def _add_energy(records: list[dict[str, Any]]) -> None:
    loudness = _normalized_values(records, "loudness_db")
    onset_rate = _normalized_values(records, "onset_rate")
    onset_strength = _normalized_values(records, "onset_strength")
    brightness = _normalized_values(records, "brightness")
    bass = _normalized_values(records, "bass_ratio")

    tempos = np.array([record["bpm"] for record in records], dtype=float)
    tempo_lower, tempo_upper = np.percentile(tempos, [10, 90])
    tempo = np.clip(
        (tempos - tempo_lower) / max(tempo_upper - tempo_lower, 1e-9), 0.0, 1.0
    )

    energies = (
        0.25 * loudness
        + 0.25 * onset_rate
        + 0.20 * onset_strength
        + 0.15 * brightness
        + 0.10 * bass
        + 0.05 * tempo
    )
    for record, energy in zip(records, energies, strict=True):
        record["energy"] = round(float(energy), 4)


def load_library(music_dir: Path, cache_path: Path) -> list[dict[str, Any]]:
    paths = discover_tracks(music_dir)
    if not paths:
        raise ValueError(f"No MP3 files found in {music_dir}")

    cache: dict[str, Any] = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cache = {}
    cached_tracks = (
        cache.get("tracks", {})
        if cache.get("analysis_version") == ANALYSIS_VERSION
        else {}
    )

    current: dict[str, dict[str, Any]] = {}
    pending: list[Path] = []
    for path in paths:
        stat = path.stat()
        cached = cached_tracks.get(str(path))
        if (
            cached
            and cached.get("size") == stat.st_size
            and cached.get("mtime_ns") == stat.st_mtime_ns
        ):
            current[str(path)] = cached
        else:
            pending.append(path)

    print(f"Found {len(paths)} MP3s: {len(current)} cached, {len(pending)} to analyze")
    failures: list[str] = []
    if pending:
        worker_count = min(4, len(pending), os.cpu_count() or 1)
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(analyze_track, str(path)): path for path in pending
            }
            completed = 0
            for future in as_completed(futures):
                path = futures[future]
                try:
                    current[str(path)] = future.result()
                except Exception as error:  # keep successful track analysis resumable
                    failures.append(f"{path.name}: {error}")
                completed += 1
                print(f"Analyzed {completed}/{len(pending)}: {path.name}")
                _write_cache(cache_path, current)

    if failures:
        print("Skipped tracks that could not be analyzed:")
        for failure in failures:
            print(f"  - {failure}")
    records = [current[str(path)] for path in paths if str(path) in current]
    if len(records) < 2:
        raise ValueError("At least two successfully analyzed tracks are required")
    _add_energy(records)
    return records

