"""ID3v2 (every frame, generically via mutagen's frame specs) and ID3v1."""

from __future__ import annotations

import os
import struct

from mutagen._constants import GENRES
from mutagen.id3 import Frames, ID3
from mutagen.id3 import _specs as S

from ..model import Field, FieldType, Kind, TagEntry
from .base import PICTURE_TYPE_CHOICES, Adapter, TagError

ENCODING_CHOICES = [(0, "Latin-1"), (1, "UTF-16"), (2, "UTF-16BE"), (3, "UTF-8")]

# Specs we know how to turn into editable fields. Anything else is carried
# through as an OPAQUE (read-only) value so the frame survives a rebuild.
_TEXTY = (S.EncodedTextSpec, S.Latin1TextSpec)

MULTILINE_FRAMES = {"USLT", "COMM", "USER"}


def frame_description(frame_id: str) -> str:
    cls = Frames.get(frame_id)
    doc = (cls.__doc__ or "").strip().splitlines() if cls else []
    return doc[0].rstrip(".") if doc else ""


def _kind_for(frame_id: str) -> Kind:
    if frame_id in ("APIC", "PIC"):
        return Kind.PICTURE
    if frame_id in ("COMM", "USLT", "SYLT", "USER"):
        return Kind.COMMENT
    if frame_id.startswith("W"):
        return Kind.URL
    if frame_id.startswith("T"):
        return Kind.TEXT
    if frame_id in ("PCST", "PCNT", "POPM"):
        return Kind.NUMBER
    if frame_id in ("PRIV", "GEOB", "UFID", "MCDI", "SIGN", "ENCR", "GRID"):
        return Kind.BINARY
    return Kind.OTHER


LABELS = {"data": "Data", "owner": "Owner", "email": "Email", "rating": "Rating (0-255)",
          "count": "Play count", "value": "Value", "filename": "File name", "url": "URL",
          "desc": "Description", "mime": "MIME type", "lang": "Language", "text": "Text",
          "element_id": "Element id", "start_time": "Start (ms)", "end_time": "End (ms)",
          "start_offset": "Start offset", "end_offset": "End offset", "sub_frames": "Sub-frames",
          "people": "People", "format": "Format", "type": "Type", "events": "Events",
          "frameid": "Frame id", "price": "Price", "seller": "Seller", "valid_until": "Valid until",
          "contact": "Contact", "method": "Method", "group": "Group", "counter": "Counter",
          "offset": "Offset", "size": "Size", "flags": "Flags"}


def _spec_field(frame_id: str, spec, value) -> Field:
    f = _spec_field_raw(frame_id, spec, value)
    if not f.label:
        f.label = LABELS.get(f.name, f.name.replace("_", " ").capitalize())
    return f


def _spec_field_raw(frame_id: str, spec, value) -> Field:
    name = spec.name
    if isinstance(spec, S.EncodingSpec):
        return Field(name, FieldType.CHOICE, int(value) if value is not None else 3,
                     "Encoding", ENCODING_CHOICES)
    if isinstance(spec, S.PictureTypeSpec):
        return Field(name, FieldType.CHOICE, int(value), "Picture type", PICTURE_TYPE_CHOICES)
    if isinstance(spec, (S.ByteSpec, S.IntegerSpec, S.SizedIntegerSpec)):
        return Field(name, FieldType.INT, int(value) if value is not None else 0)
    if isinstance(spec, S.StringSpec):
        if name == "lang":
            return Field(name, FieldType.LANG, value, "Language")
        return Field(name, FieldType.TEXT, value)
    if isinstance(spec, S.BinaryDataSpec):
        return Field(name, FieldType.BYTES, bytes(value or b""))
    if isinstance(spec, _TEXTY) and not isinstance(spec, S.SynchronizedTextSpec):
        ftype = FieldType.MULTILINE if (frame_id in MULTILINE_FRAMES and name == "text") \
            else FieldType.TEXT
        label = {"desc": "Description", "url": "URL", "mime": "MIME type",
                 "owner": "Owner"}.get(name, "")
        return Field(name, ftype, str(value) if value is not None else "", label)
    if isinstance(spec, S.MultiSpec):
        subs = spec.specs
        if len(subs) == 1 and isinstance(subs[0], _TEXTY):
            ftype = FieldType.TEXT_LIST
            if frame_id in MULTILINE_FRAMES:
                ftype = FieldType.TEXT_LIST
            return Field(name, ftype, [str(v) for v in (value or [])],
                         "URLs" if frame_id == "WXXX" else "Values")
        if len(subs) == 2 and all(isinstance(s, _TEXTY) for s in subs):
            return Field(name, FieldType.PEOPLE, [tuple(map(str, v)) for v in (value or [])],
                         "Involvement / Person")
    return Field(name, FieldType.OPAQUE, value, readonly=True)


