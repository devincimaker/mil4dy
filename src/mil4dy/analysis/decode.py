"""Track discovery, ffprobe metadata, ffmpeg decoding, content fingerprinting."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ANALYSIS_SAMPLE_RATE = 22050
RENDER_SAMPLE_RATE = 44100

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".flac", ".wav", ".aiff", ".ogg"}


def discover_tracks(music_dirs: list[Path]) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for d in music_dirs:
        for p in sorted(d.rglob("*")):
            if p.suffix.lower() in AUDIO_EXTENSIONS and p.is_file():
                rp = p.resolve()
                if rp not in seen:
                    seen.add(rp)
                    paths.append(rp)
    return paths


def fingerprint(path: Path) -> str:
    """Content fingerprint: sha1(size || first 64KiB || last 64KiB).

    Stable across renames/moves so a reorganized library keeps its cache.
    """
    size = path.stat().st_size
    h = hashlib.sha1(str(size).encode())
    with open(path, "rb") as f:
        h.update(f.read(65536))
        if size > 65536:
            f.seek(max(size - 65536, 0))
            h.update(f.read(65536))
    return h.hexdigest()


@dataclass
class TrackTags:
    title: str
    artist: str
    album: str
    genre: str
    duration: float


def probe(path: Path) -> TrackTags:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration:format_tags=title,artist,album,genre",
            "-of", "json", str(path),
        ],
        capture_output=True, check=True,
    ).stdout
    fmt = json.loads(out).get("format", {})
    tags = {k.lower(): v for k, v in fmt.get("tags", {}).items()}
    title = tags.get("title", "").strip()
    artist = tags.get("artist", "").strip()
    if not title:
        # Filename fallbacks: "<artist> - <title>" or "<id>-<artist>-<title>"
        stem = path.stem
        if " - " in stem:
            artist_guess, _, title = stem.partition(" - ")
            artist = artist or artist_guess.strip()
            title = title.strip()
        elif stem.count("-") >= 2 and stem.split("-")[0].isdigit():
            parts = stem.split("-")
            artist = artist or parts[1].strip()
            title = "-".join(parts[2:]).strip()
        else:
            title = stem
    return TrackTags(
        title=title,
        artist=artist,
        album=tags.get("album", "").strip(),
        genre=tags.get("genre", "").strip(),
        duration=float(fmt.get("duration", 0.0)),
    )


def decode(path: Path, sample_rate: int = ANALYSIS_SAMPLE_RATE, mono: bool = True) -> np.ndarray:
    """Decode any audio file to float32 via ffmpeg.

    Returns shape (n,) when mono, else (n, 2).
    """
    channels = 1 if mono else 2
    raw = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-i", str(path),
            "-f", "f32le", "-ac", str(channels), "-ar", str(sample_rate), "pipe:1",
        ],
        capture_output=True, check=True,
    ).stdout
    audio = np.frombuffer(raw, dtype=np.float32)
    if not mono:
        audio = audio.reshape(-1, 2)
    return audio
