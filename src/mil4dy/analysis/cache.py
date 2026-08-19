"""Per-track analysis cache, keyed by content fingerprint."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..schemas import ANALYSIS_VERSION, TrackAnalysis
from .beats import (
    beat_confidence,
    fit_pulse,
    phrase_grid,
    rebuild_uniform_grid,
    score_intro,
)


def migrate_analysis(rec: TrackAnalysis) -> TrackAnalysis:
    """Rewrite BPM + beat grid from a pulse fit. No audio, no beat_this."""
    if rec.analysis_version >= ANALYSIS_VERSION:
        return rec
    raw = np.asarray(rec.beat_times, dtype=float)
    downs = np.asarray(rec.downbeat_times, dtype=float)
    fit = fit_pulse(raw)
    if not fit.ok:
        return rec.model_copy(update={"analysis_version": ANALYSIS_VERSION})
    conf = beat_confidence(raw, rec.duration, fit.bpm)
    intro_bpm, intro_ok = score_intro(raw, rec.duration, fit.bpm)
    beats, new_downs = rebuild_uniform_grid(
        rec.duration, fit.bpm, downs, phase=fit.phase)
    phrases = phrase_grid(new_downs)
    return rec.model_copy(update={
        "analysis_version": ANALYSIS_VERSION,
        "bpm": float(fit.bpm),
        "beat_times": np.round(beats, 5).tolist(),
        "downbeat_times": np.round(new_downs, 5).tolist(),
        "phrase_starts": np.round(phrases, 5).tolist(),
        "downbeat_confidence": conf,
        "intro_bpm": float(intro_bpm),
        "intro_grid_ok": intro_ok,
    })


class AnalysisCache:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.dir = self.root / ".mil4dy" / "cache" / f"v{ANALYSIS_VERSION}"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, fp: str) -> Path:
        return self.dir / f"{fp}.json"

    def _load(self, path: Path) -> TrackAnalysis | None:
        try:
            return TrackAnalysis.model_validate_json(path.read_text())
        except Exception:
            return None

    def get(self, fp: str) -> TrackAnalysis | None:
        p = self._path(fp)
        if p.exists():
            rec = self._load(p)
            if rec is None:
                return None
            if rec.analysis_version == ANALYSIS_VERSION:
                return rec
            if rec.analysis_version < ANALYSIS_VERSION:
                rec = migrate_analysis(rec)
                self.put(rec)
                return rec
        for v in range(ANALYSIS_VERSION - 1, 1, -1):
            old = self.root / ".mil4dy" / "cache" / f"v{v}" / f"{fp}.json"
            if not old.exists():
                continue
            rec = self._load(old)
            if rec is None:
                continue
            rec = migrate_analysis(rec)
            self.put(rec)
            return rec
        return None

    def put(self, rec: TrackAnalysis) -> None:
        self._path(rec.fingerprint).write_text(rec.model_dump_json())
