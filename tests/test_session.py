from mutagen.id3 import ID3

from mte.core.batch import save_all
from mte.core.formats.id3 import blank_frame_entry
from mte.core.session import Session
from mte.core.model import DeleteEntry, SetEntry
from mte.core.tagfile import load

from conftest import make_mp3, make_flac
from test_formats import seed_podcast_mp3


def test_batch_edit_merge_and_save(tmp_path):
    a, b = make_mp3(tmp_path / "a.mp3"), make_mp3(tmp_path / "b.mp3")
    seed_podcast_mp3(a)
    seed_podcast_mp3(b)
    tags = ID3(b)
    tags["TIT2"].text = ["Other"]
    tags.save()
    s = Session()
    for p in (a, b):
        s.add(load(p))
    paths = [str(a), str(b)]
    rows = {(r.system, r.key): r for r in s.merged(paths)}
    assert not rows[("ID3v2", "TIT2")].uniform
    assert rows[("ID3v2", "TXXX:podcastdesc")].uniform

    e = rows[("ID3v2", "TIT2")].first.clone()
    e.set("text", ["Same"])
    s.set_entry(paths, e, "TIT2")
    s.delete(paths, "ID3v2", "TXXX:podcastdesc")
    new = blank_frame_entry("TXXX")
    new.set("desc", "added")
    new.set("text", ["x"])
    s.set_entry(paths, new, None)
    rows = {(r.system, r.key): r for r in s.merged(paths)}
    assert rows[("ID3v2", "TIT2")].uniform
    assert ("ID3v2", "TXXX:podcastdesc") not in rows
    assert s.files[str(a)].entry_state(rows[("ID3v2", "TXXX:added")].first) == "new"

    # disk untouched until save
    assert ID3(a)["TIT2"].text == ["Song"]
    result = save_all(s.save_plan())
    assert not result.errors
    for p in (a, b):
        t = ID3(p)
        assert t["TIT2"].text == ["Same"] and "TXXX:podcastdesc" not in t
        assert t["TXXX:added"].text == ["x"]


def test_batch_partial_failure(tmp_path):
    a = make_mp3(tmp_path / "a.mp3")
    f = make_flac(tmp_path / "b.flac")
    s = Session()
    s.add(load(a))
    s.add(load(f))
    e = blank_frame_entry("TIT2")
    errors = s.set_entry([str(a), str(f)], e, None)
    assert str(f) in errors and str(a) not in errors  # FLAC can't hold ID3v2
    a.write_bytes(b"corrupted now")
    result = save_all(s.save_plan())
    assert str(a) in result.errors


def test_revert(tmp_path):
    a = make_mp3(tmp_path / "a.mp3")
    seed_podcast_mp3(a)
    s = Session()
    s.add(load(a))
    s.delete([str(a)], "ID3v2", "TIT2")
    assert s.files[str(a)].dirty
    s.revert([str(a)])
    assert not s.files[str(a)].dirty
    assert s.files[str(a)].find("ID3v2", "TIT2") is not None


def _v1_file(tmp_path):
    from mte.core.formats.id3 import build_id3v1
    p = make_mp3(tmp_path / "v1.mp3")
    seed_podcast_mp3(p)
    with open(p, "ab") as f:
        f.write(build_id3v1({"title": "T", "artist": "A", "album": "Short", "year": "2013",
                             "comment": "", "track": 1, "genre": 255}))
    return p


def test_invalid_edit_is_rejected_when_made_not_on_save(tmp_path):
    import pytest
    from mte.core.formats.base import TagError

    p = _v1_file(tmp_path)
    s = Session()
    s.add(load(p))
    st = s.files[str(p)]
    album = st.find("ID3v1", "album").clone()
    album.set("value", "x" * 31)  # ID3v1 album is 30 bytes max
    with pytest.raises(TagError, match="30 bytes"):
        st.apply(SetEntry(album, "album"))
    assert not st.dirty and st.find("ID3v1", "album").get("value") == "Short"
    errors = s.set_entry([str(p)], album, "album")
    assert str(p) in errors and "30 bytes" in errors[str(p)]


def test_deleting_or_reverting_a_change_leaves_nothing_to_save(tmp_path):
    from mutagen.id3 import ID3

    p = _v1_file(tmp_path)
    s = Session()
    s.add(load(p))
    st = s.files[str(p)]
    title = st.find("ID3v2", "TIT2").clone()
    title.set("text", ["Changed"])
    st.apply(SetEntry(title, "TIT2"))
    st.apply(DeleteEntry("ID3v2", "TIT2"))
    # the earlier edit must not be replayed: only the deletion is saved
    assert [type(op).__name__ for op in s.save_plan()[str(p)]] == ["DeleteEntry"]

    back = st.original_entry("ID3v2", "TIT2").clone()
    st.apply(SetEntry(back, None))  # put the original value back
    assert not st.dirty and s.save_plan() == {}

    result = save_all(s.save_plan())
    assert not result.errors and ID3(p)["TIT2"].text == ["Song"]


def test_save_writes_the_final_state_not_the_edit_history(tmp_path):
    from mutagen.id3 import ID3

    p = _v1_file(tmp_path)
    s = Session()
    s.add(load(p))
    st = s.files[str(p)]
    for value in ("one", "two", "three"):
        t = st.find("ID3v2", "TIT2").clone()
        t.set("text", [value])
        st.apply(SetEntry(t, "TIT2"))
    txxx = st.find("ID3v2", "TXXX:podcastdesc").clone()
    txxx.set("desc", "renamed")  # key change: old key deleted, new key set
    st.apply(SetEntry(txxx, "TXXX:podcastdesc"))
    ops = s.save_plan()[str(p)]
    assert len(ops) == 3  # TIT2 set once, old TXXX deleted, new TXXX set
    assert not save_all(s.save_plan()).errors
    tags = ID3(p)
    assert tags["TIT2"].text == ["three"]
    assert "TXXX:podcastdesc" not in tags and tags["TXXX:renamed"].text == ["www.Songs.PK"]
