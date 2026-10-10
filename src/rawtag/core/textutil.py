"""Text helpers ported from the original clean_audio_tags.py script."""

from __future__ import annotations

from .model import FieldType, TagEntry


def tag_value_to_text(value) -> str:
    """Best-effort conversion of a mutagen tag value to a searchable string.

    Mutagen frame/value objects already implement __str__ correctly for every
    shape they come in (plain string .text like USLT lyrics, list .text like
    TXXX/COMM, raw bytes for freeform MP4 atoms, etc.), so we lean on that
    instead of guessing the internal structure ourselves.
    """
    try:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="ignore")
        if isinstance(value, (list, tuple)):
            parts = []
            for v in value:
                if isinstance(v, bytes):
                    parts.append(v.decode("utf-8", errors="ignore"))
                else:
                    parts.append(str(v))
            return " ".join(parts)
        return str(value)
    except Exception:
        return str(value)


def entry_search_text(entry: TagEntry) -> str:
    """All textual content of an entry (key + every field), for searching."""
    parts = [entry.key]
    for f in entry.fields:
        if f.ftype == FieldType.PICTURES:
            continue
        if f.ftype == FieldType.BYTES and len(f.value or b"") > 4096:
            continue  # don't scan image payloads
        parts.append(tag_value_to_text(f.value))
    return " ".join(parts)