def _specs(cls):
    return list(cls._framespec) + list(cls._optionalspec)


def entry_from_frame(frame) -> TagEntry:
    fid = frame.FrameID
    fields = []
    for spec in _specs(type(frame)):
        if not hasattr(frame, spec.name):
            continue  # optional spec not present
        fields.append(_spec_field(fid, spec, getattr(frame, spec.name)))
    readonly = all(f.readonly for f in fields if f.name != "encoding") and bool(fields)
    return TagEntry(
        system=ID3v2Adapter.system,
        key=frame.HashKey,
        frame_id=fid,
        kind=_kind_for(fid),
        fields=fields,
        description=frame_description(fid),
        readonly=readonly,
        editable_key=any(f.name in ("desc", "lang", "owner", "email", "element_id")
                         for f in fields),
    )


def frame_from_entry(entry: TagEntry):
    cls = Frames.get(entry.frame_id)
    if cls is None:
        raise TagError(f"Unknown ID3 frame id {entry.frame_id!r}")
    kwargs = {}
    for f in entry.fields:
        v = f.value
        if f.ftype == FieldType.PEOPLE:
            v = [list(p) for p in v]
        elif f.ftype == FieldType.TEXT_LIST:
            v = [str(x) for x in v]
        kwargs[f.name] = v
    try:
        return cls(**kwargs)
    except (ValueError, TypeError) as e:
        raise TagError(f"{entry.frame_id}: invalid value ({e})") from e


def blank_frame_entry(frame_id: str, v2_minor: int = 4) -> TagEntry:
    cls = Frames[frame_id]
    kwargs = {}
    for spec in cls._framespec:
        if isinstance(spec, S.EncodingSpec):
            kwargs[spec.name] = 3 if v2_minor == 4 else 1
        elif isinstance(spec, S.MultiSpec):
            kwargs[spec.name] = []
        elif isinstance(spec, S.StringSpec) and spec.name == "lang":
            kwargs[spec.name] = "eng"
        elif isinstance(spec, S.BinaryDataSpec):
            kwargs[spec.name] = b""
        elif isinstance(spec, S.PictureTypeSpec):
            kwargs[spec.name] = 3
        elif isinstance(spec, (S.ByteSpec, S.IntegerSpec, S.SizedIntegerSpec)):
            kwargs[spec.name] = 0
        elif isinstance(spec, _TEXTY):
            kwargs[spec.name] = ""
    frame = cls(**kwargs)
    return entry_from_frame(frame)


UNKNOWN_PREFIX = "<unparsed>"


