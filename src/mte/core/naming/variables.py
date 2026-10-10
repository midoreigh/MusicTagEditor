"""Map raw tags of any format onto Picard-style script variables.

``%artist%`` comes from TPE1, ©ART, ARTIST, APE "Artist" or ASF "Author",
depending on the file. The first tag system of a file wins (ID3v2 before
APEv2 before ID3v1). Every raw tag is also reachable by its native key, e.g.
``%_raw:TXXX:podcastdesc%`` or ``%_raw:©nam%``.
"""

from __future__ import annotations

import os

from ..model import FieldType, FileTags, TagEntry, format_value

ID3 = {
    "TIT2": "title", "TPE1": "artist", "TALB": "album", "TPE2": "albumartist",
    "TCON": "genre", "TCOM": "composer", "TEXT": "lyricist", "TPE3": "conductor",
    "TPE4": "remixer", "TIT1": "grouping", "TIT3": "subtitle", "TSOP": "artistsort",
    "TSO2": "albumartistsort", "TSOA": "albumsort", "TSOT": "titlesort",
    "TSOC": "composersort", "TBPM": "bpm", "TSRC": "isrc", "TPUB": "label",
    "TCMP": "compilation", "TKEY": "key", "TLAN": "language", "TMED": "media",
    "TCOP": "copyright", "TENC": "encodedby", "TSSE": "encodersettings",
    "TDRC": "date", "TYER": "date", "TDOR": "originaldate", "TORY": "originalyear",
    "TSST": "discsubtitle", "TMOO": "mood", "TOAL": "originalalbum",
    "TOPE": "originalartist", "TDES": "podcastdesc", "TGID": "podcastid",
    "TCAT": "podcastcategory", "TKWD": "podcastkeywords", "WFED": "podcasturl",
}
MP4 = {
    "©nam": "title", "©ART": "artist", "©alb": "album", "aART": "albumartist",
    "©gen": "genre", "©wrt": "composer", "©day": "date", "©cmt": "comment",
    "©grp": "grouping", "©lyr": "lyrics", "soar": "artistsort", "soaa": "albumartistsort",
    "soal": "albumsort", "sonm": "titlesort", "soco": "composersort", "tmpo": "bpm",
    "cpil": "compilation", "cprt": "copyright", "©too": "encodedby", "desc": "podcastdesc",
    "catg": "podcastcategory", "keyw": "podcastkeywords", "purl": "podcasturl",
    "egid": "podcastid", "pcst": "podcast", "tvsh": "show", "©wrk": "work",
    "©mvn": "movement",
}
APE = {
    "title": "title", "artist": "artist", "album": "album", "album artist": "albumartist",
    "albumartist": "albumartist", "year": "date", "genre": "genre", "composer": "composer",
    "comment": "comment", "lyrics": "lyrics",
}
ASF = {
    "Title": "title", "Author": "artist", "WM/AlbumTitle": "album",
    "WM/AlbumArtist": "albumartist", "WM/Year": "date", "WM/Genre": "genre",
    "WM/Composer": "composer", "WM/Lyrics": "lyrics", "Description": "comment",
    "Copyright": "copyright", "WM/Publisher": "label", "WM/BeatsPerMinute": "bpm",
    "WM/ISRC": "isrc", "WM/Mood": "mood",
}
VORBIS_ALIASES = {
    "totaltracks": "totaltracks", "tracktotal": "totaltracks", "totaldiscs": "totaldiscs",
    "disctotal": "totaldiscs", "organization": "label", "description": "comment",
    "unsyncedlyrics": "lyrics", "album artist": "albumartist", "year": "date",
    "encoded-by": "encodedby",
}
ID3V1 = {"title": "title", "artist": "artist", "album": "album", "year": "date",
         "comment": "comment", "track": "tracknumber", "genre": "genre"}


def _text(entry: TagEntry, sep: str = "; ") -> str:
    """Content of an entry as text (multi-values joined like Picard does)."""
    for f in entry.fields:
        if f.name in ("text", "values", "value", "url", "data") or f.name == "people":
            if f.ftype == FieldType.TEXT_LIST:
                return sep.join(str(v) for v in f.value)
            if f.ftype == FieldType.PAIR_LIST:
                return sep.join(f"{a}/{b}" if b else str(a) for a, b in f.value)
            if f.ftype == FieldType.INT_LIST:
                return sep.join(str(v) for v in f.value)
            if f.ftype == FieldType.BOOL:
                return "1" if f.value else ""
            if f.ftype == FieldType.CHOICE and entry.system == "ID3v1":
                return format_value(f).split(": ", 1)[-1] if f.value != 255 else ""
            if f.ftype in (FieldType.BYTES, FieldType.PICTURES, FieldType.OPAQUE):
                return ""
            return "" if f.value is None else str(f.value)
    return ""


