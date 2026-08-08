from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from .analysis import load_library
from .planner import plan_mix
from .renderer import output_duration, render_mix


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mil4dy",
        description="Analyze an MP3 folder and render one offline DJ mix.",
    )
    parser.add_argument("music_dir", type=Path, help="Folder containing MP3 files")
    parser.add_argument(
        "--minutes", type=float, default=30.0, help="Mix duration in minutes (default: 30)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/mix.mp3"),
        help="Output MP3 path (default: output/mix.mp3)",
    )
    return parser


def run(args: argparse.Namespace) -> None:
    if args.minutes <= 0:
        raise ValueError("--minutes must be greater than zero")
    music_dir = args.music_dir.expanduser().resolve()
    if not music_dir.is_dir():
        raise ValueError(f"Music directory does not exist: {music_dir}")
    for executable in ("ffmpeg", "ffprobe"):
        if shutil.which(executable) is None:
            raise ValueError(f"Required executable is not installed: {executable}")

    output = args.output.expanduser().resolve()
    cache_path = Path.cwd() / ".mil4dy" / "analysis.json"
    records = load_library(music_dir, cache_path)
    plan = plan_mix(records, music_dir, args.minutes * 60.0)

    plan_path = output.with_suffix(".json")
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")

    print(
        f"Planned {len(plan['tracks'])} tracks at {plan['target_bpm']} BPM "
        f"for {args.minutes:g} minutes"
    )
    for index, track in enumerate(plan["tracks"], start=1):
        print(
            f"  {index:02d}. {track['artist']} — {track['title']} "
            f"({track['bpm']:.1f} BPM, {track['key']}, energy {track['energy']:.2f})"
        )

    print(f"Rendering {output}")
    render_mix(plan, output)
    rendered_duration = output_duration(output)
    print(f"Created {output} ({rendered_duration / 60:.2f} minutes)")
    print(f"Plan: {plan_path}")


def main() -> None:
    try:
        run(_parser().parse_args())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"mil4dy: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