class ID3v2Adapter(Adapter):
    system = "ID3v2"

    def __init__(self, audio) -> None:
        super().__init__()
        self.audio = audio
        tags = audio.tags
        self.created = False
        if tags is not None and tags.version < (2, 3, 0):
            # v2.2 frames (3-char ids) can't be written back, convert to v2.4
            tags.update_to_v24()
            self.save_version = 4
            self.note = "ID3v2.2 (will be saved as v2.4)"
        elif tags is not None:
            self.save_version = tags.version[1]
            self.note = f"ID3v2.{tags.version[1]}"
        else:
            self.save_version = 4
            self.note = "none"
        self.label = "ID3v2" if tags is None else f"ID3v2.{self.save_version}"

    @property
    def tags(self) -> ID3:
        if self.audio.tags is None:
            self.audio.add_tags()
            self.created = True
        return self.audio.tags

    def read(self) -> list[TagEntry]:
        tags = self.audio.tags
        if tags is None:
            return []
        entries = [entry_from_frame(f) for f in tags.values()]
        for i, raw in enumerate(getattr(tags, "unknown_frames", []) or []):
            fid = raw[:4].decode("latin-1", "replace")
            entries.append(TagEntry(
                system=self.system,
                key=f"{UNKNOWN_PREFIX}{i}:{fid}",
                frame_id=fid,
                kind=Kind.BINARY,
                fields=[Field("data", FieldType.BYTES, bytes(raw[10:]), "Raw frame body",
                              readonly=True)],
                description="Frame mutagen couldn't parse (kept as-is)",
                readonly=True,
            ))
        return entries

    @staticmethod
    def key_of(entry: TagEntry) -> str:
        if entry.key.startswith(UNKNOWN_PREFIX):
            return entry.key
        return frame_from_entry(entry).HashKey

    def delete(self, key: str, missing_ok: bool = False) -> None:
        tags = self.audio.tags
        if key.startswith(UNKNOWN_PREFIX):
            idx = int(key[len(UNKNOWN_PREFIX):].split(":", 1)[0])
            # mark as removed (keep indexes stable during a batch of ops)
            if tags is not None and idx < len(tags.unknown_frames):
                tags.unknown_frames[idx] = b""
            return
        if tags is None or key not in tags:
            if missing_ok:
                return
            raise TagError(f"No frame {key!r}")
        del tags[key]

    def set(self, entry: TagEntry) -> None:
        frame = frame_from_entry(entry)
        tags = self.tags
        tags.delall(frame.HashKey)
        tags.add(frame)

    def save(self) -> None:
        tags = self.audio.tags
        if tags is None:
            return
        # drop unknown frames that were deleted (mutagen skips data <= 10 bytes)
        tags.unknown_frames = [f for f in tags.unknown_frames if len(f) > 10]
        if len(tags) == 0 and not tags.unknown_frames:
            self.audio.delete()  # remove the whole (now empty) ID3v2 tag
            return
        if self.save_version == 3:
            self.audio.save(v2_version=3, v1=1)
        else:
            self.audio.save(v2_version=4, v1=1)

    def templates(self) -> list[TagEntry]:
        out = []
        for fid in sorted(Frames):
            try:
                out.append(blank_frame_entry(fid, self.save_version))
            except Exception:
                continue
        return out


# ---------------------------------------------------------------------------
# ID3v1 (last 128 bytes of the file). Handled by hand so the raw v1 contents
# stay visible separately instead of being merged into the v2 frames.

V1_LAYOUT = [("title", 30), ("artist", 30), ("album", 30), ("year", 4), ("comment", 30)]
GENRE_CHOICES = [(i, f"{i}: {g}") for i, g in enumerate(GENRES[:192])] + [(255, "255: (none)")]
V1_DESCRIPTIONS = {"title": "Title", "artist": "Artist", "album": "Album", "year": "Year",
                   "comment": "Comment", "track": "Track (ID3v1.1)", "genre": "Genre"}


def parse_id3v1(block: bytes) -> dict | None:
    if len(block) != 128 or block[:3] != b"TAG":
        return None
    out: dict = {}
    pos = 3
    for name, size in V1_LAYOUT:
        raw = block[pos:pos + size]
        pos += size
        if name == "comment" and raw[28] == 0 and raw[29] != 0:
            out["track"] = raw[29]
            raw = raw[:28]
        out[name] = raw.split(b"\x00", 1)[0].decode("latin-1").rstrip(" ")
    out.setdefault("track", 0)
    out["genre"] = block[127]
    return out


