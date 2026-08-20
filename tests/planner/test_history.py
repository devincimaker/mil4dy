"""History store: every render is a file; verdict is a flag."""

import json
import threading
from pathlib import Path

from mil4dy.analysis.decode import discover_tracks
from mil4dy.lab.history import HistoryStore, TrackIdentity


def test_discover_tracks_skips_mil4dy_history(tmp_path: Path):
    (tmp_path / "song.wav").write_bytes(b"RIFF")
    hidden = tmp_path / ".mil4dy" / "history" / "abc"
    hidden.mkdir(parents=True)
    (hidden / "blend.wav").write_bytes(b"RIFF")
    found = discover_tracks([tmp_path])
    assert [p.name for p in found] == ["song.wav"]


def _identity(name: str) -> TrackIdentity:
    return TrackIdentity(id=name, artist="Test", title=name)


def test_record_blend_survives_reload_and_writes_latest(tmp_path: Path):
    src = tmp_path / "heard.wav"
    src.write_bytes(b"BLEND-BYTES")
    store = HistoryStore(tmp_path / "hist")
    rec = store.record_blend(
        outgoing=_identity("alpha"),
        incoming=_identity("beta"),
        decision={"type": "filter_sweep", "length_beats": 32},
        blend_src=src,
        blend_filename="Test-alpha__Test-beta-blend.wav",
    )
    kept = store.resolve(rec.blend)
    assert kept.is_file()
    assert kept.read_bytes() == b"BLEND-BYTES"
    src.write_bytes(b"CHANGED")

    again = HistoryStore(tmp_path / "hist")
    listed = again.list()
    assert len(listed) == 1
    assert listed[0].id == rec.id
    assert listed[0].favorite is False
    assert listed[0].verdict == "none"
    assert listed[0].note is None
    assert again.resolve(listed[0].blend).read_bytes() == b"BLEND-BYTES"
    latest = (tmp_path / "hist" / "LATEST.json")
    assert latest.is_file()
    assert rec.id in latest.read_text()
    link = tmp_path / "hist" / "latest-blend.wav"
    assert link.exists()
    assert link.read_bytes() == b"BLEND-BYTES"


def test_second_hear_is_a_new_file(tmp_path: Path):
    src = tmp_path / "heard.wav"
    src.write_bytes(b"TAKE")
    store = HistoryStore(tmp_path / "hist")
    a = store.record_blend(
        outgoing=_identity("alpha"), incoming=_identity("beta"),
        decision={"type": "quick_cut"}, blend_src=src, blend_filename="a.wav",
    )
    b = store.record_blend(
        outgoing=_identity("alpha"), incoming=_identity("beta"),
        decision={"type": "quick_cut"}, blend_src=src, blend_filename="a.wav",
    )
    assert a.id != b.id
    assert store.resolve(a.blend) != store.resolve(b.blend)
    assert store.latest().id == b.id
    assert len(store.list()) == 2


def test_favorite_is_a_flag_unfavorite_keeps_the_file(tmp_path: Path):
    src = tmp_path / "heard.wav"
    src.write_bytes(b"BLEND")
    store = HistoryStore(tmp_path / "hist")
    rec = store.record_blend(
        outgoing=_identity("alpha"), incoming=_identity("beta"),
        decision={"type": "filter_sweep"}, blend_src=src, blend_filename="b.wav",
    )
    starred = store.set_favorite(rec.id, True)
    assert starred.favorite is True
    assert store.favorites()[0].id == rec.id
    store.set_favorite(rec.id, False)
    assert store.favorites() == []
    assert store.get(rec.id) is not None
    assert store.resolve(rec.blend).is_file()


def test_attach_mix_and_remove_drops_files(tmp_path: Path):
    blend = tmp_path / "blend.wav"
    mix = tmp_path / "mix.wav"
    blend.write_bytes(b"BLEND")
    mix.write_bytes(b"FULLMIX")
    store = HistoryStore(tmp_path / "hist")
    rec = store.record_blend(
        outgoing=_identity("alpha"), incoming=_identity("beta"),
        decision={"type": "filter_sweep"}, blend_src=blend, blend_filename="b.wav",
    )
    updated = store.attach_mix(rec.id, mix, "m.wav")
    assert updated is not None
    assert updated.mix is not None
    mix_path = store.resolve(updated.mix)
    assert mix_path.read_bytes() == b"FULLMIX"
    assert (tmp_path / "hist" / "latest-mix.wav").exists()

    store.remove(rec.id)
    assert store.get(rec.id) is None
    assert not (tmp_path / "hist" / rec.id).exists()


def _write_blend(tmp_path: Path) -> tuple[HistoryStore, object]:
    src = tmp_path / "heard.wav"
    src.write_bytes(b"BLEND")
    store = HistoryStore(tmp_path / "hist")
    rec = store.record_blend(
        outgoing=_identity("alpha"), incoming=_identity("beta"),
        decision={"type": "filter_sweep"}, blend_src=src, blend_filename="b.wav",
    )
    return store, rec


