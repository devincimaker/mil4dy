"""v3 → v4 cache migrate: refit BPM, no beat_this, no audio."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from mil4dy.analysis.beats import fit_pulse
from mil4dy.analysis.cache import AnalysisCache, migrate_analysis
from mil4dy.planner.pair import decide_pair
from mil4dy.schemas import ANALYSIS_VERSION, TrackAnalysis


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FERXXO = FIXTURES / "ferxxo_grid.json"
G1RL5 = FIXTURES / "g1rl5_grid.json"


def _load(path: Path) -> TrackAnalysis:
    return TrackAnalysis.model_validate_json(path.read_text())


def test_ferxxo_g1rl5_stored_bpm_is_the_125_lie():
    ferxxo, girl = _load(FERXXO), _load(G1RL5)
    assert ferxxo.analysis_version < ANALYSIS_VERSION
    assert girl.analysis_version < ANALYSIS_VERSION
    assert abs(ferxxo.bpm - 125.0) < 0.01
    assert abs(girl.bpm - 125.0) < 0.01


def test_migrate_recovers_124_and_127_without_audio():
    ferxxo = migrate_analysis(_load(FERXXO))
    girl = migrate_analysis(_load(G1RL5))
    assert ferxxo.analysis_version == ANALYSIS_VERSION
    assert girl.analysis_version == ANALYSIS_VERSION
    assert abs(ferxxo.bpm - 124.00) < 0.05
    assert abs(girl.bpm - 126.99) < 0.05
    raw_f = np.asarray(_load(FERXXO).beat_times, dtype=float)
    raw_g = np.asarray(_load(G1RL5).beat_times, dtype=float)
    assert fit_pulse(raw_f).rms < 0.015
    assert fit_pulse(raw_g).rms < 0.015
    # Rebuilt ticks are a constant period, not 460/480 leftover.
    # Cache write rounds to 1e-5 s (~0.01 ms); that is not 20 ms snap.
    ibi_g = np.diff(np.asarray(girl.beat_times, dtype=float))
    assert float(np.max(ibi_g) - np.min(ibi_g)) < 1e-4
    assert not {0.46, 0.48}.issubset(set(np.round(ibi_g, 2)))


def test_decide_pair_sees_a_real_gap_after_migrate():
    ferxxo = migrate_analysis(_load(FERXXO))
    girl = migrate_analysis(_load(G1RL5))
    d = decide_pair(ferxxo, girl)
    gap_bpm = d.bpm_gap * ferxxo.bpm
    assert gap_bpm > 1.5
    blob = " ".join(d.reasons)
    assert "0.0 BPM apart" not in blob
    assert "will ramp" in blob
    assert abs(d.bpm_gap) > 0.01


def test_cache_get_migrates_v3_json_without_beat_this(tmp_path: Path):
    src = _load(G1RL5)
    old_dir = tmp_path / ".mil4dy" / "cache" / "v3"
    old_dir.mkdir(parents=True)
    (old_dir / f"{src.fingerprint}.json").write_text(src.model_dump_json())

    cache = AnalysisCache(tmp_path)
    rec = cache.get(src.fingerprint)
    assert rec is not None
    assert rec.analysis_version == ANALYSIS_VERSION
    assert abs(rec.bpm - 126.99) < 0.05
    v4 = tmp_path / ".mil4dy" / "cache" / f"v{ANALYSIS_VERSION}" / f"{src.fingerprint}.json"
    assert v4.is_file()
    # Second read is a v4 hit, still the fitted BPM.
    again = cache.get(src.fingerprint)
    assert again is not None
    assert abs(again.bpm - rec.bpm) < 1e-9
