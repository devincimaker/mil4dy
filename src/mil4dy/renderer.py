from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def render_mix(plan: dict[str, Any], output_path: Path) -> None:
    tracks = plan["tracks"]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for track in tracks:
        command.extend(["-i", track["path"]])

    filters: list[str] = []
    for index, track in enumerate(tracks):
        fade_in = ",afade=t=in:st=0:d=2" if index == 0 else ""
        filters.append(
            f"[{index}:a:0]"
            f"atrim=start={track['cue_in']}:end={track['cue_out']},"
            "asetpts=PTS-STARTPTS,"
            f"atempo={track['tempo_factor']},"
            "loudnorm=I=-14:TP=-1.5:LRA=11,"
            "aresample=44100,"
            "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo"
            f"{fade_in}[a{index}]"
        )

    current = "a0"
    crossfade = plan["crossfade_seconds"]
    for index in range(1, len(tracks)):
        output_label = f"mix{index}"
        filters.append(
            f"[{current}][a{index}]"
            f"acrossfade=d={crossfade}:c1=qsin:c2=qsin[{output_label}]"
        )
        current = output_label

    duration = float(plan["duration_seconds"])
    fade_start = max(duration - 8.0, 0.0)
    filters.append(
        f"[{current}]atrim=duration={duration},"
        f"afade=t=out:st={fade_start}:d=8,"
        "alimiter=limit=0.85:level=false[final]"
    )

    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[final]",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "320k",
            "-map_metadata",
            "-1",
            "-id3v2_version",
            "3",
            "-metadata",
            "title=mil4dy mix",
            str(output_path),
        ]
    )
    subprocess.run(command, check=True)


def output_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())
