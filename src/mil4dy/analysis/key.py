"""Key detection: essentia EDMA profile primary, chroma-template fallback."""

from __future__ import annotations

import numpy as np

# Camelot wheel: (pitch class, minor?) -> code. 8A = A minor, 8B = C major.
_NOTE_PC = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5,
            "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}

# Minor keys around the wheel starting at 1A = Ab minor; major: 1B = B major.
_MINOR_WHEEL = ["Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E", "B", "F#", "C#"]
_MAJOR_WHEEL = ["B", "F#", "C#", "Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E"]


def to_camelot(key: str, scale: str) -> str:
    key = key.strip()
    pc = _NOTE_PC.get(key)
    if pc is None:
        return ""
    wheel = _MINOR_WHEEL if scale.lower() == "minor" else _MAJOR_WHEEL
    for i, name in enumerate(wheel):
        if _NOTE_PC[name] == pc:
            return f"{i + 1}{'A' if scale.lower() == 'minor' else 'B'}"
    return ""


def detect_key(y_44k: np.ndarray) -> tuple[str, str, str, float, str]:
    """Returns (key, scale, camelot, confidence, engine). Input: mono f32 @44.1k."""
    try:
        import essentia.standard as es

        key, scale, strength = es.KeyExtractor(profileType="edma")(y_44k)
        return key, scale, to_camelot(key, scale), float(strength), "essentia-edma"
    except Exception:
        pass
    return _chroma_key(y_44k)


# Temperley profiles (better than Krumhansl for popular music)
_MAJOR_PROFILE = np.array([5.0, 2.0, 3.5, 2.0, 4.5, 4.0, 2.0, 4.5, 2.0, 3.5, 1.5, 4.0])
_MINOR_PROFILE = np.array([5.0, 2.0, 3.5, 4.5, 2.0, 4.0, 2.0, 4.5, 3.5, 2.0, 1.5, 4.0])
_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _chroma_key(y: np.ndarray, sr: int = 44100) -> tuple[str, str, str, float, str]:
    import librosa

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
    scores: list[tuple[float, str, str]] = []
    for shift in range(12):
        rotated = np.roll(chroma, -shift)
        for profile, scale in ((_MAJOR_PROFILE, "major"), (_MINOR_PROFILE, "minor")):
            r = np.corrcoef(rotated, profile)[0, 1]
            scores.append((r, _NOTE_NAMES[shift], scale))
    scores.sort(reverse=True)
    best, second = scores[0], scores[1]
    confidence = float(np.clip(1.0 - second[0] / best[0], 0.0, 1.0)) if best[0] > 0 else 0.0
    key, scale = best[1], best[2]
    return key, scale, to_camelot(key, scale), confidence, "chroma-fallback"
