"""Builds tiny but valid audio files for every supported container.

Only the M4A fixture is a committed binary (made with macOS afconvert); the
rest are synthesised here so the tests run anywhere without ffmpeg.
"""

from __future__ import annotations

import shutil
import struct
import wave
from pathlib import Path

import pytest
from mutagen.ogg import OggPage

FIXTURES = Path(__file__).parent / "fixtures"


def make_mp3(path: Path, frames: int = 20) -> Path:
    # MPEG-1 Layer III, 128 kbps, 44.1 kHz, no padding -> 417-byte frames
    header = b"\xff\xfb\x90\x00"
    path.write_bytes((header + b"\x00" * 413) * frames)
    return path


def make_wav(path: Path) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 800)
    return path


def make_flac(path: Path) -> Path:
    # STREAMINFO only (last-metadata-block flag set); no audio frames needed
    sample_rate, channels, bps, total = 44100, 2, 16, 44100
    packed = (sample_rate << 44) | ((channels - 1) << 41) | ((bps - 1) << 36) | total
    streaminfo = struct.pack(">HH", 4096, 4096) + b"\x00\x00\x00" * 2 \
        + packed.to_bytes(8, "big") + b"\x00" * 16
    block = bytes([0x80]) + len(streaminfo).to_bytes(3, "big") + streaminfo
    path.write_bytes(b"fLaC" + block)
    return path


def make_opus(path: Path) -> Path:
    head = b"OpusHead" + struct.pack("<BBHIhB", 1, 2, 312, 48000, 0, 0)
    tags_pkt = b"OpusTags" + struct.pack("<I", 6) + b"rawtag" + struct.pack("<I", 0)
    pages = []
    for seq, (pkt, pos, flags) in enumerate([(head, 0, 0x02), (tags_pkt, 0, 0),
                                             (b"\xf8\xff\xfe", 960, 0x04)]):
        page = OggPage()
        page.serial = 1234
        page.sequence = seq
        page.position = pos
        page.first = bool(flags & 0x02)
        page.last = bool(flags & 0x04)
        page.packets = [pkt]
        pages.append(page.write())
    path.write_bytes(b"".join(pages))
    return path


@pytest.fixture
def mp3(tmp_path):
    return make_mp3(tmp_path / "a.mp3")


@pytest.fixture
def wav(tmp_path):
    return make_wav(tmp_path / "a.wav")


@pytest.fixture
def flac(tmp_path):
    return make_flac(tmp_path / "a.flac")


@pytest.fixture
def opus(tmp_path):
    return make_opus(tmp_path / "a.opus")


@pytest.fixture
def m4a(tmp_path):
    dst = tmp_path / "a.m4a"
    shutil.copy(FIXTURES / "silence.m4a", dst)
    return dst
