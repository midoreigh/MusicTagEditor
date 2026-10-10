"""Round-trip tests: edit through mte, reopen with plain mutagen, check raw state."""

from __future__ import annotations

import base64

import mutagen
from mutagen.apev2 import APEv2
from mutagen.flac import FLAC, Picture as FlacPicture
from mutagen.id3 import APIC, COMM, ID3, PCST, PRIV, TIT2, TXXX, TYER, WFED
from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm

from mte.core.cleaner import removal_ops
from mte.core.formats.id3 import blank_frame_entry, build_id3v1, parse_id3v1
from mte.core.model import DeleteEntry, FieldType, SetEntry
from mte.core.tagfile import TagFile, apply_and_save, load

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def entry(ft, system, key):
    for e in ft.entries:
        if e.system == system and e.key == key:
            return e
    raise AssertionError(f"{system}:{key} not in {[(e.system, e.key) for e in ft.entries]}")


def keys(ft, system=None):
    return {e.key for e in ft.entries if system is None or e.system == system}


# ---------------------------------------------------------------- ID3v2

def seed_podcast_mp3(path, v2_version=4):
    tags = ID3()
    tags.add(TIT2(encoding=3, text=["Song"]))
    tags.add(TXXX(encoding=3, desc="podcastdesc", text=["www.Songs.PK"]))
    tags.add(TXXX(encoding=3, desc="podcastid", text=["www.Songs.PK"]))
    tags.add(WFED(url="http://ww.Songs.PK"))
    tags.add(PCST(value=1))
    tags.add(PRIV(owner="WM/MediaClassPrimaryID", data=b"\x01\x02\x03"))
    tags.add(COMM(encoding=3, lang="eng", desc="", text=["hello"]))
    tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="cover", data=JPEG))
    if v2_version == 3:
        tags.add(TYER(encoding=1, text=["1999"]))
        tags.save(path, v2_version=3)
    else:
        tags.save(path)


def test_id3_shows_every_frame(mp3):
    seed_podcast_mp3(mp3)
    ft = load(mp3)
    assert ft.error is None
    assert {"TIT2", "TXXX:podcastdesc", "TXXX:podcastid", "WFED", "PCST",
            "PRIV:WM/MediaClassPrimaryID:\x01\x02\x03", "COMM::eng", "APIC:cover"} <= keys(ft, "ID3v2")
    comm = entry(ft, "ID3v2", "COMM::eng")
    assert comm.get("lang") == "eng" and comm.get("text") == ["hello"]
    apic = entry(ft, "ID3v2", "APIC:cover")
    assert apic.get("data") == JPEG and apic.get("type") == 3


def test_id3_edit_text_and_rename_txxx(mp3):
    seed_podcast_mp3(mp3)
    ft = load(mp3)
    title = entry(ft, "ID3v2", "TIT2").clone()
    title.set("text", ["New", "Second"])
    txxx = entry(ft, "ID3v2", "TXXX:podcastid").clone()
    txxx.set("desc", "renamed")
    apply_and_save(mp3, [SetEntry(title, "TIT2"), SetEntry(txxx, "TXXX:podcastid")])
    tags = ID3(mp3)
    assert tags["TIT2"].text == ["New", "Second"]
    assert "TXXX:podcastid" not in tags and tags["TXXX:renamed"].text == ["www.Songs.PK"]
    assert tags["PRIV:WM/MediaClassPrimaryID:\x01\x02\x03"].data == b"\x01\x02\x03"  # untouched


def test_id3_v23_stays_v23_and_raw(mp3):
    seed_podcast_mp3(mp3, v2_version=3)
    ft = load(mp3)
    assert "TYER" in keys(ft, "ID3v2")  # not translated to TDRC
    assert ft.info["id3"] == "ID3v2.3"
    e = entry(ft, "ID3v2", "TIT2").clone()
    e.set("text", ["v23"])
    apply_and_save(mp3, [SetEntry(e, "TIT2")])
    raw = ID3(mp3, translate=False)
    assert raw.version == (2, 3, 0)
    assert raw["TYER"].text == ["1999"] and raw["TIT2"].text == ["v23"]


def test_id3_add_and_delete(mp3):
    ft = load(mp3)
    assert keys(ft, "ID3v2") == set()
    new = blank_frame_entry("TXXX")
    new.set("desc", "custom")
    new.set("text", ["value"])
    apply_and_save(mp3, [SetEntry(new)])
    assert ID3(mp3)["TXXX:custom"].text == ["value"]
    apply_and_save(mp3, [DeleteEntry("ID3v2", "TXXX:custom")])
    assert mutagen.File(mp3).tags is None  # empty tag removed entirely


