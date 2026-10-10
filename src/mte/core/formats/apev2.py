"""APEv2 tags (Monkey's Audio, WavPack, Musepack, ... and APE tags on MP3)."""

from __future__ import annotations

from mutagen.apev2 import BINARY, EXTERNAL, TEXT, APEValue, is_valid_apev2_key

from ..model import Field, FieldType, Kind, TagEntry
from .base import Adapter, TagError

KIND_CHOICES = [(TEXT, "Text (UTF-8)"), (BINARY, "Binary"), (EXTERNAL, "External (URL)")]

DESCRIPTIONS = {
    "Title": "Title", "Artist": "Artist", "Album": "Album", "Album Artist": "Album artist",
    "Year": "Year", "Track": "Track", "Disc": "Disc", "Genre": "Genre",
    "Comment": "Comment", "Composer": "Composer", "Lyrics": "Lyrics",
    "Cover Art (Front)": "Front cover (filename\\0data)",
    "Cover Art (Back)": "Back cover (filename\\0data)",
    "REPLAYGAIN_TRACK_GAIN": "ReplayGain track gain",
    "REPLAYGAIN_TRACK_PEAK": "ReplayGain track peak",
}


def entry_for(key: str, value) -> TagEntry:
    fields = [Field("key", FieldType.TEXT, key, "Item key"),
              Field("type", FieldType.CHOICE, value.kind, "Item type", KIND_CHOICES)]
    if value.kind == TEXT:
        fields.append(Field("values", FieldType.TEXT_LIST, list(value), "Values"))
        kind = Kind.TEXT
    elif value.kind == EXTERNAL:
        fields.append(Field("url", FieldType.TEXT, value.value, "URL"))
        kind = Kind.URL
    else:
        fields.append(Field("data", FieldType.BYTES, bytes(value.value), "Data"))
        kind = Kind.PICTURE if key.lower().startswith("cover art") else Kind.BINARY
    fields[1].readonly = True  # changing the type would need a different payload field
    return TagEntry(APEv2Adapter.system, key, key, kind, fields,
                    description=DESCRIPTIONS.get(key, ""), editable_key=True)


class APEv2Adapter(Adapter):
    system = "APEv2"
    label = "APEv2"

    def __init__(self, tags, save_fn, create_fn=None) -> None:
        super().__init__()
        self._tags = tags
        self._save_fn = save_fn
        self._create_fn = create_fn

    @property
    def tags(self):
        if self._tags is None:
            if self._create_fn is None:
                raise TagError("This file can't hold APEv2 tags")
            self._tags = self._create_fn()
        return self._tags

    def read(self) -> list[TagEntry]:
        if self._tags is None:
            return []
        return [entry_for(k, v) for k, v in self._tags.items()]

    @staticmethod
    def key_of(entry: TagEntry) -> str:
        key = entry.get("key", entry.key)
        if not is_valid_apev2_key(key):
            raise TagError(f"Invalid APEv2 key {key!r} (2-255 ASCII chars, not ID3/TAG/OggS/MP+)")
        return key

    def delete(self, key: str, missing_ok: bool = False) -> None:
        if self._tags is None or key not in self._tags:
            if missing_ok:
                return
            raise TagError(f"No APEv2 item {key!r}")
        del self._tags[key]

    def set(self, entry: TagEntry) -> None:
        key = self.key_of(entry)
        kind = int(entry.get("type", TEXT))
        if kind == TEXT:
            value = APEValue("\0".join(str(v) for v in entry.get("values", [])), TEXT)
        elif kind == EXTERNAL:
            value = APEValue(str(entry.get("url", "")), EXTERNAL)
        else:
            value = APEValue(bytes(entry.get("data", b"")), BINARY)
        self.tags[key] = value

    def save(self) -> None:
        if self._tags is None:
            return
        self._save_fn(self._tags)

    def templates(self) -> list[TagEntry]:
        return [entry_for(k, APEValue("", TEXT)) for k in DESCRIPTIONS
                if not k.startswith("Cover")] + \
            [entry_for("Cover Art (Front)", APEValue(b"cover.jpg\0", BINARY))]
