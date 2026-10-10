"""File naming: script engine, variable mapping, renamer, save integration."""

from __future__ import annotations

import os

import pytest
from mutagen.flac import FLAC
from mutagen.id3 import ID3, TALB, TIT2, TPE1, TPE2, TPOS, TRCK, TXXX
from mutagen.mp4 import MP4

from mte.core.batch import save_all
from mte.core.naming import (PICARD_DEFAULT, NamingOptions, ScriptError, build_variables,
                             evaluate, rename_file, script_to_relpath, target_path)
from mte.core.naming.renamer import sanitize_component
from mte.core.model import SetEntry
from mte.core.tagfile import load

from conftest import make_flac, make_mp3


# ------------------------------------------------------------- script engine

@pytest.mark.parametrize("script, expected", [
    ("%artist% - %title%", "A - T"),
    ("$if(%missing%,yes,no)", "no"),
    ("$if(%artist%,yes)", "yes"),
    ("$if2(%missing%,%empty%,%title%)", "T"),
    ("$num(%track%,2)", "03"),
    ("$num(abc,3)", "000"),
    ("$upper($left(%title%xyz,2))", "TX"),
    ("$title(hello world)", "Hello World"),
    ("$replace(a.b.c,.,_)", "a_b_c"),
    ("$rreplace(track 01,\\\\s*\\\\d+,)", "track"),  # regex backslashes are escaped
    ("$set(x,1)$if($eq(%x%,1),one,other)", "one"),
    ("$gt(%track%,2)|$lt(%track%,2)", "1|"),
    ("$and(%artist%,%missing%)|$or(%artist%,%missing%)|$not(%missing%)", "|1|1"),
    ("$swapprefix(The Beatles)", "Beatles, The"),
    ("$firstalphachar(%artist%)/$firstalphachar(9 lives)", "A/#"),
    ("\\$\\%\\(\\)\\,", "$%(),"),
    ("$noop(comment, ignored)x", "x"),
    ("plain (text), kept", "plain (text), kept"),
    ("$add(1,2,3)-$sub(10,3)-$mul(2,4)-$div(9,2)-$mod(9,2)", "6-7-8-4-1"),
    ("%ARTIST%", "A"),  # variable names are case-insensitive
])
def test_script(script, expected):
    assert evaluate(script, {"artist": "A", "title": "T", "track": "3", "empty": ""}) == expected


@pytest.mark.parametrize("script", ["%unclosed", "$if(a,b", "$nosuch(x)", "$if(a)", "$(x)",
                                    "trailing\\"])
def test_script_errors(script):
    with pytest.raises(ScriptError):
        evaluate(script, {})


def test_picard_default_script_and_newlines():
    v = {"albumartist": "Various", "artist": "Solo", "album": "Hits", "tracknumber": "3",
         "totaldiscs": "2", "discnumber": "1", "title": "Song", "_multiartist": "1"}
    assert script_to_relpath(PICARD_DEFAULT, v) == "Various/Hits/1-03 Solo - Song"
    v = {"artist": "Solo", "title": "Song"}
    assert script_to_relpath(PICARD_DEFAULT, v) == "Solo/Song"


def test_sanitize():
    assert sanitize_component('a:b*c?"d<e>|f') == "a_b_c__d_e__f"
    assert sanitize_component("name. ") == "name"
    assert sanitize_component("CON") == "_CON"
    assert len(sanitize_component("x" * 400).encode()) <= 240
    assert script_to_relpath("a/../b//c", {}) == "a/b/c"


# --------------------------------------------------------------- variables

def test_variables_from_id3_and_flac(tmp_path):
    mp3 = make_mp3(tmp_path / "a.mp3")
    t = ID3()
    t.add(TIT2(encoding=3, text=["Song"]))
    t.add(TPE1(encoding=3, text=["Artist", "Feat"]))
    t.add(TRCK(encoding=3, text=["3/12"]))
    t.add(TPOS(encoding=3, text=["1/2"]))
    t.add(TXXX(encoding=3, desc="podcastdesc", text=["junk"]))
    t.save(mp3)
    v = build_variables(load(mp3))
    assert v["title"] == "Song" and v["artist"] == "Artist; Feat"
    assert (v["tracknumber"], v["totaltracks"], v["discnumber"], v["totaldiscs"]) == \
        ("3", "12", "1", "2")
    assert v["podcastdesc"] == "junk" and v["_raw:txxx:podcastdesc"] == "junk"
    assert v["_extension"] == "mp3" and v["_filename"] == "a"

    flac = make_flac(tmp_path / "b.flac")
    f = FLAC(flac)
    f.add_tags()
    f.tags.extend([("TITLE", "FT"), ("TRACKNUMBER", "7"), ("TRACKTOTAL", "9"),
                   ("ALBUMARTIST", "AA"), ("ARTIST", "X")])
    f.save()
    v = build_variables(load(flac))
    assert (v["title"], v["tracknumber"], v["totaltracks"]) == ("FT", "7", "9")
    assert v["_multiartist"] == "1"


