"""Apply edit operations to many files, collecting per-file errors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .model import EditOp, FileTags
from .naming import NamingOptions, rename_file
from .tagfile import apply_and_save, load


@dataclass
class BatchResult:
    # original path -> reloaded tags (FileTags.path is the new path if renamed)
    saved: dict[str, FileTags] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)          # tags not saved
    rename_errors: dict[str, str] = field(default_factory=dict)   # tags saved, rename failed

    @property
    def renamed(self) -> dict[str, str]:
        return {old: ft.path for old, ft in self.saved.items() if ft.path != old}


def save_all(plan: dict[str, list[EditOp]],
             progress: Callable[[int, int, str], None] | None = None,
             naming: NamingOptions | None = None) -> BatchResult:
    result = BatchResult()
    total = len(plan)
    for i, (path, ops) in enumerate(plan.items()):
        if progress:
            progress(i, total, path)
        try:
            ft = apply_and_save(path, ops) if ops else load(path)
        except Exception as e:  # keep going, report at the end
            result.errors[path] = f"{type(e).__name__}: {e}"
            continue
        if naming is not None and naming.active:
            try:
                new_path = rename_file(ft, naming)
                if new_path != ft.path:
                    ft = load(new_path)
            except Exception as e:
                result.rename_errors[path] = f"{type(e).__name__}: {e}"
        result.saved[path] = ft
    if progress:
        progress(total, total, "")
    return result
