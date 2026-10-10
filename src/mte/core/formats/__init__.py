"""Tag system adapters."""

from __future__ import annotations

from ..model import TagEntry
from .apev2 import APEv2Adapter
from .asf import ASFAdapter
from .base import Adapter, TagError
from .id3 import ID3v1Adapter, ID3v2Adapter
from .mp4 import MP4Adapter
from .vorbis import FlacPictureAdapter, VorbisAdapter

ADAPTERS: dict[str, type[Adapter]] = {
    cls.system: cls for cls in (ID3v2Adapter, ID3v1Adapter, APEv2Adapter, MP4Adapter,
                                VorbisAdapter, FlacPictureAdapter, ASFAdapter)
}


def key_for(entry: TagEntry) -> str:
    """Native key an entry will be stored under once written."""
    return ADAPTERS[entry.system].key_of(entry)


def validate_entry(entry: TagEntry) -> str:
    """Raise TagError if ``entry`` can't be written; returns its key."""
    return ADAPTERS[entry.system].validate(entry)


__all__ = ["ADAPTERS", "Adapter", "TagError", "key_for", "validate_entry"]
