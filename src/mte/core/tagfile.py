"""Open an audio file with every tag system it can carry and route edits."""

from __future__ import annotations

import os

import mutagen
from mutagen.apev2 import APENoHeaderError, APEv2, APEv2File
from mutagen.asf import ASF
from mutagen.flac import FLAC
from mutagen.id3 import ID3FileType
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.ogg import OggFileType

from .formats.apev2 import APEv2Adapter
from .formats.asf import ASFAdapter
from .formats.base import Adapter, TagError
from .formats.id3 import ID3v1Adapter, ID3v2Adapter
from .formats.mp4 import MP4Adapter
from .formats.vorbis import FlacPictureAdapter, VorbisAdapter
from .model import EditOp, FileTags

try:  # optional formats, present in all modern mutagen versions
    from mutagen.aiff import AIFF
    from mutagen.wave import WAVE
    from mutagen.dsf import DSF
    _IFF_ID3 = (AIFF, WAVE, DSF)
except ImportError:  # pragma: no cover
    _IFF_ID3 = ()

try:
    from mutagen.trueaudio import TrueAudio
    _V1_CAPABLE = (MP3, TrueAudio)
except ImportError:  # pragma: no cover
    _V1_CAPABLE = (MP3,)


class UnsupportedFile(Exception):
    pass


def _open_raw_id3(cls, path):
    """Re-open an ID3-carrying file without translating frames to v2.4 and
    without merging ID3v1 into the v2 frames, so we see exactly what's stored."""
    try:
        return cls(path, translate=False, load_v1=False)
    except TypeError:
        return cls(path)


class TagFile:
    def __init__(self, path: str) -> None:
        self.path = os.fspath(path)
        audio = mutagen.File(self.path)
        if audio is None:
            raise UnsupportedFile("unsupported/unrecognized audio format")
        self.adapters: list[Adapter] = []
        self.format_name = type(audio).__name__

        if isinstance(audio, ID3FileType) or isinstance(audio, _IFF_ID3):
            audio = _open_raw_id3(type(audio), self.path)
            self.adapters.append(ID3v2Adapter(audio))
            if isinstance(audio, _V1_CAPABLE):
                try:
                    ape = APEv2(self.path)
                except APENoHeaderError:
                    ape = None
                self.adapters.append(APEv2Adapter(
                    ape, save_fn=lambda t: t.save(self.path), create_fn=APEv2))
                self.adapters.append(ID3v1Adapter(self.path))
        elif isinstance(audio, MP4):
            self.adapters.append(MP4Adapter(audio))
        elif isinstance(audio, FLAC):
            self.adapters.append(VorbisAdapter(audio))
            self.adapters.append(FlacPictureAdapter(audio))
        elif isinstance(audio, OggFileType):
            self.adapters.append(VorbisAdapter(audio))
        elif isinstance(audio, APEv2File):
            def _create(a=audio):
                a.add_tags()
                return a.tags
            self.adapters.append(APEv2Adapter(audio.tags, save_fn=lambda t, a=audio: a.save(),
                                              create_fn=_create))
        elif isinstance(audio, ASF):
            self.adapters.append(ASFAdapter(audio))
        else:
            raise UnsupportedFile(f"{self.format_name}: tag editing not supported")
        self.audio = audio

    # ------------------------------------------------------------------
    def adapter(self, system: str) -> Adapter:
        for a in self.adapters:
            if a.system == system:
                return a
        raise TagError(f"{os.path.basename(self.path)} ({self.format_name}) "
                       f"can't hold {system} tags")

    def has_system(self, system: str) -> bool:
        return any(a.system == system for a in self.adapters)

    def info(self) -> dict:
        info = {"format": self.format_name}
        ai = getattr(self.audio, "info", None)
        if ai is not None:
            for attr in ("length", "bitrate", "sample_rate", "channels", "bits_per_sample",
                         "codec_name", "codec_description"):
                v = getattr(ai, attr, None)
                if v not in (None, ""):
                    info[attr] = v
        for a in self.adapters:
            if isinstance(a, ID3v2Adapter):
                info["id3"] = a.note
        return info

    def read(self) -> FileTags:
        entries = []
        for a in self.adapters:
            entries.extend(a.read())
        return FileTags(
            path=self.path,
            format_name=self.format_name,
            systems=[a.system for a in self.adapters],
            entries=entries,
            info=self.info(),
        )

    def apply(self, ops: list[EditOp]) -> None:
        by_system: dict[str, list[EditOp]] = {}
        for op in ops:
            by_system.setdefault(op.system, []).append(op)
        for system, sys_ops in by_system.items():
            self.adapter(system).apply(sys_ops)

    def save(self) -> None:
        v1 = None
        wrote = False
        for a in self.adapters:
            if isinstance(a, ID3v1Adapter):
                v1 = a
                continue
            if a.dirty:
                a.save()
                a.dirty = False
                wrote = True
        # ID3v1 lives in the last 128 bytes; mutagen may have rewritten it
        # from the v2 frames, so always restore our (possibly edited) copy last.
        if v1 is not None and (v1.dirty or (wrote and v1.original is not None)):
            v1.save()
            v1.dirty = False


def load(path: str) -> FileTags:
    try:
        return TagFile(path).read()
    except Exception as e:  # report per-file problems instead of failing a whole folder
        return FileTags(path=os.fspath(path), format_name="?", systems=[], error=str(e))


def apply_and_save(path: str, ops: list[EditOp]) -> FileTags:
    tf = TagFile(path)
    tf.apply(ops)
    tf.save()
    return TagFile(path).read()
