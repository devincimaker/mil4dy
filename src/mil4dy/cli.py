"""mil4dy CLI: analyze / plan / mix / doctor."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Bare alias: `mil4dy DIR [...] --minutes 30 --output mix.mp3` == `mil4dy mix ...`
    if argv and argv[0] not in (
            "analyze", "plan", "mix", "lab", "doctor", "-h", "--help"):
        argv = ["mix", *argv]

    parser = argparse.ArgumentParser(prog="mil4dy",
                                     description="Offline professional DJ mix generator")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p):
        p.add_argument("music_dirs", nargs="+", type=Path, metavar="MUSIC_DIR")
        p.add_argument("--workers", type=int, default=None)
        p.add_argument("--force", action="store_true", help="re-analyze everything")

    p_an = sub.add_parser("analyze", help="analyze tracks and warm the cache")
    add_common(p_an)

    p_plan = sub.add_parser("plan", help="plan a mix (no rendering)")
    add_common(p_plan)
    p_plan.add_argument("--minutes", type=float, default=30.0)
    p_plan.add_argument("--seed", type=int, default=None)
    p_plan.add_argument("--json", type=Path, default=None, help="write plan JSON here")

    p_mix = sub.add_parser("mix", help="analyze, plan, and render a mix")
    add_common(p_mix)
    p_mix.add_argument("--minutes", type=float, default=30.0)
    p_mix.add_argument("--seed", type=int, default=None)
    p_mix.add_argument("--output", type=Path, default=Path("output/mix.mp3"))
    p_mix.add_argument("--loudness", choices=["mix", "streaming"], default="mix",
                       help="mix = -10 LUFS, streaming = -14 LUFS")
    p_mix.add_argument("--wav", action="store_true", help="also write a 24-bit WAV")
    p_mix.add_argument("--debug-transition", type=int, default=None, metavar="N",
                       help="render only transition N (1-based) +/- 8 beats to WAV")

    p_lab = sub.add_parser("lab", help="open the pair-lab UI (crate + two-track mix)")
    add_common(p_lab)
    p_lab.add_argument("--host", default="127.0.0.1")
    p_lab.add_argument("--port", type=int, default=8765)
    p_lab.add_argument(
        "--reload", action=argparse.BooleanOptionalAction, default=True,
        help="restart when src/mil4dy changes (default on; --no-reload to pin)",
    )

    sub.add_parser("doctor", help="check ffmpeg/rubberband/ML dependencies")

    args = parser.parse_args(argv)

    if args.command == "doctor":
        from .render.audio_io import doctor

        problems = doctor()
        for p in problems:
            print(f"  ✗ {p}")
        if not problems:
            print("  ✓ environment healthy")
        sys.exit(1 if any("not found" in p for p in problems) else 0)

    for d in args.music_dirs:
        if not d.is_dir():
            sys.exit(f"not a directory: {d}")

    if args.command == "lab":
        from .lab import run_lab

        run_lab(args.music_dirs, host=args.host, port=args.port,
                force=args.force, workers=args.workers, reload=args.reload)
        return

    from .analysis import analyze_library

    analyses = analyze_library(args.music_dirs, workers=args.workers, force=args.force)
    print(f"library: {len(analyses)} tracks analyzed", file=sys.stderr)
    if args.command == "analyze":
        return

    from .planner import plan_mix

    target_lufs = -10.0
    if args.command == "mix" and args.loudness == "streaming":
        target_lufs = -14.0
    plan = plan_mix(analyses, minutes=args.minutes, seed=args.seed, target_lufs=target_lufs)

    summary = [
        f"{t.id}: {t.artist} - {t.title} [{t.native_bpm:.1f} bpm, {t.camelot}]"
        for t in plan.tracks
    ]
    print("\n".join(summary), file=sys.stderr)
    for tr in plan.transitions:
        print(f"  {tr.from_id}->{tr.to_id}: {tr.type} over {tr.length_beats} beats "
              f"({tr.tempo_ramp.from_bpm:.1f}->{tr.tempo_ramp.to_bpm:.1f} bpm)",
              file=sys.stderr)
    print(f"planned duration: {plan.target_duration_s / 60:.1f} min", file=sys.stderr)

    if args.command == "plan":
        out = args.json
        if out is not None:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(plan.model_dump_json(indent=2))
            print(f"wrote {out}", file=sys.stderr)
        return

    from .render.renderer import render_mix

    render_mix(plan, args.output, wav=args.wav, debug_transition=args.debug_transition)
    if args.debug_transition is not None:
        return

    plan_sidecar = args.output.with_suffix(".json")
    plan_sidecar.write_text(plan.model_dump_json(indent=2))
    print(f"wrote {args.output} and {plan_sidecar}", file=sys.stderr)


if __name__ == "__main__":
    main()
