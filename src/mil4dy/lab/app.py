"""FastAPI app: crate listing, pair decisions, overlap renders."""

from __future__ import annotations

import hashlib
import os
import tempfile
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..analysis import analyze_library
from ..planner.pair import plan_pair
from ..render.renderer import render_mix
from ..schemas import MixPlan, TrackAnalysis
from .views import PairRequest, PairResponse, TrackView, decision_view, track_view

WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"
AUDIO_TYPES = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".aiff": "audio/aiff",
    ".ogg": "audio/ogg",
}


class LabState:
    def __init__(self, music_dirs: list[Path], force: bool = False,
                 workers: int | None = None):
        self.music_dirs = music_dirs
        self.force = force
        self.workers = workers
        self.tracks: dict[str, TrackAnalysis] = {}
        self.render_dir = Path(tempfile.gettempdir()) / "mil4dy-lab"
        self.render_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> None:
        recs = analyze_library(self.music_dirs, workers=self.workers, force=self.force)
        self.tracks = {r.fingerprint: r for r in recs}

    def get(self, fid: str) -> TrackAnalysis:
        rec = self.tracks.get(fid)
        if rec is None:
            raise HTTPException(404, f"unknown track {fid}")
        return rec


def create_app(music_dirs: list[Path], force: bool = False,
               workers: int | None = None,
               preloaded: list[TrackAnalysis] | None = None) -> FastAPI:
    state = LabState(music_dirs, force=force, workers=workers)
    if preloaded is not None:
        state.tracks = {r.fingerprint: r for r in preloaded}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if preloaded is None:
            state.load()
        yield

    app = FastAPI(title="mil4dy lab", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def no_cache_ui(request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.endswith((".html", ".js", ".css")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "tracks": len(state.tracks)}

    @app.get("/api/library", response_model=list[TrackView])
    def library() -> list[TrackView]:
        recs = sorted(state.tracks.values(),
                      key=lambda r: ((r.artist or "zzz").lower(), r.title.lower()))
        return [track_view(r) for r in recs]

    @app.get("/api/tracks/{fid}", response_model=TrackView)
    def one_track(fid: str) -> TrackView:
        return track_view(state.get(fid))

    @app.get("/api/tracks/{fid}/audio")
    def track_audio(fid: str) -> FileResponse:
        rec = state.get(fid)
        path = Path(rec.path)
        if not path.is_file():
            raise HTTPException(404, "audio file missing on disk")
        media = AUDIO_TYPES.get(path.suffix.lower(), "application/octet-stream")
        return FileResponse(path, media_type=media, filename=path.name)

    @app.get("/api/pair", response_model=PairResponse)
    def pair_get(a: str, b: str) -> PairResponse:
        return _pair(state, a, b)

    @app.post("/api/pair", response_model=PairResponse)
    def pair_post(body: PairRequest) -> PairResponse:
        return _pair(state, body.a, body.b)

    @app.post("/api/pair/render")
    def pair_render(body: PairRequest) -> FileResponse:
        rec_a, rec_b = state.get(body.a), state.get(body.b)
        try:
            plan, decision = plan_pair(rec_a, rec_b)
            key = hashlib.sha1(
                f"{body.a}:{body.b}:{decision.type}:{decision.length_beats}:"
                f"{decision.a_anchor}:{decision.b_anchor}:"
                f"{decision.out_pulse_shift_s:.4f}:{decision.in_pulse_shift_s:.4f}".encode()
            ).hexdigest()[:16]
            state.render_dir.mkdir(parents=True, exist_ok=True)
            wav = state.render_dir / f"{key}.wav"
            if not wav.exists():
                render_mix(plan, wav, encode=False, end_fade_s=0.4)
            if not wav.is_file():
                raise RuntimeError(f"render wrote nothing at {wav}")
            return FileResponse(wav, media_type="audio/wav", filename=f"{key}.wav")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc

    if WEB_DIST.is_dir():
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="ui")

    return app


def _pair(state: LabState, a: str, b: str) -> PairResponse:
    if a == b:
        raise HTTPException(400, "pick two different tracks")
    rec_a, rec_b = state.get(a), state.get(b)
    plan, decision = plan_pair(rec_a, rec_b)
    blend_start, blend_end = _blend_span(plan)
    return PairResponse(
        a=track_view(rec_a),
        b=track_view(rec_b),
        decision=decision_view(
            decision, plan.target_duration_s, blend_start, blend_end),
    )


def _blend_span(plan: MixPlan) -> tuple[float, float]:
    """Overlap start/end in the rendered window (after outgoing pad)."""
    if len(plan.timeline) >= 2:
        start = float(plan.timeline[1].mix_start_s)
        end = float(plan.timeline[0].mix_end_s)
        if end < start:
            start, end = end, start
        return start, end
    return 0.0, float(plan.target_duration_s)


_ENV_DIRS = "MIL4DY_LAB_DIRS"
_ENV_FORCE = "MIL4DY_LAB_FORCE"
_ENV_WORKERS = "MIL4DY_LAB_WORKERS"


def app_factory() -> FastAPI:
    """Import target for `uvicorn --reload`. Reads crate paths from the env."""
    raw = os.environ.get(_ENV_DIRS, "")
    dirs = [Path(p) for p in raw.split(os.pathsep) if p]
    if not dirs:
        raise RuntimeError(f"{_ENV_DIRS} is empty — start the lab via `mil4dy lab`")
    force = os.environ.get(_ENV_FORCE, "") == "1"
    workers_raw = os.environ.get(_ENV_WORKERS, "")
    workers = int(workers_raw) if workers_raw else None
    return create_app(dirs, force=force, workers=workers)


def serve(app: FastAPI | None = None, host: str = "127.0.0.1", port: int = 8765,
          *, reload: bool = False, music_dirs: list[Path] | None = None,
          force: bool = False, workers: int | None = None) -> None:
    import uvicorn

    url = f"http://{host}:{port}"
    print(f"mil4dy lab → {url}", flush=True)
    if reload:
        print("  watching src/mil4dy (save a .py to restart)", flush=True)
    if not WEB_DIST.is_dir():
        print("  (no web/dist yet — run `npm install && npm run build` in web/ "
              "or `npm run dev` on :5173)", flush=True)
    try:
        webbrowser.open(url)
    except Exception:
        pass

    if reload:
        if not music_dirs:
            raise RuntimeError("reload needs music_dirs")
        os.environ[_ENV_DIRS] = os.pathsep.join(str(p.resolve()) for p in music_dirs)
        os.environ[_ENV_FORCE] = "1" if force else "0"
        if workers is not None:
            os.environ[_ENV_WORKERS] = str(workers)
        else:
            os.environ.pop(_ENV_WORKERS, None)
        watch = Path(__file__).resolve().parents[1]
        uvicorn.run(
            "mil4dy.lab.app:app_factory",
            factory=True,
            host=host,
            port=port,
            log_level="info",
            reload=True,
            reload_dirs=[str(watch)],
        )
        return

    if app is None:
        raise RuntimeError("serve() needs an app when reload is off")
    uvicorn.run(app, host=host, port=port, log_level="info")