def test_cleaner_matches_original_script_behaviour(mp3):
    seed_podcast_mp3(mp3)
    ft = load(mp3)
    ops = removal_ops(ft, "songs.pk")
    assert {op.key for op in ops} == {"TXXX:podcastdesc", "TXXX:podcastid", "WFED"}
    apply_and_save(mp3, ops)
    tags = ID3(mp3)
    assert "TXXX:podcastdesc" not in tags and "WFED" not in tags
    assert tags["TIT2"].text == ["Song"]


def test_unknown_frames_survive_and_can_be_deleted(mp3):
    seed_podcast_mp3(mp3)
    # append a frame with an id mutagen doesn't know (v2.4 header + body)
    data = bytearray(mp3.read_bytes())
    body = b"\x00custom-payload"
    frame = b"XZZY" + bytes([0, 0, 0, len(body)]) + b"\x00\x00" + body
    size = int.from_bytes(data[6:10], "big")
    size = (size & 0x7F) | ((size >> 8) & 0x7F) << 7 | ((size >> 16) & 0x7F) << 14 | \
        ((size >> 24) & 0x7F) << 21
    new_size = size + len(frame)
    syncsafe = bytes([(new_size >> 21) & 0x7F, (new_size >> 14) & 0x7F,
                      (new_size >> 7) & 0x7F, new_size & 0x7F])
    data[6:10] = syncsafe
    data[10:10] = frame
    mp3.write_bytes(bytes(data))

    ft = load(mp3)
    unknown = [e for e in ft.entries if e.frame_id == "XZZY"]
    assert unknown and unknown[0].readonly and unknown[0].get("data") == body
    # unrelated edit keeps the unknown frame
    t = entry(ft, "ID3v2", "TIT2").clone()
    t.set("text", ["x"])
    ft = apply_and_save(mp3, [SetEntry(t, "TIT2")])
    unknown = [e for e in ft.entries if e.frame_id == "XZZY"]
    assert unknown
    ft = apply_and_save(mp3, [DeleteEntry("ID3v2", unknown[0].key)])
    assert not [e for e in ft.entries if e.frame_id == "XZZY"]


# ---------------------------------------------------------------- ID3v1 / APE on MP3

def test_id3v1_is_separate_and_preserved(mp3):
    v1 = {"title": "V1 title", "artist": "A", "album": "B", "year": "2001",
          "comment": "c", "track": 7, "genre": 17}
    seed_podcast_mp3(mp3)
    with open(mp3, "ab") as f:  # v1 that differs from the v2 frames
        f.write(build_id3v1(v1))
    ft = load(mp3)
    assert entry(ft, "ID3v1", "title").get("value") == "V1 title"
    assert entry(ft, "ID3v2", "TIT2").get("text") == ["Song"]  # not merged
    # editing v2 must not overwrite v1 with v2 data
    t = entry(ft, "ID3v2", "TIT2").clone()
    t.set("text", ["Changed"])
    apply_and_save(mp3, [SetEntry(t, "TIT2")])
    assert parse_id3v1(mp3.read_bytes()[-128:])["title"] == "V1 title"
    # edit v1 itself
    e = entry(load(mp3), "ID3v1", "artist").clone()
    e.set("value", "New artist")
    apply_and_save(mp3, [SetEntry(e, "artist")])
    parsed = parse_id3v1(mp3.read_bytes()[-128:])
    assert parsed["artist"] == "New artist" and parsed["track"] == 7 and parsed["genre"] == 17


def test_apev2_on_mp3(mp3):
    seed_podcast_mp3(mp3)
    ape = APEv2()
    ape["Artist"] = "Ape artist"
    ape.save(mp3)
    ft = load(mp3)
    e = entry(ft, "APEv2", "Artist").clone()
    assert e.get("values") == ["Ape artist"]
    e.set("values", ["one", "two"])
    e.set("key", "Performer")
    apply_and_save(mp3, [SetEntry(e, "Artist")])
    ape = APEv2(mp3)
    assert "Artist" not in ape and list(ape["Performer"]) == ["one", "two"]
    assert ID3(mp3)["TIT2"].text == ["Song"]


# ---------------------------------------------------------------- WAV (ID3 in RIFF)