def _split_pair(value: str) -> tuple[str, str]:
    num, _, total = value.partition("/")
    return num.strip(), total.strip()


def _names_for(entry: TagEntry) -> list[str]:
    """Picard variable names an entry feeds (possibly several, possibly none)."""
    s, k = entry.system, entry.key
    if s == "ID3v2":
        fid = entry.frame_id
        if fid in ("TRCK",):
            return ["_pair:tracknumber:totaltracks"]
        if fid in ("TPOS",):
            return ["_pair:discnumber:totaldiscs"]
        if fid == "COMM":
            return ["comment"] if not entry.get("desc") else [f"comment:{entry.get('desc')}".lower()]
        if fid == "USLT":
            return ["lyrics"]
        if fid in ("TXXX", "WXXX"):
            return [str(entry.get("desc", "")).lower()]
        return [ID3[fid]] if fid in ID3 else []
    if s == "MP4":
        if k == "trkn":
            return ["_pair:tracknumber:totaltracks"]
        if k == "disk":
            return ["_pair:discnumber:totaldiscs"]
        if k.startswith("----:"):
            return [k.split(":", 2)[-1].lower()]
        return [MP4[k]] if k in MP4 else []
    if s == "Vorbis":
        if k.startswith("<") or entry.frame_id == "METADATA_BLOCK_PICTURE":
            return []
        low = k.lower()
        if low in ("tracknumber", "discnumber"):
            total = "totaltracks" if low == "tracknumber" else "totaldiscs"
            return [f"_pair:{low}:{total}"]
        return [VORBIS_ALIASES.get(low, low)]
    if s == "APEv2":
        low = k.lower()
        if low == "track":
            return ["_pair:tracknumber:totaltracks"]
        if low == "disc":
            return ["_pair:discnumber:totaldiscs"]
        return [APE.get(low, low)]
    if s == "ASF":
        if k == "WM/TrackNumber":
            return ["_pair:tracknumber:totaltracks"]
        if k == "WM/PartOfSet":
            return ["_pair:discnumber:totaldiscs"]
        if k in ASF:
            return [ASF[k]]
        return [k.split("/", 1)[-1].lower()] if k.startswith("WM/") else [k.lower()]
    if s == "ID3v1":
        return [ID3V1[k]] if k in ID3V1 else []
    return []


def build_variables(ft: FileTags, entries: list[TagEntry] | None = None) -> dict[str, str]:
    """Variables for one file. ``entries`` defaults to the file's saved tags;
    pass the working (edited) entries to preview pending changes."""
    entries = ft.entries if entries is None else entries
    out: dict[str, str] = {}

    def put(name: str, value: str) -> None:
        if name and value != "" and name not in out:
            out[name] = value

    for e in entries:
        value = _text(e)
        out.setdefault(f"_raw:{e.key}".lower(), value)
        for name in _names_for(e):
            if name.startswith("_pair:"):
                _, num_name, total_name = name.split(":")
                num, total = _split_pair(value)
                put(num_name, num)
                put(total_name, total)
            else:
                put(name, value)

    if "date" in out:
        out.setdefault("year", out["date"][:4])
    if "originaldate" in out:
        out.setdefault("originalyear", out["originaldate"][:4])
    artist, albumartist = out.get("artist", ""), out.get("albumartist", "")
    if albumartist and artist and artist != albumartist:
        out["_multiartist"] = "1"

    # file/technical variables (Picard names)
    name = os.path.basename(ft.path)
    stem, ext = os.path.splitext(name)
    out["_filename"] = stem
    out["_extension"] = ext.lstrip(".").lower()
    out["_dirname"] = os.path.basename(os.path.dirname(ft.path))
    out["_format"] = ft.format_name
    info = ft.info
    if info.get("length"):
        m, sec = divmod(int(info["length"]), 60)
        out["_length"] = f"{m}:{sec:02d}"
    for src, dst in (("bitrate", "_bitrate"), ("sample_rate", "_sample_rate"),
                     ("channels", "_channels"), ("bits_per_sample", "_bits_per_sample")):
        if info.get(src):
            v = info[src]
            out[dst] = str(v // 1000 if src == "bitrate" else v)
    return out


# Shown in the naming dialog's variable list.
COMMON_VARIABLES = [
    "title", "artist", "album", "albumartist", "tracknumber", "totaltracks", "discnumber",
    "totaldiscs", "date", "year", "genre", "composer", "comment", "artistsort",
    "albumartistsort", "bpm", "label", "isrc", "compilation", "_multiartist", "_filename",
    "_extension", "_dirname", "_format", "_length", "_bitrate", "_raw:<native key>",
]
