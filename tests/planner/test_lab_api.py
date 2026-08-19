"""Pair-lab HTTP API against an in-memory crate (no audio / no analyze)."""

from pathlib import Path

from fastapi.testclient import TestClient

from mil4dy.lab.app import create_app
from mil4dy.schemas import TrackAnalysis
from tests.planner.test_pair import _track

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "walk_with_me_grid.json"


def _tracks():
    return [
        _track("alpha", camelot="8A"),
        _track("beta", camelot="8A"),
        _track("clash", camelot="3A"),
    ]


def _client(tmp_path: Path | None = None) -> TestClient:
    hist = (tmp_path / "hist") if tmp_path is not None else None
    app = create_app([Path("/tmp")], preloaded=_tracks(), history_dir=hist)
    return TestClient(app)


def _stub_render(monkeypatch, _tmp_path: Path | None = None):
    def fake_render(plan, wav, **kwargs):
        path = Path(wav)
        path.parent.mkdir(parents=True, exist_ok=True)
        kind = b"MIX" if plan.target_duration_s > 180 else b"BLEND"
        path.write_bytes(kind + b":" + str(plan.target_duration_s).encode())
        return {}

    monkeypatch.setattr("mil4dy.lab.app.render_mix", fake_render)


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


def test_hear_is_saved_to_history_without_favoriting(tmp_path: Path, monkeypatch):
    _stub_render(monkeypatch)
    with _client(tmp_path) as c:
        assert c.get("/api/history").json() == []
        heard = c.post("/api/pair/render", json={"a": "alpha", "b": "beta"})
        assert heard.status_code == 200
        meta = heard.json()
        assert meta["kind"] == "blend"
        assert meta["take_id"] == meta["id"]
        assert meta["favorite"] is False
        assert "alpha" in meta["filename"]
        audio = c.get(meta["url"])
        assert audio.content.startswith(b"BLEND:")
        assert Path(meta["blend_path"]).is_file()
        assert Path(meta["blend_path"]).read_bytes() == audio.content

        hist = c.get("/api/history").json()
        assert len(hist) == 1
        assert hist[0]["id"] == meta["id"]
        assert hist[0]["favorite"] is False
        assert c.get("/api/favorites").json() == []

        latest = c.get("/api/history/latest")
        assert latest.status_code == 200
        assert latest.json()["id"] == meta["id"]
        assert (tmp_path / "hist" / "LATEST.json").is_file()


def test_second_hear_is_a_new_history_row(tmp_path: Path, monkeypatch):
    _stub_render(monkeypatch)
    with _client(tmp_path) as c:
        a = c.post("/api/pair/render", json={"a": "alpha", "b": "beta"}).json()
        b = c.post("/api/pair/render", json={"a": "alpha", "b": "beta"}).json()
        assert a["id"] != b["id"]
        assert a["blend_path"] != b["blend_path"]
        hist = c.get("/api/history").json()
        assert len(hist) == 2
        assert hist[0]["id"] == b["id"]


def test_favorite_is_a_flag_and_unfavorite_keeps_the_file(tmp_path: Path, monkeypatch):
    _stub_render(monkeypatch)
    with _client(tmp_path) as c:
        heard = c.post("/api/pair/render", json={"a": "alpha", "b": "beta"}).json()
        starred = c.post("/api/favorites", json={"take_id": heard["id"]})
        assert starred.status_code == 200
        body = starred.json()
        assert body["favorite"] is True
        assert Path(body["blend_path"]).is_file()
        assert len(c.get("/api/favorites").json()) == 1

        gone = c.delete(f"/api/favorites/{heard['id']}")
        assert gone.status_code == 200
        assert gone.json()["favorite"] is False
        assert c.get("/api/favorites").json() == []
        still = c.get("/api/history").json()
        assert len(still) == 1
        assert Path(still[0]["blend_path"]).is_file()


def test_download_mix_is_not_the_padded_window_and_attaches(tmp_path: Path, monkeypatch):
    _stub_render(monkeypatch)
    with _client(tmp_path) as c:
        blend = c.post("/api/pair/render", json={"a": "alpha", "b": "beta"}).json()
        mix = c.post(
            "/api/pair/mix",
            json={"a": "alpha", "b": "beta", "take_id": blend["id"]},
        )
        assert mix.status_code == 200
        body = mix.json()
        assert body["kind"] == "mix"
        assert body["take_id"] == blend["id"]
        assert "mix" in body["filename"]
        mix_bytes = c.get(body["url"]).content
        blend_bytes = c.get(blend["url"]).content
        assert mix_bytes.startswith(b"MIX:")
        assert mix_bytes != blend_bytes
        take = c.get("/api/history").json()[0]
        assert take["id"] == blend["id"]
        assert take["mix_path"]
        assert Path(take["mix_path"]).read_bytes() == mix_bytes
        assert c.get(take["mix_url"]).content == mix_bytes
        dl = c.get(take["blend_download_url"])
        assert "alpha" in (dl.headers.get("content-disposition") or "")


def test_remove_from_history_drops_files(tmp_path: Path, monkeypatch):
    _stub_render(monkeypatch)
    with _client(tmp_path) as c:
        blend = c.post("/api/pair/render", json={"a": "alpha", "b": "beta"}).json()
        c.post("/api/pair/mix", json={"a": "alpha", "b": "beta", "take_id": blend["id"]})
        take = c.get("/api/history").json()[0]
        blend_path = Path(take["blend_path"])
        mix_path = Path(take["mix_path"])
        gone = c.delete(f"/api/history/{blend['id']}")
        assert gone.status_code == 200
        assert c.get("/api/history").json() == []
        assert not blend_path.exists()
        assert not mix_path.exists()


def test_cannot_favorite_an_unknown_take(tmp_path: Path):
    with _client(tmp_path) as c:
        res = c.post("/api/favorites", json={"blend_id": "missing"})
        assert res.status_code == 404


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
