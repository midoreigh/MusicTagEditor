"""Format-independent tag model.

Every tag system (ID3v2, ID3v1, MP4, Vorbis comments, APEv2, ASF) is read into
a flat list of :class:`TagEntry` objects. Each entry carries the *native* key
exactly as the file stores it plus an ordered list of :class:`Field` values
that describe the frame/atom at full detail (encoding, language, description,
raw bytes, ...). The UI only ever works with these objects and the two edit
operations :class:`SetEntry` and :class:`DeleteEntry`; adapters translate them
back to mutagen objects.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FieldType(str, Enum):
    TEXT = "text"              # single-line str
    MULTILINE = "multiline"    # multi-line str (lyrics, long comments)
    TEXT_LIST = "text_list"    # list[str] (multi-value text)
    INT = "int"                # int
    INT_LIST = "int_list"      # list[int]
    PAIR_LIST = "pair_list"    # list[tuple[int, int]] (track 3/12)
    PEOPLE = "people"          # list[tuple[str, str]] (ID3 TIPL/TMCL)
    BOOL = "bool"              # bool
    BYTES = "bytes"            # raw binary payload
    CHOICE = "choice"          # one of Field.choices (value is the key)
    LANG = "lang"              # 3-letter ISO-639-2 language code
    PICTURES = "pictures"      # list[Picture] (MP4 covr)
    OPAQUE = "opaque"          # structured value we display but don't edit


@dataclass
class Picture:
    data: bytes
    mime: str = "image/jpeg"
    pic_type: int = 3
    desc: str = ""


@dataclass
class Field:
    name: str
    ftype: FieldType
    value: Any
    label: str = ""
    choices: list[tuple[Any, str]] | None = None  # (value, label)
    readonly: bool = False

    @property
    def title(self) -> str:
        return self.label or self.name


class Kind(str, Enum):
    TEXT = "text"
    URL = "url"
    COMMENT = "comment"
    PICTURE = "picture"
    BINARY = "binary"
    NUMBER = "number"
    OTHER = "other"


@dataclass
class TagEntry:
    system: str              # adapter system id, e.g. "ID3v2", "MP4"
    key: str                 # unique native key inside the file+system
    frame_id: str            # frame/atom/field name, e.g. "TXXX", "----", "TITLE"
    kind: Kind
    fields: list[Field]
    description: str = ""    # human readable name of the frame id
    readonly: bool = False   # e.g. unknown raw frames that can only be deleted
    editable_key: bool = False  # key itself is user-defined (TXXX desc, Vorbis key...)

    def get(self, name: str, default: Any = None) -> Any:
        for f in self.fields:
            if f.name == name:
                return f.value
        return default

    def set(self, name: str, value: Any) -> None:
        for f in self.fields:
            if f.name == name:
                f.value = value
                return
        raise KeyError(name)

    def field(self, name: str) -> Field | None:
        for f in self.fields:
            if f.name == name:
                return f
        return None

    def clone(self) -> "TagEntry":
        return copy.deepcopy(self)

    def summary(self) -> str:
        """One-line representation used in the tag table."""
        return summarize(self)

    @property
    def size(self) -> int:
        total = 0
        for f in self.fields:
            if f.ftype == FieldType.BYTES and isinstance(f.value, (bytes, bytearray)):
                total += len(f.value)
            elif f.ftype == FieldType.PICTURES:
                total += sum(len(p.data) for p in f.value)
        return total


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def format_value(f: Field) -> str:
    v = f.value
    t = f.ftype
    if v is None:
        return ""
    if t in (FieldType.TEXT, FieldType.MULTILINE, FieldType.LANG):
        return str(v).replace("\r\n", " ⏎ ").replace("\n", " ⏎ ")
    if t == FieldType.TEXT_LIST:
        return " ; ".join(str(x).replace("\n", " ⏎ ") for x in v)
    if t == FieldType.INT:
        return str(v)
    if t == FieldType.INT_LIST:
        return " ; ".join(str(x) for x in v)
    if t == FieldType.PAIR_LIST:
        return " ; ".join(f"{a}/{b}" if b else str(a) for a, b in v)
    if t == FieldType.PEOPLE:
        return " ; ".join(f"{a}: {b}" for a, b in v)
    if t == FieldType.BOOL:
        return "true" if v else "false"
    if t == FieldType.BYTES:
        return f"<binary {_human_size(len(v))}>"
    if t == FieldType.CHOICE:
        for cv, label in f.choices or []:
            if cv == v:
                return label
        return str(v)
    if t == FieldType.OPAQUE:
        return _opaque_text(v)
    if t == FieldType.PICTURES:
        return ", ".join(f"<{p.mime} {_human_size(len(p.data))}>" for p in v)
    return str(v)


def _opaque_text(v: Any) -> str:
    if isinstance(v, (bytes, bytearray)):
        return f"<binary {_human_size(len(v))}>"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_opaque_text(x) for x in v) + "]"
    if hasattr(v, "pprint"):
        try:
            return v.pprint().replace("\n", " ; ")
        except Exception:
            pass
    return str(v)


# Fields that are metadata about a frame rather than its content; they're shown
# in the detail column instead of the value column.
META_FIELDS = {"encoding", "lang", "desc", "owner", "mime", "type", "dataformat",
               "filename", "email", "name", "mean", "value_type"}


# Fields duplicated by the key column.
KEY_FIELDS = {"key"}


def summarize(entry: TagEntry) -> str:
    content = [f for f in entry.fields if f.name not in META_FIELDS | KEY_FIELDS]
    if not content:
        content = entry.fields
    return " | ".join(format_value(f) for f in content if format_value(f) != "")


def details(entry: TagEntry) -> str:
    parts = []
    for f in entry.fields:
        if f.name in META_FIELDS:
            val = format_value(f)
            if val != "":
                parts.append(f"{f.title}={val}")
    size = entry.size
    if size:
        parts.append(_human_size(size))
    return ", ".join(parts)


_EMPTY = {
    FieldType.TEXT: "", FieldType.MULTILINE: "", FieldType.TEXT_LIST: [], FieldType.INT: 0,
    FieldType.INT_LIST: [], FieldType.PAIR_LIST: [], FieldType.PEOPLE: [],
    FieldType.BOOL: False, FieldType.BYTES: b"", FieldType.PICTURES: [],
}


def blank_content(entry: TagEntry) -> TagEntry:
    """Copy of ``entry`` with its content emptied but its identity kept
    (key, encoding, language, description...). Used as the starting point
    when a file doesn't have a tag yet."""
    e = entry.clone()
    for f in e.fields:
        if f.name in META_FIELDS | KEY_FIELDS or f.readonly or f.ftype not in _EMPTY:
            continue
        f.value = copy.deepcopy(_EMPTY[f.ftype])
    return e


@dataclass
class SetEntry:
    """Replace the entry stored under ``old_key`` (if any) with ``entry``."""
    entry: TagEntry
    old_key: str | None = None

    @property
    def system(self) -> str:
        return self.entry.system


@dataclass
class DeleteEntry:
    system: str
    key: str


EditOp = SetEntry | DeleteEntry


@dataclass
class FileTags:
    path: str
    format_name: str                 # e.g. "MP3", "FLAC"
    systems: list[str]               # tag systems that can hold entries for this file
    entries: list[TagEntry] = field(default_factory=list)
    info: dict[str, Any] = field(default_factory=dict)  # duration, bitrate, id3 version ...
    error: str | None = None
