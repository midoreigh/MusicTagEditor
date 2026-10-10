"""Compute and perform script-based renames (Picard's "Rename files when saving")."""

from __future__ import annotations

import os
import re
import shutil
import unicodedata
from dataclasses import dataclass

from ..model import FileTags, TagEntry
from .script import ScriptError, evaluate
from .variables import build_variables

PICARD_DEFAULT = (
    "$if2(%albumartist%,%artist%)/\n"
    "$if(%albumartist%,%album%/,)\n"
    "$if($gt(%totaldiscs%,1),$if($gt(%totaldiscs%,9),$num(%discnumber%,2),%discnumber%)-,)"
    "$if($and(%albumartist%,%tracknumber%),$num(%tracknumber%,2) ,)"
    "$if(%_multiartist%,%artist% - ,)%title%"
)

PRESETS = {
    "Picard default (Artist/Album/NN Title)": PICARD_DEFAULT,
    "NN - Title (same folder)": "$if(%tracknumber%,$num(%tracknumber%,2) - ,)%title%",
    "Artist - Title (same folder)": "$if2(%artist%,Unknown Artist) - %title%",
    "Album/NN - Artist - Title": (
        "$if2(%album%,Unknown Album)/\n"
        "$if(%tracknumber%,$num(%tracknumber%,2) - ,)%artist% - %title%"
    ),
}

# Characters invalid in a path component on at least one OS (we always build
# names valid on Windows so a library can move between machines).
_ILLEGAL = re.compile(r'[<>:"|?*\\\x00-\x1f]')
_WIN_RESERVED = re.compile(r"^(con|prn|aux|nul|com\d|lpt\d)(\..*)?$", re.IGNORECASE)
MAX_COMPONENT_BYTES = 240  # leave room for the extension and " (n)" suffix


@dataclass
class NamingOptions:
    rename: bool = False
    script: str = PICARD_DEFAULT
    move: bool = False             # put files under dest_dir instead of their folder
    dest_dir: str = ""
    delete_empty_dirs: bool = True

    @property
    def active(self) -> bool:
        return self.rename or self.move


def sanitize_component(name: str, replacement: str = "_") -> str:
    name = unicodedata.normalize("NFC", name)
    name = _ILLEGAL.sub(replacement, name)
    name = name.strip().rstrip(". ")  # Windows drops trailing dots/spaces
    if _WIN_RESERVED.match(name):
        name = "_" + name
    raw = name.encode("utf-8")
    if len(raw) > MAX_COMPONENT_BYTES:
        name = raw[:MAX_COMPONENT_BYTES].decode("utf-8", "ignore").rstrip(". ")
    return name


def script_to_relpath(script: str, variables: dict[str, str]) -> str:
    """Evaluate a naming script to a relative path *without* extension.

    Like Picard, newlines and tabs in the script are ignored (so scripts can
    be written over several lines) and '/' separates folders.
    """
    text = evaluate(script.replace("\r", "").replace("\n", "").replace("\t", ""), variables)
    parts = [sanitize_component(p) for p in text.replace("\\", "/").split("/")]
    parts = [p for p in parts if p not in ("", ".", "..")]
    return "/".join(parts)


def target_path(ft: FileTags, opts: NamingOptions,
                entries: list[TagEntry] | None = None) -> str:
    """Absolute path the file would get. Raises ScriptError/ValueError."""
    src = os.path.abspath(ft.path)
    base_dir = os.path.abspath(os.path.expanduser(opts.dest_dir)) if opts.move and opts.dest_dir \
        else os.path.dirname(src)
    ext = os.path.splitext(src)[1].lower()
    if opts.rename:
        rel = script_to_relpath(opts.script, build_variables(ft, entries))
        if not rel:
            raise ValueError("naming script produced an empty file name")
    else:
        rel = os.path.splitext(os.path.basename(src))[0]
    return os.path.normpath(os.path.join(base_dir, *rel.split("/"))) + ext


def _same_file(a: str, b: str) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def unique_path(path: str, src: str) -> str:
    """``path`` or ``path (n)`` so we never overwrite another file."""
    if not os.path.exists(path) or _same_file(path, src):
        return path
    stem, ext = os.path.splitext(path)
    n = 1
    while True:
        candidate = f"{stem} ({n}){ext}"
        if not os.path.exists(candidate) or _same_file(candidate, src):
            return candidate
        n += 1


def _remove_empty_dirs(start: str, stop_at: str | None) -> None:
    d = start
    while d and os.path.isdir(d) and d != stop_at and d != os.path.dirname(d):
        try:
            if os.listdir(d):
                return
            os.rmdir(d)
        except OSError:
            return
        d = os.path.dirname(d)


def rename_file(ft: FileTags, opts: NamingOptions) -> str:
    """Move/rename one (already saved) file; returns its new path."""
    src = os.path.abspath(ft.path)
    dst = target_path(ft, opts)
    if dst == src:
        return src
    dst = unique_path(dst, src)
    if dst == src:
        return src
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if _same_file(src, dst):  # case-only change on a case-insensitive FS
        os.rename(src, dst)
    else:
        shutil.move(src, dst)
    if opts.delete_empty_dirs and os.path.dirname(src) != os.path.dirname(dst):
        stop = os.path.abspath(os.path.expanduser(opts.dest_dir)) if opts.move and opts.dest_dir \
            else None
        _remove_empty_dirs(os.path.dirname(src), stop)
    return dst


def preview(ft: FileTags, opts: NamingOptions, entries: list[TagEntry] | None = None) -> str:
    """Target path or an error message (for the UI)."""
    try:
        return target_path(ft, opts, entries)
    except (ScriptError, ValueError) as e:
        return f"⚠ {e}"


__all__ = ["NamingOptions", "PICARD_DEFAULT", "PRESETS", "preview", "rename_file",
           "script_to_relpath", "target_path", "ScriptError"]
