"""Vorbis comments (FLAC, Ogg Vorbis/Opus/FLAC/Speex) and FLAC picture blocks.

Comments are kept as the ordered raw ``(KEY, value)`` list (original key case
preserved) and grouped per key case-insensitively for display.
"""

from __future__ import annotations

import base64

from mutagen.flac import Picture as FlacPicture

from ..model import Field, FieldType, Kind, TagEntry
from .base import PICTURE_TYPE_CHOICES, Adapter, TagError, sniff_mime

VENDOR_KEY = "<vendor>"
MBP = "METADATA_BLOCK_PICTURE"

DESCRIPTIONS = {
    "TITLE": "Title", "ARTIST": "Artist", "ALBUM": "Album", "ALBUMARTIST": "Album artist",
    "DATE": "Date", "GENRE": "Genre", "TRACKNUMBER": "Track number",
    "TRACKTOTAL": "Track total", "TOTALTRACKS": "Track total", "DISCNUMBER": "Disc number",
    "DISCTOTAL": "Disc total", "TOTALDISCS": "Disc total", "COMMENT": "Comment",
    "DESCRIPTION": "Description", "COMPOSER": "Composer", "PERFORMER": "Performer",
    "LYRICS": "Lyrics", "UNSYNCEDLYRICS": "Lyrics", "ISRC": "ISRC",
    "COPYRIGHT": "Copyright", "LICENSE": "License", "ORGANIZATION": "Label",
    "LABEL": "Label", "ENCODER": "Encoder", "ENCODED-BY": "Encoded by",
    "REPLAYGAIN_TRACK_GAIN": "ReplayGain track gain",
    "REPLAYGAIN_TRACK_PEAK": "ReplayGain track peak",
    "REPLAYGAIN_ALBUM_GAIN": "ReplayGain album gain",
    "REPLAYGAIN_ALBUM_PEAK": "ReplayGain album peak", "BPM": "BPM",
    "MUSICBRAINZ_TRACKID": "MusicBrainz recording id",
    "MUSICBRAINZ_ALBUMID": "MusicBrainz release id",
    "MUSICBRAINZ_ARTISTID": "MusicBrainz artist id", MBP: "Picture (base64 FLAC block)",
}


def valid_key(key: str) -> bool:
    return bool(key) and all(0x20 <= ord(c) <= 0x7D and c != "=" for c in key)


def picture_fields(pic: FlacPicture) -> list[Field]:
    return [
        Field("type", FieldType.CHOICE, int(pic.type), "Picture type", PICTURE_TYPE_CHOICES),
        Field("mime", FieldType.TEXT, pic.mime, "MIME type"),
        Field("desc", FieldType.TEXT, pic.desc, "Description"),
        Field("width", FieldType.INT, pic.width, "Width"),
        Field("height", FieldType.INT, pic.height, "Height"),
        Field("depth", FieldType.INT, pic.depth, "Colour depth"),
        Field("colors", FieldType.INT, pic.colors, "Indexed colours"),
        Field("data", FieldType.BYTES, bytes(pic.data), "Image data"),
    ]


def picture_from_entry(entry: TagEntry) -> FlacPicture:
    pic = FlacPicture()
    pic.type = int(entry.get("type", 3))
    pic.data = bytes(entry.get("data", b""))
    pic.mime = entry.get("mime") or sniff_mime(pic.data, "image/jpeg")
    pic.desc = entry.get("desc", "")
    pic.width = int(entry.get("width", 0))
    pic.height = int(entry.get("height", 0))
    pic.depth = int(entry.get("depth", 0))
    pic.colors = int(entry.get("colors", 0))
    return pic


