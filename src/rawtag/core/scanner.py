"""Find audio files below a folder (ported from clean_audio_tags.py)."""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator

DEFAULT_EXTENSIONS = {
    "mp3", "m4a", "m4b", "m4p", "m4r", "mp4", "aac", "flac", "ogg", "oga", "opus",
    "spx", "wav", "aif", "aiff", "aifc", "wma", "asf", "ape", "wv", "mpc", "ofr",
    "tak", "tta", "dsf",
}


def has_audio_ext(path: str, extensions: Iterable[str] = DEFAULT_EXTENSIONS) -> bool:
    name = os.path.basename(path)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return ext in set(extensions)


def find_audio_files(root: str, extensions: Iterable[str] = DEFAULT_EXTENSIONS) -> Iterator[str]:
    extensions = set(extensions)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            if not name.startswith("._") and has_audio_ext(name, extensions):
                yield os.path.join(dirpath, name)
