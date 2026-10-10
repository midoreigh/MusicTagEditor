"""ASF / WMA attributes."""

from __future__ import annotations

from mutagen.asf import ASFBaseAttribute

from ..model import Field, FieldType, Kind, TagEntry
from .base import Adapter, TagError

UNICODE, BYTEARRAY, BOOL, DWORD, QWORD, WORD, GUID = range(7)
TYPE_CHOICES = [(UNICODE, "Unicode string"), (BYTEARRAY, "Byte array"), (BOOL, "Bool"),
                (DWORD, "DWORD (32-bit)"), (QWORD, "QWORD (64-bit)"), (WORD, "WORD (16-bit)"),
                (GUID, "GUID")]
_NUMERIC = {BOOL, DWORD, QWORD, WORD}
_BINARY = {BYTEARRAY, GUID}

DESCRIPTIONS = {
    "Title": "Title", "Author": "Artist", "Copyright": "Copyright",
    "Description": "Description", "Rating": "Rating", "WM/AlbumTitle": "Album",
    "WM/AlbumArtist": "Album artist", "WM/TrackNumber": "Track number",
    "WM/PartOfSet": "Disc number", "WM/Year": "Year", "WM/Genre": "Genre",
    "WM/Composer": "Composer", "WM/Lyrics": "Lyrics", "WM/Picture": "Picture",
    "WM/Publisher": "Publisher", "WM/EncodedBy": "Encoded by",
    "WM/ToolName": "Encoding tool", "WM/MediaClassPrimaryID": "Media class",
    "WM/Mood": "Mood", "WM/BeatsPerMinute": "BPM", "WM/ISRC": "ISRC",
}


def entry_for(key: str, values: list) -> TagEntry:
    types = {v.TYPE for v in values}
    vtype = values[0].TYPE if len(types) == 1 else UNICODE
    readonly = len(types) > 1
    fields = [Field("key", FieldType.TEXT, key, "Attribute name"),
              Field("value_type", FieldType.CHOICE, vtype, "Value type", TYPE_CHOICES,
                    readonly=vtype in _BINARY)]
    if readonly:
        fields.append(Field("values", FieldType.OPAQUE, [v.value for v in values], readonly=True))
        kind = Kind.OTHER
    elif vtype in _BINARY:
        if len(values) == 1:
            fields.append(Field("data", FieldType.BYTES, bytes(values[0].value), "Data"))
        else:
            fields.append(Field("data", FieldType.OPAQUE, [bytes(v.value) for v in values],
                                readonly=True))
            readonly = True
        kind = Kind.PICTURE if key == "WM/Picture" else Kind.BINARY
    elif vtype in _NUMERIC:
        fields.append(Field("values", FieldType.INT_LIST, [int(v.value) for v in values],
                            "Values (bool: 0/1)"))
        kind = Kind.NUMBER
    else:
        fields.append(Field("values", FieldType.TEXT_LIST, [str(v.value) for v in values],
                            "Values"))
        kind = Kind.TEXT
    extras = [(v.language, v.stream) for v in values]
    if any(x != (None, None) for x in extras):
        fields.append(Field("lang_stream", FieldType.OPAQUE, extras,
                            "Language / stream index", readonly=True))
    return TagEntry(ASFAdapter.system, key, key, kind, fields,
                    description=DESCRIPTIONS.get(key, ""), readonly=readonly, editable_key=True)


def values_for(entry: TagEntry) -> list:
    vtype = int(entry.get("value_type", UNICODE))
    cls = ASFBaseAttribute._get_type(vtype)
    extras = entry.get("lang_stream") or []
    if vtype in _BINARY:
        raw = [entry.get("data", b"")]
    elif vtype == BOOL:
        raw = [bool(int(v)) for v in entry.get("values", [])]
    elif vtype in _NUMERIC:
        raw = [int(v) for v in entry.get("values", [])]
    else:
        raw = [str(v) for v in entry.get("values", [])]
    out = []
    for i, v in enumerate(raw):
        lang, stream = extras[i] if i < len(extras) else (None, None)
        try:
            out.append(cls(value=v, language=lang, stream=stream))
        except (TypeError, ValueError) as e:
            raise TagError(f"{entry.key}: {e}") from e
    return out


class ASFAdapter(Adapter):
    system = "ASF"
    label = "ASF attributes"

    def __init__(self, audio) -> None:
        super().__init__()
        self.audio = audio

    def read(self) -> list[TagEntry]:
        tags = self.audio.tags
        if tags is None:
            return []
        groups: dict[str, list] = {}
        for k, v in tags:
            groups.setdefault(k, []).append(v)
        return [entry_for(k, vs) for k, vs in groups.items()]

    @staticmethod
    def key_of(entry: TagEntry) -> str:
        key = entry.get("key", entry.key)
        if not key:
            raise TagError("Attribute name can't be empty")
        return key

    def delete(self, key: str, missing_ok: bool = False) -> None:
        tags = self.audio.tags
        if tags is None or key not in tags:
            if missing_ok:
                return
            raise TagError(f"No attribute {key!r}")
        del tags[key]

    def set(self, entry: TagEntry) -> None:
        if self.audio.tags is None:
            self.audio.add_tags()
        key = self.key_of(entry)
        values = values_for(entry)
        if key in self.audio.tags:
            del self.audio.tags[key]
        self.audio.tags[key] = values

    def save(self) -> None:
        self.audio.save()

    def templates(self) -> list[TagEntry]:
        from mutagen.asf import ASFUnicodeAttribute
        return [entry_for(k, [ASFUnicodeAttribute("")]) for k in sorted(DESCRIPTIONS)
                if k != "WM/Picture"]