def build_id3v1(values: dict) -> bytes:
    def enc(s: str, size: int) -> bytes:
        return s.encode("latin-1", "replace")[:size].ljust(size, b"\x00")

    track = int(values.get("track") or 0)
    comment = enc(values.get("comment", ""), 28 if track else 30)
    if track:
        comment += b"\x00" + struct.pack("B", track & 0xFF)
    return (b"TAG" + enc(values.get("title", ""), 30) + enc(values.get("artist", ""), 30)
            + enc(values.get("album", ""), 30) + enc(values.get("year", ""), 4) + comment
            + struct.pack("B", int(values.get("genre", 255)) & 0xFF))


class ID3v1Adapter(Adapter):
    system = "ID3v1"
    label = "ID3v1"

    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = path
        self.original = self._read_block()
        self.values = parse_id3v1(self.original) if self.original else None

    def _read_block(self) -> bytes | None:
        with open(self.path, "rb") as f:
            f.seek(0, os.SEEK_END)
            if f.tell() < 128:
                return None
            f.seek(-128, os.SEEK_END)
            block = f.read(128)
        return block if block[:3] == b"TAG" else None

    def _entry(self, name: str, value) -> TagEntry:
        if name == "genre":
            fld = Field("value", FieldType.CHOICE, value, "Genre", GENRE_CHOICES)
        elif name == "track":
            fld = Field("value", FieldType.INT, value, "Track (0 = none)")
        else:
            size = dict(V1_LAYOUT)[name]
            fld = Field("value", FieldType.TEXT, value, f"Value (max {size} Latin-1 bytes)")
        return TagEntry(self.system, name, name.upper(), Kind.TEXT, [fld],
                        description=V1_DESCRIPTIONS[name])

    def read(self) -> list[TagEntry]:
        if not self.values:
            return []
        out = []
        for name in ("title", "artist", "album", "year", "comment", "track", "genre"):
            v = self.values.get(name)
            if name in ("track",) and not v:
                continue
            if name == "genre" and v == 255:
                continue
            if isinstance(v, str) and v == "":
                continue
            out.append(self._entry(name, v))
        return out

    def _blank(self) -> dict:
        return {"title": "", "artist": "", "album": "", "year": "", "comment": "",
                "track": 0, "genre": 255}

    def delete(self, key: str, missing_ok: bool = False) -> None:
        if key == "*":  # remove whole tag
            self.values = None
            return
        if not self.values:
            if missing_ok:
                return
            raise TagError("File has no ID3v1 tag")
        self.values[key] = self._blank()[key]

    def set(self, entry: TagEntry) -> None:
        if entry.key not in V1_DESCRIPTIONS:
            raise TagError(f"ID3v1 has no field {entry.key!r}")
        if self.values is None:
            self.values = self._blank()
        value = entry.get("value")
        if entry.key in ("track", "genre"):
            value = int(value)
        else:
            size = dict(V1_LAYOUT)[entry.key]
            if len(str(value).encode("latin-1", "replace")) > size:
                raise TagError(f"ID3v1 {entry.key} is limited to {size} bytes")
        self.values[entry.key] = value

    def save(self) -> None:
        """Rewrite the trailing 128 bytes. Must run after every other writer."""
        current = self._read_block()
        if self.values is None:
            if current is not None:
                with open(self.path, "r+b") as f:
                    f.seek(-128, os.SEEK_END)
                    f.truncate()
            return
        block = build_id3v1(self.values)
        with open(self.path, "r+b") as f:
            if current is not None:
                f.seek(-128, os.SEEK_END)
            else:
                f.seek(0, os.SEEK_END)
            f.write(block)

    def templates(self) -> list[TagEntry]:
        blank = self._blank()
        return [self._entry(n, blank[n]) for n in
                ("title", "artist", "album", "year", "comment", "track", "genre")]
