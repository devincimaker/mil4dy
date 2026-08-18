"""Pair-lab HTTP API against an in-memory crate (no audio / no analyze)."""

from pathlib import Path

from fastapi.testclient import TestClient

from mil4dy.lab.app import create_app
from tests.planner.test_pair import _track


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


def test_same_track_rejected():
    with _client() as c:
        res = c.get("/api/pair", params={"a": "alpha", "b": "alpha"})
        assert res.status_code == 400
