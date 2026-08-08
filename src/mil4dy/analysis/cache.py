"""Per-track analysis cache, keyed by content fingerprint."""

from __future__ import annotations

from pathlib import Path

from ..schemas import ANALYSIS_VERSION, TrackAnalysis


class AnalysisCache:
    def __init__(self, root: Path):
        self.dir = root / ".mil4dy" / "cache" / f"v{ANALYSIS_VERSION}"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, fp: str) -> Path:
        return self.dir / f"{fp}.json"

    def get(self, fp: str) -> TrackAnalysis | None:
        p = self._path(fp)
        if not p.exists():
            return None
        try:
            rec = TrackAnalysis.model_validate_json(p.read_text())
        except Exception:
            return None
        if rec.analysis_version != ANALYSIS_VERSION:
            return None
        return rec

    def put(self, rec: TrackAnalysis) -> None:
        self._path(rec.fingerprint).write_text(rec.model_dump_json())
