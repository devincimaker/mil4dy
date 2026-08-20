"""On-disk history of every pair-lab render.

Every Hear and every full-mix write a real WAV under `.mil4dy/history/`.
Favorite is a flag on a take, not a second copy. Unfavorite does not delete.
`LATEST.json` plus `latest-blend.wav` / `latest-mix.wav` point at the newest
files so a human or a bot can find the last generation without the UI.
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


INDEX_NAME = "index.json"
LATEST_NAME = "LATEST.json"
INDEX_VERSION = 2


class TrackIdentity(BaseModel):
    id: str
    artist: str
    title: str


class HistoryRecord(BaseModel):
    id: str
    created_at: str
    outgoing: TrackIdentity
    incoming: TrackIdentity
    decision: dict[str, Any]
    blend: str | None = None
    mix: str | None = None
    blend_filename: str | None = None
    mix_filename: str | None = None
    favorite: bool = False


class HistoryIndex(BaseModel):
    version: int = INDEX_VERSION
    takes: list[HistoryRecord] = Field(default_factory=list)


class HistoryStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def list(self) -> list[HistoryRecord]:
        return list(self._load().takes)

    def favorites(self) -> list[HistoryRecord]:
        return [t for t in self.list() if t.favorite]

    def get(self, tid: str) -> HistoryRecord | None:
        for rec in self.list():
            if rec.id == tid:
                return rec
        return None

    def latest(self) -> HistoryRecord | None:
        takes = self.list()
        return takes[0] if takes else None

    def record_blend(
        self,
        *,
        outgoing: TrackIdentity,
        incoming: TrackIdentity,
        decision: dict[str, Any],
        blend_src: Path,
        blend_filename: str,
    ) -> HistoryRecord:
        tid = uuid.uuid4().hex[:12]
        dest = self.root / tid
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(blend_src, dest / "blend.wav")
        rec = HistoryRecord(
            id=tid,
            created_at=datetime.now(timezone.utc).isoformat(),
            outgoing=outgoing,
            incoming=incoming,
            decision=decision,
            blend=f"{tid}/blend.wav",
            blend_filename=blend_filename,
        )
        idx = self._load()
        idx.takes.insert(0, rec)
        self._save(idx)
        return rec

    def record_or_attach_mix(
        self,
        *,
        take_id: str | None,
        outgoing: TrackIdentity,
        incoming: TrackIdentity,
        decision: dict[str, Any],
        mix_src: Path,
        mix_filename: str,
    ) -> HistoryRecord:
        if take_id:
            attached = self.attach_mix(take_id, mix_src, mix_filename)
            if attached is not None:
                return attached
        match = next(
            (t for t in self.list()
             if t.outgoing.id == outgoing.id and t.incoming.id == incoming.id
             and t.mix is None),
            None,
        )
        if match is not None:
            attached = self.attach_mix(match.id, mix_src, mix_filename)
            if attached is not None:
                return attached
        tid = uuid.uuid4().hex[:12]
        dest = self.root / tid
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(mix_src, dest / "mix.wav")
        rec = HistoryRecord(
            id=tid,
            created_at=datetime.now(timezone.utc).isoformat(),
            outgoing=outgoing,
            incoming=incoming,
            decision=decision,
            mix=f"{tid}/mix.wav",
            mix_filename=mix_filename,
        )
        idx = self._load()
        idx.takes.insert(0, rec)
        self._save(idx)
        return rec

    def attach_mix(self, tid: str, mix_src: Path, mix_filename: str) -> HistoryRecord | None:
        rec = self.get(tid)
        if rec is None:
            return None
        dest = self.root / tid
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(mix_src, dest / "mix.wav")
        rec = rec.model_copy(update={"mix": f"{tid}/mix.wav", "mix_filename": mix_filename})
        self._replace(rec)
        return rec

    def set_favorite(self, tid: str, favorite: bool) -> HistoryRecord | None:
        rec = self.get(tid)
        if rec is None:
            return None
        rec = rec.model_copy(update={"favorite": favorite})
        self._replace(rec)
        return rec

    def remove(self, tid: str) -> HistoryRecord | None:
        rec = self.get(tid)
        if rec is None:
            return None
        idx = self._load()
        idx.takes = [r for r in idx.takes if r.id != tid]
        self._save(idx)
        folder = self.root / tid
        if folder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)
        return rec

    def resolve(self, rel: str) -> Path:
        path = (self.root / rel).resolve()
        root = self.root.resolve()
        if path != root and root not in path.parents:
            raise ValueError("path escapes history dir")
        return path

    def import_legacy_favorites(self, fav_root: Path) -> int:
        """Copy an older favorites/ index into history if we have no takes yet."""
        if self.list():
            return 0
        index = Path(fav_root) / "index.json"
        if not index.is_file():
            return 0
        try:
            data = json.loads(index.read_text())
        except Exception:
            return 0
        imported = 0
        for raw in data.get("favorites") or []:
            src_dir = Path(fav_root) / raw.get("id", "")
            blend_src = src_dir / "blend.wav"
            if not blend_src.is_file():
                continue
            rec = self.record_blend(
                outgoing=TrackIdentity.model_validate(raw["outgoing"]),
                incoming=TrackIdentity.model_validate(raw["incoming"]),
                decision=raw.get("decision") or {},
                blend_src=blend_src,
                blend_filename=raw.get("blend_filename") or "blend.wav",
            )
            mix_src = src_dir / "mix.wav"
            if mix_src.is_file():
                rec = self.attach_mix(
                    rec.id, mix_src, raw.get("mix_filename") or "mix.wav",
                ) or rec
            self.set_favorite(rec.id, True)
            imported += 1
        return imported

    def _replace(self, rec: HistoryRecord) -> None:
        idx = self._load()
        idx.takes = [rec if r.id == rec.id else r for r in idx.takes]
        self._save(idx)

    def _index_path(self) -> Path:
        return self.root / INDEX_NAME

    def _load(self) -> HistoryIndex:
        path = self._index_path()
        if not path.is_file():
            return HistoryIndex()
        try:
            raw = json.loads(path.read_text())
        except Exception:
            return HistoryIndex()
        if "takes" not in raw and "favorites" in raw:
            raw["takes"] = [
                {**item, "favorite": True} for item in raw["favorites"]
            ]
        try:
            return HistoryIndex.model_validate(raw)
        except Exception:
            return HistoryIndex()

    def _save(self, idx: HistoryIndex) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._index_path()
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(idx.model_dump(), indent=2))
        tmp.replace(path)
        self._write_latest(idx.takes)

    def _write_latest(self, takes: list[HistoryRecord]) -> None:
        if not takes:
            return
        newest = takes[0]
        latest_mix = next((t for t in takes if t.mix), None)
        payload = {
            "id": newest.id,
            "created_at": newest.created_at,
            "outgoing": newest.outgoing.model_dump(),
            "incoming": newest.incoming.model_dump(),
            "favorite": newest.favorite,
            "blend_path": str(self.resolve(newest.blend)) if newest.blend else None,
            "mix_path": (
                str(self.resolve(latest_mix.mix))
                if latest_mix is not None and latest_mix.mix
                else None
            ),
        }
        (self.root / LATEST_NAME).write_text(json.dumps(payload, indent=2))
        if newest.blend:
            self._relink("latest-blend.wav", self.resolve(newest.blend))
        if latest_mix is not None and latest_mix.mix:
            self._relink("latest-mix.wav", self.resolve(latest_mix.mix))

    def _relink(self, name: str, target: Path) -> None:
        link = self.root / name
        try:
            if link.is_symlink() or link.is_file():
                link.unlink()
            link.symlink_to(target)
        except OSError:
            shutil.copy2(target, link)
