"""Decode/encode for the renderer, plus environment preflight checks."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from ..analysis.decode import RENDER_SAMPLE_RATE, decode


def decode_stereo(path: Path) -> np.ndarray:
    """Decode to float32 stereo (n, 2) at the render rate."""
    return decode(path, sample_rate=RENDER_SAMPLE_RATE, mono=False)


def encode_mp3(audio: np.ndarray, path: Path, sample_rate: int = RENDER_SAMPLE_RATE,
               title: str = "mil4dy mix") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "f32le", "-ac", "2", "-ar", str(sample_rate), "-i", "pipe:0",
            "-codec:a", "libmp3lame", "-b:a", "320k",
            "-id3v2_version", "3", "-metadata", f"title={title}",
            str(path),
        ],
        stdin=subprocess.PIPE,
    )
    proc.communicate(audio.astype(np.float32).tobytes())
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg mp3 encode failed")


def write_wav(audio: np.ndarray, path: Path, sample_rate: int = RENDER_SAMPLE_RATE,
              bits: int = 24) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if bits == 16:
        # TPDF dither at 1 LSB before quantization
        lsb = 2.0 ** -15
        rng = np.random.default_rng(0)
        dither = (rng.random(audio.shape) + rng.random(audio.shape) - 1.0) * lsb
        sf.write(path, np.clip(audio + dither, -1.0, 1.0), sample_rate, subtype="PCM_16")
    else:
        sf.write(path, audio, sample_rate, subtype="PCM_24")


def doctor() -> list[str]:
    """Return a list of problems with the environment (empty = healthy)."""
    problems = []
    for binary in ("ffmpeg", "ffprobe", "rubberband"):
        if shutil.which(binary) is None:
            problems.append(f"{binary} not found on PATH (brew install {binary})")
    if shutil.which("rubberband"):
        out = subprocess.run(["rubberband", "--version"], capture_output=True, text=True)
        version = (out.stdout or out.stderr).strip().splitlines()[0]
        try:
            if int(version.split(".")[0]) < 3:
                problems.append(f"rubberband >= 3.0 required for the R3 engine (found {version})")
        except ValueError:
            problems.append(f"could not parse rubberband version: {version!r}")
    try:
        import essentia.standard  # noqa: F401
    except Exception as e:  # pragma: no cover
        problems.append(f"essentia unavailable ({e}); key detection will use chroma fallback")
    try:
        from beat_this.inference import Audio2Beats  # noqa: F401
    except Exception as e:  # pragma: no cover
        problems.append(f"beat_this unavailable ({e}); beats will use librosa fallback")
    return problems