def test_variables_from_mp4(m4a):
    mp4 = MP4(m4a)
    mp4["©nam"] = ["Pod ep"]
    mp4["trkn"] = [(4, 10)]
    mp4["----:com.apple.iTunes:MOOD"] = [b"calm"]
    mp4.save()
    v = build_variables(load(m4a))
    assert v["title"] == "Pod ep" and v["tracknumber"] == "4" and v["totaltracks"] == "10"
    assert v["mood"] == "calm"


# ----------------------------------------------------------------- renamer

def seeded(path, title="Song", artist="Artist", album="Album", track="3"):
    make_mp3(path)
    t = ID3()
    t.add(TIT2(encoding=3, text=[title]))
    t.add(TPE1(encoding=3, text=[artist]))
    t.add(TPE2(encoding=3, text=[artist]))
    t.add(TALB(encoding=3, text=[album]))
    t.add(TRCK(encoding=3, text=[track]))
    t.save(path)
    return path


def test_rename_in_place_and_collision(tmp_path):
    a = seeded(tmp_path / "a.mp3")
    b = seeded(tmp_path / "b.mp3")
    opts = NamingOptions(rename=True, script="$num(%tracknumber%,2) - %title%")
    new_a = rename_file(load(a), opts)
    assert new_a == str(tmp_path / "03 - Song.mp3") and os.path.exists(new_a)
    new_b = rename_file(load(b), opts)  # same target -> suffixed, never overwritten
    assert new_b == str(tmp_path / "03 - Song (1).mp3")
    # renaming an already-correct file is a no-op
    assert rename_file(load(new_a), opts) == new_a


def test_move_into_folders_and_cleanup(tmp_path):
    src_dir = tmp_path / "incoming" / "nested"
    src_dir.mkdir(parents=True)
    a = seeded(src_dir / "x.MP3", title='What? "Now"')
    lib = tmp_path / "Library"
    opts = NamingOptions(rename=True, script=PICARD_DEFAULT, move=True, dest_dir=str(lib),
                         delete_empty_dirs=True)
    new = rename_file(load(a), opts)
    assert new == str(lib / "Artist" / "Album" / "03 What_ _Now_.mp3")
    assert os.path.exists(new) and not src_dir.exists() and not (tmp_path / "incoming").exists()


def test_move_without_rename_keeps_name(tmp_path):
    a = seeded(tmp_path / "keep me.mp3")
    lib = tmp_path / "lib"
    new = rename_file(load(a), NamingOptions(rename=False, move=True, dest_dir=str(lib)))
    assert new == str(lib / "keep me.mp3")


def test_empty_result_is_an_error(tmp_path):
    a = make_mp3(tmp_path / "a.mp3")
    with pytest.raises(ValueError):
        target_path(load(a), NamingOptions(rename=True, script="%title%"))


def test_preview_uses_pending_edits(tmp_path):
    a = seeded(tmp_path / "a.mp3")
    ft = load(a)
    working = [e.clone() for e in ft.entries]
    next(e for e in working if e.key == "TIT2").set("text", ["Edited"])
    opts = NamingOptions(rename=True, script="%title%")
    assert target_path(ft, opts, working).endswith("Edited.mp3")


def test_save_all_renames_after_writing_tags(tmp_path):
    a = seeded(tmp_path / "a.mp3")
    ft = load(a)
    title = next(e for e in ft.entries if e.key == "TIT2").clone()
    title.set("text", ["New Title"])
    result = save_all({str(a): [SetEntry(title, "TIT2")]},
                      naming=NamingOptions(rename=True, script="%artist% - %title%"))
    assert not result.errors and not result.rename_errors
    new = str(tmp_path / "Artist - New Title.mp3")
    assert result.renamed == {str(a): new}
    assert ID3(new)["TIT2"].text == ["New Title"] and not a.exists()


def test_rename_failure_keeps_saved_tags(tmp_path):
    a = seeded(tmp_path / "a.mp3")
    ft = load(a)
    title = next(e for e in ft.entries if e.key == "TIT2").clone()
    title.set("text", [""])
    result = save_all({str(a): [SetEntry(title, "TIT2")]},
                      naming=NamingOptions(rename=True, script="%title%"))
    assert str(a) in result.rename_errors and str(a) in result.saved and not result.errors
    assert "TIT2" not in ID3(a)  # the (empty) title edit was written