def test_wav_id3(wav):
    tf = TagFile(wav)
    e = blank_frame_entry("TIT2")
    e.set("text", ["wav title"])
    tf.apply([SetEntry(e)])
    tf.save()
    assert mutagen.File(wav).tags["TIT2"].text == ["wav title"]


# ---------------------------------------------------------------- MP4

def test_mp4_atoms(m4a):
    mp4 = MP4(m4a)
    mp4["©nam"] = ["Title"]
    mp4["pcst"] = True
    mp4["catg"] = ["www.Songs.PK"]
    mp4["trkn"] = [(3, 12)]
    mp4["----:com.apple.iTunes:podcastdesc"] = [MP4FreeForm(b"junk")]
    mp4["covr"] = [MP4Cover(JPEG, MP4Cover.FORMAT_JPEG)]
    mp4.save()

    ft = load(m4a)
    assert entry(ft, "MP4", "pcst").get("value") is True
    assert entry(ft, "MP4", "trkn").get("values") == [(3, 12)]
    assert entry(ft, "MP4", "covr").get("images")[0].data == JPEG
    ff = entry(ft, "MP4", "----:com.apple.iTunes:podcastdesc").clone()
    assert ff.get("values") == ["junk"]

    ff.set("key", "----:com.apple.iTunes:renamed")
    ff.set("values", ["a", "b"])
    trkn = entry(ft, "MP4", "trkn").clone()
    trkn.set("values", [(5, 10)])
    apply_and_save(m4a, [SetEntry(ff, "----:com.apple.iTunes:podcastdesc"),
                         SetEntry(trkn, "trkn"), DeleteEntry("MP4", "catg")])
    mp4 = MP4(m4a)
    assert "----:com.apple.iTunes:podcastdesc" not in mp4
    assert [bytes(v) for v in mp4["----:com.apple.iTunes:renamed"]] == [b"a", b"b"]
    assert mp4["trkn"] == [(5, 10)] and "catg" not in mp4 and mp4["pcst"] is True


# ---------------------------------------------------------------- Vorbis / FLAC

def test_flac_vorbis_and_pictures(flac):
    f = FLAC(flac)
    f.add_tags()
    f.tags.append(("Title", "t"))
    f.tags.append(("podcasturl", "ww.Songs.PK"))
    f.tags.append(("ARTIST", "a1"))
    f.tags.append(("artist", "a2"))
    pic = FlacPicture()
    pic.type, pic.mime, pic.data = 3, "image/jpeg", JPEG
    f.add_picture(pic)
    f.save()

    ft = load(flac)
    art = entry(ft, "Vorbis", "ARTIST")
    assert art.get("values") == ["a1", "a2"]  # grouped, original case kept
    assert entry(ft, "FLAC", "PICTURE#0").get("data") == JPEG
    assert entry(ft, "Vorbis", "<vendor>").get("value")

    art = art.clone()
    art.set("values", ["only"])
    apply_and_save(flac, [SetEntry(art, "ARTIST"), DeleteEntry("Vorbis", "podcasturl"),
                          DeleteEntry("FLAC", "PICTURE#0")])
    f = FLAC(flac)
    assert list(f.tags) == [("Title", "t"), ("ARTIST", "only")]
    assert f.pictures == []


def test_opus_comments_and_embedded_picture(opus):
    pic = FlacPicture()
    pic.type, pic.mime, pic.data = 3, "image/jpeg", JPEG
    a = mutagen.File(opus)
    a.tags["TITLE"] = ["opus"]
    a.tags["METADATA_BLOCK_PICTURE"] = [base64.b64encode(pic.write()).decode()]
    a.save()
    ft = load(opus)
    assert entry(ft, "Vorbis", "TITLE").get("values") == ["opus"]
    p = entry(ft, "Vorbis", "METADATA_BLOCK_PICTURE#0")
    assert p.get("data") == JPEG and p.field("data").ftype == FieldType.BYTES
    p = p.clone()
    p.set("desc", "front")
    apply_and_save(opus, [SetEntry(p, p.key)])
    raw = mutagen.File(opus).tags["METADATA_BLOCK_PICTURE"][0]
    assert FlacPicture(base64.b64decode(raw)).desc == "front"


def test_unsupported_file_reports_error(tmp_path):
    p = tmp_path / "x.mp3"
    p.write_bytes(b"not audio at all")
    ft = load(p)
    assert ft.error
