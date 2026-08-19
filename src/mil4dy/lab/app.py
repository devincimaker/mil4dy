"""FastAPI app: crate listing, pair decisions, overlap renders, mix history."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import threading
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..analysis import analyze_library
from ..planner.pair import PairDecision, plan_pair, plan_pair_full
from ..render.renderer import render_mix
from ..schemas import MixPlan, TrackAnalysis
from .history import HistoryRecord, HistoryStore
from .views import (
    FavoriteRequest,
    HistoryView,
    PairRequest,
    PairResponse,
    RenderView,
    TrackView,
    decision_view,
    history_view,
    identity_view,
    track_view,
)

WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"
AUDIO_TYPES = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".aiff": "audio/aiff",
    ".ogg": "audio/ogg",
}
BLEND_FADE_S = 0.4
MIX_FADE_S = 2.0


class LabState:
    def __init__(self, music_dirs: list[Path], force: bool = False,
                 workers: int | None = None,
                 history_dir: Path | None = None,
                 import_legacy: bool = True):
        self.music_dirs = music_dirs
        self.force = force
        self.workers = workers
        self.tracks: dict[str, TrackAnalysis] = {}
        self.render_dir = Path(tempfile.gettempdir()) / "mil4dy-lab"
        self.render_dir.mkdir(parents=True, exist_ok=True)
        if history_dir is not None:
            self.history_dir = Path(history_dir)
        elif music_dirs:
            self.history_dir = music_dirs[0] / ".mil4dy" / "history"
        else:
            self.history_dir = self.render_dir / "history"
        self.store = HistoryStore(self.history_dir)
        if import_legacy and music_dirs:
            legacy = music_dirs[0] / ".mil4dy" / "favorites"
            if legacy.is_dir() and legacy != self.history_dir:
                n = self.store.import_legacy_favorites(legacy)
                if n:
                    print(f"imported {n} older favorites into history", flush=True)
        self._render_lock = threading.Lock()

    def load(self) -> None:
        recs = analyze_library(self.music_dirs, workers=self.workers, force=self.force)
        self.tracks = {r.fingerprint: r for r in recs}

    def get(self, fid: str) -> TrackAnalysis:
        rec = self.tracks.get(fid)
        if rec is None:
            raise HTTPException(404, f"unknown track {fid}")
        return rec

    def get_take(self, tid: str) -> HistoryRecord:
        rec = self.store.get(tid)
        if rec is None:
            raise HTTPException(404, "unknown take")
        return rec


def create_app(music_dirs: list[Path], force: bool = False,
               workers: int | None = None,
               preloaded: list[TrackAnalysis] | None = None,
               history_dir: Path | None = None,
               favorites_dir: Path | None = None) -> FastAPI:
    explicit_dir = history_dir or favorites_dir
    state = LabState(
        music_dirs, force=force, workers=workers,
        history_dir=explicit_dir,
        import_legacy=explicit_dir is None,
    )
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
        latest = state.store.latest()
        return {
            "ok": True,
            "tracks": len(state.tracks),
            "history": len(state.store.list()),
            "latest_id": latest.id if latest else None,
        }

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

    @app.post("/api/pair/render", response_model=RenderView)
    def pair_render(body: PairRequest) -> RenderView:
        return _render_pair(state, body.a, body.b, kind="blend")

    @app.post("/api/pair/mix", response_model=RenderView)
    def pair_mix(body: PairRequest) -> RenderView:
        return _render_pair(state, body.a, body.b, kind="mix", take_id=body.take_id)

    @app.get("/api/history", response_model=list[HistoryView])
    def list_history() -> list[HistoryView]:
        return [_take_payload(state, rec) for rec in state.store.list()]

    @app.get("/api/history/latest")
    def latest_take() -> dict:
        rec = state.store.latest()
        if rec is None:
            raise HTTPException(404, "no renders yet")
        payload = _take_payload(state, rec)
        return {
            **payload.model_dump(),
            "latest_json": str(state.store.root / "LATEST.json"),
        }

    @app.get("/api/history/{tid}/blend")
    def history_blend(tid: str, download: bool = False) -> FileResponse:
        return _serve_take_audio(state, tid, "blend", download)

    @app.get("/api/history/{tid}/mix")
    def history_mix(tid: str, download: bool = False) -> FileResponse:
        return _serve_take_audio(state, tid, "mix", download)

    @app.post("/api/history/{tid}/favorite", response_model=HistoryView)
    def star_take(tid: str, favorite: bool = True) -> HistoryView:
        rec = state.store.set_favorite(tid, favorite)
        if rec is None:
            raise HTTPException(404, "unknown take")
        return _take_payload(state, rec)

    @app.delete("/api/history/{tid}")
    def delete_take(tid: str) -> dict:
        rec = state.store.remove(tid)
        if rec is None:
            raise HTTPException(404, "unknown take")
        return {"ok": True, "id": tid}

    @app.get("/api/favorites", response_model=list[HistoryView])
    def list_favorites() -> list[HistoryView]:
        return [_take_payload(state, rec) for rec in state.store.favorites()]

    @app.post("/api/favorites", response_model=HistoryView)
    def create_favorite(body: FavoriteRequest) -> HistoryView:
        tid = body.take_id or body.blend_id
        if not tid:
            raise HTTPException(400, "take_id or blend_id required")
        rec = state.store.get(tid)
        if rec is None:
            raise HTTPException(404, "unknown take — Hear the blend first")
        rec = state.store.set_favorite(tid, body.favorite)
        if rec is None:
            raise HTTPException(404, "unknown take")
        return _take_payload(state, rec)

    @app.post("/api/favorites/{tid}/mix", response_model=HistoryView)
    def attach_favorite_mix(tid: str) -> HistoryView:
        rec = state.store.get(tid)
        if rec is None:
            raise HTTPException(404, "unknown take")
        if rec.mix is None:
            raise HTTPException(400, "this take has no full mix yet — download the mix first")
        return _take_payload(state, rec)

    @app.delete("/api/favorites/{tid}", response_model=HistoryView)
    def unfavorite(tid: str) -> HistoryView:
        rec = state.store.set_favorite(tid, False)
        if rec is None:
            raise HTTPException(404, "unknown take")
        return _take_payload(state, rec)

    @app.get("/api/favorites/{tid}/blend")
    def favorite_blend(tid: str, download: bool = False) -> FileResponse:
        return _serve_take_audio(state, tid, "blend", download)

    @app.get("/api/favorites/{tid}/mix")
    def favorite_mix(tid: str, download: bool = False) -> FileResponse:
        return _serve_take_audio(state, tid, "mix", download)

    @app.get("/api/renders/{tid}")
    def serve_render(tid: str, download: bool = False) -> FileResponse:
        rec = state.get_take(tid)
        kind = "mix" if rec.blend is None and rec.mix else "blend"
        return _serve_take_audio(state, tid, kind, download)

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


def _render_pair(state: LabState, a: str, b: str, *, kind: str,
                 take_id: str | None = None) -> RenderView:
    if a == b:
        raise HTTPException(400, "pick two different tracks")
    rec_a, rec_b = state.get(a), state.get(b)
    try:
        window_plan, decision = plan_pair(rec_a, rec_b)
        plan = window_plan if kind == "blend" else plan_pair_full(rec_a, rec_b)[0]
        key = _decision_key(a, b, decision, kind)
        state.render_dir.mkdir(parents=True, exist_ok=True)
        wav = state.render_dir / f"{key}.wav"
        fade = BLEND_FADE_S if kind == "blend" else MIX_FADE_S
        with state._render_lock:
            if not wav.exists():
                render_mix(plan, wav, encode=False, end_fade_s=fade)
            if not wav.is_file():
                raise RuntimeError(f"render wrote nothing at {wav}")
        filename = _render_filename(rec_a, rec_b, kind)
        blend_start, blend_end = _blend_span(window_plan)
        dumped = decision_view(
            decision, window_plan.target_duration_s, blend_start, blend_end,
        ).model_dump()
        if kind == "blend":
            take = state.store.record_blend(
                outgoing=identity_view(rec_a),
                incoming=identity_view(rec_b),
                decision=dumped,
                blend_src=wav,
                blend_filename=filename,
            )
            print(f"saved blend → {state.store.resolve(take.blend)}", flush=True)
        else:
            take = state.store.record_or_attach_mix(
                take_id=take_id,
                outgoing=identity_view(rec_a),
                incoming=identity_view(rec_b),
                decision=dumped,
                mix_src=wav,
                mix_filename=filename,
            )
            if take.mix:
                print(f"saved mix → {state.store.resolve(take.mix)}", flush=True)
        return _render_payload(state, take, kind, filename)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc


def _render_payload(state: LabState, take: HistoryRecord, kind: str,
                    filename: str) -> RenderView:
    view = _take_payload(state, take)
    url = view.mix_url if kind == "mix" else view.blend_url
    dl = view.mix_download_url if kind == "mix" else view.blend_download_url
    if not url or not dl:
        raise HTTPException(500, "take is missing the rendered file")
    return RenderView(
        id=take.id,
        kind=kind,  # type: ignore[arg-type]
        filename=filename,
        url=url,
        download_url=dl,
        outgoing=take.outgoing,
        incoming=take.incoming,
        decision=view.decision,
        take_id=take.id,
        favorite=take.favorite,
        blend_path=view.blend_path,
        mix_path=view.mix_path,
    )


def _decision_key(a: str, b: str, decision: PairDecision, kind: str) -> str:
    raw = (
        f"{kind}:{a}:{b}:{decision.type}:{decision.length_beats}:"
        f"{decision.a_anchor}:{decision.b_anchor}:"
        f"{decision.out_pulse_shift_s:.4f}:{decision.in_pulse_shift_s:.4f}"
    )
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^\w]+", "-", text.strip(), flags=re.UNICODE).strip("-")
    return (cleaned or "track")[:80]


def _render_filename(a: TrackAnalysis, b: TrackAnalysis, kind: str) -> str:
    left = _slug(f"{a.artist or ''} {a.title or Path(a.path).stem}")
    right = _slug(f"{b.artist or ''} {b.title or Path(b.path).stem}")
    return f"{left}__{right}-{kind}.wav"


def _audio_file(path: Path, filename: str, *, download: bool) -> FileResponse:
    return FileResponse(
        path,
        media_type="audio/wav",
        filename=filename,
        content_disposition_type="attachment" if download else "inline",
    )


def _take_payload(state: LabState, rec: HistoryRecord) -> HistoryView:
    blend = state.store.resolve(rec.blend) if rec.blend else None
    mix = state.store.resolve(rec.mix) if rec.mix else None
    return history_view(
        rec,
        blend_abs=str(blend) if blend is not None else None,
        mix_abs=str(mix) if mix is not None else None,
    )


def _serve_take_audio(state: LabState, tid: str, kind: str, download: bool) -> FileResponse:
    rec = state.get_take(tid)
    rel = rec.blend if kind == "blend" else rec.mix
    name = rec.blend_filename if kind == "blend" else rec.mix_filename
    if not rel:
        raise HTTPException(404, f"this take has no {kind} file")
    path = state.store.resolve(rel)
    if not path.is_file():
        raise HTTPException(404, f"{kind} file is missing")
    return _audio_file(path, name or f"{tid}-{kind}.wav", download=download)


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
