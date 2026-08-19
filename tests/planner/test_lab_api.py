"""Pair-lab HTTP API against an in-memory crate (no audio / no analyze)."""

from pathlib import Path

from fastapi.testclient import TestClient

from mil4dy.lab.app import create_app
from mil4dy.schemas import TrackAnalysis
from tests.planner.test_pair import _track

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "walk_with_me_grid.json"


def _client() -> TestClient:
    tracks = [
        _track("alpha", camelot="8A"),
        _track("beta", camelot="8A"),
        _track("clash", camelot="3A"),
    ]
    app = create_app([Path("/tmp")], preloaded=tracks)
    return TestClient(app)


def test_library_lists_preloaded_tracks():
    with _client() as c:
        res = c.get("/api/library")
        assert res.status_code == 200
        names = {t["title"] for t in res.json()}
        assert names == {"alpha", "beta", "clash"}


def test_pair_returns_a_decision():
    with _client() as c:
        res = c.get("/api/pair", params={"a": "alpha", "b": "beta"})
        assert res.status_code == 200
        body = res.json()
        assert body["a"]["id"] == "alpha"
        assert body["b"]["id"] == "beta"
        assert body["decision"]["length_beats"] >= 8
        assert body["decision"]["reasons"]
        d = body["decision"]
        assert 0 <= d["blend_start_s"] < d["blend_end_s"]
        assert d["blend_end_s"] <= d["window_duration_s"] + 1.5


def test_same_track_rejected():
    with _client() as c:
        res = c.get("/api/pair", params={"a": "alpha", "b": "alpha"})
        assert res.status_code == 400


def test_pair_flags_broken_intro_grid():
    walk = TrackAnalysis.model_validate_json(_FIXTURE.read_text())
    out = _track(
        "underground",
        bpm=125.0,
        duration=360.0,
        camelot=walk.camelot or "8A",
        segments=[
            ("drop", 0.0, 280.0, 0.15),
            ("verse", 280.0, 360.0, 0.2),
        ],
    )
    app = create_app([Path("/tmp")], preloaded=[out, walk])
    with TestClient(app) as c:
        res = c.get("/api/pair", params={"a": out.fingerprint, "b": walk.fingerprint})
        assert res.status_code == 200
        d = res.json()["decision"]
        assert d["length_beats"] == 64
        assert abs((d["in_end_s"] - d["in_start_s"]) - 30.72) < 1.5
        assert d["in_grid_ok"] is False
        assert d["window_expected_s"] > 30
        assert d["grid_warning"]
        assert "grid looks off" in d["grid_warning"]
        assert "pulse_warning" in d
        assert d["out_pulse_shift_s"] == 0.0
        assert d["in_pulse_shift_s"] == 0.0
