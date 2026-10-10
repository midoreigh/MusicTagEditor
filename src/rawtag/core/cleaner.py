"""Remove every tag whose key or value contains a search term.

Same matching rule as the original clean_audio_tags.py (case-insensitive
substring on the key or the textual value), working on TagEntry objects so it
covers every tag system and the GUI can preview matches before deleting.
"""

from __future__ import annotations

from .model import DeleteEntry, FileTags, TagEntry
from .textutil import entry_search_text


def matching_entries(ft: FileTags, term: str, keys_only: bool = False) -> list[TagEntry]:
    term = term.lower()
    if not term:
        return []
    out = []
    for e in ft.entries:
        hay = e.key if keys_only else entry_search_text(e)
        if term in hay.lower():
            out.append(e)
    return out


def removal_ops(ft: FileTags, term: str, keys_only: bool = False) -> list[DeleteEntry]:
    return [DeleteEntry(e.system, e.key) for e in matching_entries(ft, term, keys_only)]