class VorbisAdapter(Adapter):
    system = "Vorbis"
    label = "Vorbis comments"

    def __init__(self, audio) -> None:
        super().__init__()
        self.audio = audio
        tags = audio.tags
        self.items: list[list[str] | None] = [[k, v] for k, v in tags] if tags is not None else []
        self.vendor = tags.vendor if tags is not None else ""

    # --- helpers --------------------------------------------------------
    def _groups(self) -> dict[str, tuple[str, list[str]]]:
        """lower key -> (display key, values) in file order."""
        groups: dict[str, tuple[str, list[str]]] = {}
        for item in self.items:
            if item is None or item[0].upper() == MBP:
                continue
            k, v = item
            groups.setdefault(k.lower(), (k, []))[1].append(v)
        return groups

    def _picture_items(self) -> list[int]:
        return [i for i, it in enumerate(self.items) if it is not None and it[0].upper() == MBP]

    # --- Adapter API ----------------------------------------------------
    def read(self) -> list[TagEntry]:
        out = [TagEntry(self.system, VENDOR_KEY, "VENDOR", Kind.TEXT,
                        [Field("value", FieldType.TEXT, self.vendor, "Vendor string")],
                        description="Encoder vendor string (part of the comment header)")]
        for lower, (key, values) in self._groups().items():
            multiline = key.upper() in ("LYRICS", "UNSYNCEDLYRICS", "COMMENT", "DESCRIPTION")
            out.append(TagEntry(
                self.system, key, key.upper(), Kind.TEXT,
                [Field("key", FieldType.TEXT, key, "Field name"),
                 Field("values", FieldType.TEXT_LIST, values,
                       "Values" + (" (multi-line)" if multiline else ""))],
                description=DESCRIPTIONS.get(key.upper(), ""), editable_key=True))
        for n, idx in enumerate(self._picture_items()):
            raw = self.items[idx][1]
            try:
                pic = FlacPicture(base64.b64decode(raw))
                fields = picture_fields(pic)
                ro = False
            except Exception:
                fields = [Field("data", FieldType.TEXT, raw, "Undecodable value", readonly=True)]
                ro = True
            out.append(TagEntry(self.system, f"{MBP}#{n}", MBP, Kind.PICTURE, fields,
                                description=DESCRIPTIONS[MBP], readonly=ro))
        return out

    @staticmethod
    def key_of(entry: TagEntry) -> str:
        if entry.frame_id in ("VENDOR", MBP):
            return entry.key
        key = entry.get("key", entry.key)
        if not valid_key(key):
            raise TagError(f"Invalid Vorbis field name {key!r} (ASCII 0x20-0x7D, no '=')")
        return key

    def delete(self, key: str, missing_ok: bool = False) -> None:
        if key == VENDOR_KEY:
            self.vendor = ""
            return
        if key.startswith(MBP + "#"):
            n = int(key.split("#", 1)[1])
            idxs = self._picture_items()
            if n < len(idxs):
                self.items[idxs[n]] = None
            elif not missing_ok:
                raise TagError(f"No picture {key}")
            return
        found = False
        for i, item in enumerate(self.items):
            if item is not None and item[0].lower() == key.lower():
                self.items[i] = None
                found = True
        if not found and not missing_ok:
            raise TagError(f"No field {key!r}")

    def set(self, entry: TagEntry) -> None:
        if entry.key == VENDOR_KEY:
            self.vendor = str(entry.get("value", ""))
            return
        if entry.frame_id == MBP:
            data = base64.b64encode(picture_from_entry(entry).write()).decode("ascii")
            n = entry.key.split("#", 1)[1] if "#" in entry.key else "new"
            idxs = self._picture_items()
            if n.isdigit() and int(n) < len(idxs):
                self.items[idxs[int(n)]][1] = data
            else:
                self.items.append([MBP, data])
            return
        key = self.key_of(entry)
        values = [str(v) for v in entry.get("values", [])]
        first = None
        for i, item in enumerate(self.items):
            if item is not None and item[0].lower() == key.lower():
                if first is None:
                    first = i
                self.items[i] = None
        new = [[key, v] for v in values]
        if first is None:
            self.items.extend(new)
        else:
            self.items[first:first] = new

    def save(self) -> None:
        if self.audio.tags is None:
            self.audio.add_tags()
        tags = self.audio.tags
        del tags[:]
        tags.extend((k, v) for k, v in (it for it in self.items if it is not None))
        tags.vendor = self.vendor
        self.audio.save()

    def templates(self) -> list[TagEntry]:
        out = []
        for key in sorted(set(DESCRIPTIONS) - {MBP}):
            out.append(TagEntry(self.system, key, key, Kind.TEXT,
                                [Field("key", FieldType.TEXT, key, "Field name"),
                                 Field("values", FieldType.TEXT_LIST, [], "Values")],
                                description=DESCRIPTIONS[key], editable_key=True))
        pic = FlacPicture()
        pic.type = 3
        out.append(TagEntry(self.system, f"{MBP}#new", MBP, Kind.PICTURE, picture_fields(pic),
                            description=DESCRIPTIONS[MBP]))
        return out


class FlacPictureAdapter(Adapter):
    """FLAC METADATA_BLOCK_PICTURE blocks (not part of the Vorbis comment)."""

    system = "FLAC"
    label = "FLAC picture blocks"

    def __init__(self, audio) -> None:
        super().__init__()
        self.audio = audio
        self.pictures: list[FlacPicture | None] = list(audio.pictures)

    def read(self) -> list[TagEntry]:
        return [TagEntry(self.system, f"PICTURE#{i}", "PICTURE", Kind.PICTURE,
                         picture_fields(p), description="FLAC picture block")
                for i, p in enumerate(self.pictures) if p is not None]

    def delete(self, key: str, missing_ok: bool = False) -> None:
        n = key.split("#", 1)[1]
        if n.isdigit() and int(n) < len(self.pictures):
            self.pictures[int(n)] = None
        elif not missing_ok:
            raise TagError(f"No picture {key}")

    def set(self, entry: TagEntry) -> None:
        pic = picture_from_entry(entry)
        n = entry.key.split("#", 1)[1]
        if n.isdigit() and int(n) < len(self.pictures):
            self.pictures[int(n)] = pic
        else:
            self.pictures.append(pic)

    def save(self) -> None:
        self.audio.clear_pictures()
        for p in self.pictures:
            if p is not None:
                self.audio.add_picture(p)
        self.audio.save()

    def templates(self) -> list[TagEntry]:
        pic = FlacPicture()
        pic.type = 3
        return [TagEntry(self.system, "PICTURE#new", "PICTURE", Kind.PICTURE,
                         picture_fields(pic), description="FLAC picture block")]
