"""Manual folder renaming."""

from __future__ import annotations

import os
import re

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def validate_folder_name(name: str) -> str | None:
    """Error message, or None if ``name`` is usable on every OS."""
    if not name.strip():
        return "The name can't be empty."
    if name in (".", ".."):
        return "That name isn't allowed."
    bad = sorted(set(_INVALID.findall(name)))
    if bad:
        shown = " ".join("/" if c == "/" else repr(c)[1:-1] for c in bad)
        return f"Folder names can't contain: {shown}"
    if name != name.rstrip(" ."):
        return "Folder names can't end with a space or a dot (not allowed on Windows)."
    return None


def rename_folder(old_dir: str, new_name: str) -> str:
    """Rename ``old_dir`` to ``new_name`` in the same parent; returns the new path."""
    old_dir = os.path.abspath(old_dir)
    err = validate_folder_name(new_name)
    if err:
        raise ValueError(err)
    if not os.path.isdir(old_dir):
        raise FileNotFoundError(f"Folder not found: {old_dir}")
    new_dir = os.path.join(os.path.dirname(old_dir), new_name)
    if new_dir == old_dir:
        return old_dir
    if os.path.exists(new_dir):
        same = False
        try:
            same = os.path.samefile(old_dir, new_dir)  # case-only change on macOS/Windows
        except OSError:
            pass
        if not same:
            raise FileExistsError(f"A folder named {new_name!r} already exists there.")
    os.rename(old_dir, new_dir)
    return new_dir


def remap_path(path: str, old_dir: str, new_dir: str) -> str:
    """``path`` moved along with a renamed ancestor folder (unchanged otherwise)."""
    old_dir = os.path.abspath(old_dir)
    p = os.path.abspath(path)
    if p == old_dir or p.startswith(old_dir + os.sep):
        return new_dir + p[len(old_dir):]
    return path


def ancestor_choices(path: str, all_paths: list[str]) -> list[str]:
    """Folders that can be renamed for ``path``: its folder and parents, up to
    the deepest folder containing every loaded file."""
    folder = os.path.dirname(os.path.abspath(path))
    try:
        top = os.path.commonpath([os.path.dirname(os.path.abspath(p)) for p in all_paths])
    except ValueError:  # different drives on Windows
        top = folder
    out = [folder]
    while folder != top and os.path.dirname(folder) != folder:
        folder = os.path.dirname(folder)
        if not folder.startswith(top) or os.path.dirname(folder) == folder:
            break
        out.append(folder)
    return out
