"""History store: every render is a file; favorite is a flag."""

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
