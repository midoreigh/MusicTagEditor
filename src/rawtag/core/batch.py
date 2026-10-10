"""Apply edit operations to many files, collecting per-file errors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .model import EditOp, FileTags
from .tagfile import apply_and_save


@dataclass
class BatchResult:
    saved: dict[str, FileTags] = field(default_factory=dict)   # path -> reloaded tags
    errors: dict[str, str] = field(default_factory=dict)        # path -> message


def save_all(plan: dict[str, list[EditOp]],
             progress: Callable[[int, int, str], None] | None = None) -> BatchResult:
    result = BatchResult()
    total = len(plan)
    for i, (path, ops) in enumerate(plan.items()):
        if progress:
            progress(i, total, path)
        try:
            result.saved[path] = apply_and_save(path, ops)
        except Exception as e:  # keep going, report at the end
            result.errors[path] = f"{type(e).__name__}: {e}"
    if progress:
        progress(total, total, "")
    return result