def test_downvote_clears_favorite_and_keeps_the_file(tmp_path: Path):
    store, rec = _write_blend(tmp_path)
    store.set_favorite(rec.id, True)
    down = store.set_verdict(rec.id, "downvoted", note="flams on the swap")
    assert down is not None
    assert down.verdict == "downvoted"
    assert down.favorite is False
    assert down.note == "flams on the swap"
    assert store.favorites() == []
    assert store.downvoted()[0].id == rec.id
    assert store.resolve(rec.blend).is_file()
    store.set_verdict(rec.id, "none")
    kept = store.get(rec.id)
    assert kept is not None
    assert kept.verdict == "none"
    assert store.resolve(rec.blend).is_file()


def test_favorite_clears_downvote(tmp_path: Path):
    store, rec = _write_blend(tmp_path)
    store.set_verdict(rec.id, "downvoted", note="keep this breadcrumb")
    starred = store.set_favorite(rec.id, True)
    assert starred is not None
    assert starred.verdict == "favorite"
    assert starred.favorite is True
    assert starred.note == "keep this breadcrumb"
    assert store.downvoted() == []
    assert store.favorites()[0].id == rec.id


def test_note_persists_across_reload_and_empty_is_valid(tmp_path: Path):
    store, rec = _write_blend(tmp_path)
    store.set_verdict(rec.id, "downvoted", note="keys clash in the mids")
    again = HistoryStore(tmp_path / "hist")
    loaded = again.get(rec.id)
    assert loaded is not None
    assert loaded.verdict == "downvoted"
    assert loaded.note == "keys clash in the mids"
    again.set_note(rec.id, "   ")
    blank = HistoryStore(tmp_path / "hist").get(rec.id)
    assert blank is not None
    assert blank.note is None
    assert blank.verdict == "downvoted"


def test_old_index_without_verdict_reads_as_unmarked(tmp_path: Path):
    root = tmp_path / "hist"
    root.mkdir()
    (root / "index.json").write_text(json.dumps({
        "version": 2,
        "takes": [{
            "id": "abc123abc123",
            "created_at": "2026-01-01T00:00:00+00:00",
            "outgoing": {"id": "a", "artist": "A", "title": "a"},
            "incoming": {"id": "b", "artist": "B", "title": "b"},
            "decision": {"type": "quick_cut"},
            "favorite": False,
        }],
    }))
    rec = HistoryStore(root).get("abc123abc123")
    assert rec is not None
    assert rec.verdict == "none"
    assert rec.favorite is False
    assert rec.note is None


def test_old_favorite_without_verdict_reads_as_favorite(tmp_path: Path):
    root = tmp_path / "hist"
    root.mkdir()
    (root / "index.json").write_text(json.dumps({
        "version": 2,
        "takes": [{
            "id": "fav123fav123",
            "created_at": "2026-01-01T00:00:00+00:00",
            "outgoing": {"id": "a", "artist": "A", "title": "a"},
            "incoming": {"id": "b", "artist": "B", "title": "b"},
            "decision": {"type": "quick_cut"},
            "favorite": True,
        }],
    }))
    rec = HistoryStore(root).get("fav123fav123")
    assert rec is not None
    assert rec.verdict == "favorite"
    assert rec.favorite is True
    assert rec.note is None


def test_concurrent_verdict_and_note_leave_a_valid_index(tmp_path: Path):
    store, rec = _write_blend(tmp_path)
    errors: list[Exception] = []

    def vote() -> None:
        try:
            store.set_verdict(rec.id, "downvoted")
        except Exception as exc:
            errors.append(exc)

    def note() -> None:
        try:
            store.set_note(rec.id, "flams")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=vote) for _ in range(8)]
    threads += [threading.Thread(target=note) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    raw = json.loads((tmp_path / "hist" / "index.json").read_text())
    assert raw["version"] == 3
    loaded = HistoryStore(tmp_path / "hist").get(rec.id)
    assert loaded is not None
    assert loaded.verdict in {"none", "favorite", "downvoted"}
    assert (tmp_path / "hist" / rec.id / "blend.wav").is_file()


def test_index_with_trailing_junk_still_loads(tmp_path: Path):
    store, rec = _write_blend(tmp_path)
    store.set_verdict(rec.id, "downvoted", note="keep me")
    path = tmp_path / "hist" / "index.json"
    path.write_text(path.read_text() + "  ]\n}")
    again = HistoryStore(tmp_path / "hist")
    loaded = again.get(rec.id)
    assert loaded is not None
    assert loaded.verdict == "downvoted"
    assert loaded.note == "keep me"
