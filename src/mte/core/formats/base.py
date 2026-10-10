"""Adapter interface shared by every tag system."""

from __future__ import annotations

from ..model import DeleteEntry, EditOp, Field, FieldType, Picture, SetEntry, TagEntry


class TagError(Exception):
    """A user-facing problem with an edit (bad value, unsupported op...)."""


class Adapter:
    """Reads/writes one tag system of one opened file.

    Adapters are bound to an already opened file (see :mod:`mte.core.tagfile`).
    ``apply`` mutates the in-memory tags only; ``save`` writes them to disk.
    """

    system: str = ""
    #: label shown in the UI (e.g. "ID3v2.3")
    label: str = ""

    def __init__(self) -> None:
        self.dirty = False

    def read(self) -> list[TagEntry]:
        raise NotImplementedError

    def apply(self, ops: list[EditOp]) -> None:
        for op in ops:
            if isinstance(op, DeleteEntry):
                self.delete(op.key)
            elif isinstance(op, SetEntry):
                if op.entry.readonly:
                    raise TagError(f"{op.entry.key} is read-only")
                if op.old_key is not None:
                    self.delete(op.old_key, missing_ok=True)
                self.set(op.entry)
            self.dirty = True

    def delete(self, key: str, missing_ok: bool = False) -> None:
        raise NotImplementedError

    def set(self, entry: TagEntry) -> None:
        raise NotImplementedError

    def save(self) -> None:
        raise NotImplementedError

    @staticmethod
    def key_of(entry: TagEntry) -> str:
        """Native key an entry will be stored under (may depend on its fields)."""
        return entry.key

    def templates(self) -> list[TagEntry]:
        """Blank entries offered by the "Add tag" dialog."""
        return []


# ---------------------------------------------------------------------------
# Helpers shared by several adapters

PICTURE_TYPES = [
    "Other", "File icon (32x32 PNG)", "Other file icon", "Cover (front)",
    "Cover (back)", "Leaflet page", "Media", "Lead artist", "Artist",
    "Conductor", "Band", "Composer", "Lyricist", "Recording location",
    "During recording", "During performance", "Screen capture",
    "Bright coloured fish", "Illustration", "Band logotype", "Publisher logotype",
]
PICTURE_TYPE_CHOICES = [(i, f"{i}: {name}") for i, name in enumerate(PICTURE_TYPES)]


def sniff_mime(data: bytes, fallback: str = "application/octet-stream") -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:2] == b"BM":
        return "image/bmp"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return fallback


def text_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]


__all__ = [
    "Adapter", "TagError", "PICTURE_TYPES", "PICTURE_TYPE_CHOICES", "sniff_mime",
    "text_list", "Field", "FieldType", "Picture", "TagEntry",
]
