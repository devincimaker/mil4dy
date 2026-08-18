"""Local pair-lab HTTP server."""

from __future__ import annotations

from pathlib import Path


def run_lab(music_dirs: list[Path], host: str = "127.0.0.1", port: int = 8765,
            force: bool = False, workers: int | None = None) -> None:
    from .app import create_app, serve

    app = create_app(music_dirs, force=force, workers=workers)
    serve(app, host=host, port=port)
