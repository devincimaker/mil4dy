from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any


MAX_STRETCH = 0.06
PHRASE_BEATS = 32
MAX_TRACK_OUTPUT_SECONDS = 240.0

PITCH_CLASS = {
    "C": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
}


def _target_bpm(records: list[dict[str, Any]]) -> float:
    candidates = [round(record["bpm"], 1) for record in records if record["bpm"] > 0]
    best_target = candidates[0]
    best_score = (-1, float("-inf"))
    for target in candidates:
        compatible = [
            record
            for record in records
            if abs(target / record["bpm"] - 1.0) <= MAX_STRETCH
        ]
        average_stretch = sum(
            abs(target / record["bpm"] - 1.0) for record in compatible
        ) / max(len(compatible), 1)
        score = (len(compatible), -average_stretch)
        if score > best_score:
            best_score = score
            best_target = target
    return round(best_target)


def _parse_key(key: str) -> tuple[int, bool] | None:
    minor = key.endswith("m")
    root = key[:-1] if minor else key
    if root not in PITCH_CLASS:
        return None
    return PITCH_CLASS[root], minor


def _key_compatibility(left: str, right: str) -> float:
    first = _parse_key(left)
    second = _parse_key(right)
    if first is None or second is None:
        return 0.5
    if first == second:
        return 1.0
    first_root, first_minor = first
    second_root, second_minor = second
    if first_minor != second_minor:
        major_root = first_root if not first_minor else second_root
        minor_root = first_root if first_minor else second_root
        if (minor_root + 3) % 12 == major_root:
            return 0.95
    if first_minor == second_minor and (first_root - second_root) % 12 in {5, 7}:
        return 0.85
    if first_root == second_root:
        return 0.7
    return 0.25


def _energy_target(progress: float) -> float:
    progress = min(max(progress, 0.0), 1.0)
    if progress <= 0.72:
        return 0.25 + (0.80 - 0.25) * (progress / 0.72)
    return 0.80 + (0.55 - 0.80) * ((progress - 0.72) / 0.28)


def _segment(record: dict[str, Any], target_bpm: float) -> dict[str, Any] | None:
    bpm = float(record["bpm"])
    tempo_factor = target_bpm / bpm
    beats = record["beats"]
    if len(beats) <= PHRASE_BEATS * 2:
        return None

    cue_in = float(beats[0])
    desired_source_end = cue_in + MAX_TRACK_OUTPUT_SECONDS * tempo_factor
    last_usable = 0
    for index, beat in enumerate(beats):
        if beat <= desired_source_end and beat < record["duration"] - 0.1:
            last_usable = index
        else:
            break
    cue_index = (last_usable // PHRASE_BEATS) * PHRASE_BEATS
    if cue_index < PHRASE_BEATS * 2:
        return None
    cue_out = float(beats[cue_index])
    output_duration = (cue_out - cue_in) / tempo_factor
    return {
        "path": record["path"],
        "title": record["title"],
        "artist": record["artist"],
        "genre": record["genre"],
        "bpm": round(bpm, 3),
        "target_bpm": target_bpm,
        "tempo_factor": round(tempo_factor, 8),
        "key": record["key"],
        "key_confidence": round(record["key_confidence"], 4),
        "energy": record["energy"],
        "cue_in": round(cue_in, 6),
        "cue_out": round(cue_out, 6),
        "output_duration": round(output_duration, 3),
    }


def plan_mix(
    records: list[dict[str, Any]], music_dir: Path, duration_seconds: float
) -> dict[str, Any]:
    target_bpm = _target_bpm(records)
    crossfade_seconds = PHRASE_BEATS * 60.0 / target_bpm
    candidates = []
    for record in records:
        if abs(target_bpm / record["bpm"] - 1.0) <= MAX_STRETCH:
            segment = _segment(record, target_bpm)
            if segment and segment["output_duration"] > crossfade_seconds * 2:
                candidates.append(segment)
    if len(candidates) < 2:
        raise ValueError("The library does not contain enough tempo-compatible tracks")

    selected: list[dict[str, Any]] = []
    elapsed = 0.0
    remaining = list(candidates)
    while elapsed < duration_seconds and remaining:
        progress = elapsed / duration_seconds
        desired_energy = _energy_target(progress)
        previous = selected[-1] if selected else None

        def candidate_score(candidate: dict[str, Any]) -> tuple[float, str]:
            energy_score = 1.0 - abs(candidate["energy"] - desired_energy)
            key_score = (
                _key_compatibility(previous["key"], candidate["key"])
                if previous
                else 0.5
            )
            stretch_score = 1.0 - abs(candidate["tempo_factor"] - 1.0) / MAX_STRETCH
            duration_score = min(candidate["output_duration"] / 180.0, 1.0)
            artist_penalty = (
                0.5
                if previous
                and candidate["artist"].casefold() == previous["artist"].casefold()
                else 0.0
            )
            score = (
                0.55 * energy_score
                + 0.25 * key_score
                + 0.15 * stretch_score
                + 0.05 * duration_score
                - artist_penalty
            )
            return score, candidate["path"]

        chosen = max(remaining, key=candidate_score)
        chosen = dict(chosen)
        chosen["energy_target"] = round(desired_energy, 4)
        chosen["starts_at"] = round(elapsed, 3)
        selected.append(chosen)
        remaining.remove(next(item for item in remaining if item["path"] == chosen["path"]))
        elapsed += chosen["output_duration"]
        if len(selected) > 1:
            elapsed -= crossfade_seconds

    if elapsed < duration_seconds:
        raise ValueError(
            f"Compatible tracks only cover {elapsed / 60:.1f} of the requested "
            f"{duration_seconds / 60:.1f} minutes"
        )

    return {
        "version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "music_dir": str(music_dir.resolve()),
        "duration_seconds": round(duration_seconds, 3),
        "target_bpm": target_bpm,
        "crossfade_beats": PHRASE_BEATS,
        "crossfade_seconds": round(crossfade_seconds, 6),
        "tracks": selected,
    }

