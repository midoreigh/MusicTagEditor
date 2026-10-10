from mutagen.id3 import ID3

from rawtag.core.batch import save_all
from rawtag.core.formats.id3 import blank_frame_entry
from rawtag.core.session import Session
from rawtag.core.tagfile import load

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
