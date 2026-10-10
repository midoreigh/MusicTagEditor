"""In-memory editing session: loaded files, pending edits, merged views.

Nothing touches disk until :func:`Session.save_plan` is executed through
:func:`mte.core.batch.save_all`. Each file keeps its original tags and a
working copy reflecting pending edits. What gets saved is the *difference*
between the two, not the history of edits: an edit that was later deleted,
overwritten or reverted leaves nothing behind. Every edit is validated when
it's made, so a value that can't be written is rejected immediately instead
of failing at save time.
"""

from __future__ import annotations

import os
from collections import OrderedDict
from dataclasses import dataclass, field

from .formats import validate_entry
from .formats.base import TagError
from .model import DeleteEntry, EditOp, FileTags, SetEntry, TagEntry

GroupKey = tuple[str, str]  # (system, key)


@dataclass
class FileState:
    original: FileTags
    working: list[TagEntry]
    _ops: list[EditOp] | None = field(default=None, repr=False)  # cached diff

    @property
    def path(self) -> str:
        return self.original.path

    @property
    def ops(self) -> list[EditOp]:
        """Edits that turn the original tags into the working ones."""
        if self._ops is None:
            self._ops = diff_ops(self.original.entries, self.working)
        return self._ops

    @property
    def dirty(self) -> bool:
        return bool(self.ops)

    def find(self, system: str, key: str) -> TagEntry | None:
        for e in self.working:
            if e.system == system and e.key == key:
                return e
        return None

    def original_entry(self, system: str, key: str) -> TagEntry | None:
        for e in self.original.entries:
            if e.system == system and e.key == key:
                return e
        return None

    def apply(self, op: EditOp) -> None:
        """Apply an edit to the working copy. Raises TagError (leaving the
        working copy untouched) if the result couldn't be written."""
        if isinstance(op, DeleteEntry):
            self.working = [e for e in self.working
                            if not (e.system == op.system and e.key == op.key)]
        else:
            if op.system not in self.original.systems:
                raise TagError(f"{os.path.basename(self.path)} can't hold {op.system} tags")
            new = op.entry.clone()
            new.key = validate_entry(new)
            if new.key.endswith("#new"):  # each added picture block needs its own key
                n = 1
                while self.find(new.system, f"{new.key}{n}") is not None:
                    n += 1
                new.key = f"{new.key}{n}"
            pos = None
            for i, e in enumerate(self.working):
                if e.system == new.system and e.key in (op.old_key, new.key):
                    pos = i if pos is None else pos
            self.working = [e for e in self.working
                            if not (e.system == new.system and e.key in (op.old_key, new.key))]
            if pos is None:
                self.working.append(new)
            else:
                self.working.insert(min(pos, len(self.working)), new)
        self._ops = None

    def revert(self) -> None:
        self.working = [e.clone() for e in self.original.entries]
        self._ops = None

    def entry_state(self, entry: TagEntry) -> str:
        """'' (unchanged), 'new' or 'modified'."""
        orig = self.original_entry(entry.system, entry.key)
        if orig is None:
            return "new"
        if orig.fields != entry.fields:
            return "modified"
        return ""


def diff_ops(original: list[TagEntry], working: list[TagEntry]) -> list[EditOp]:
    """Deletions for entries that are gone, then a set for every entry that is
    new or changed. Keys are compared per tag system."""
    orig = {(e.system, e.key): e for e in original}
    work = {(e.system, e.key): e for e in working}
    ops: list[EditOp] = [DeleteEntry(s, k) for (s, k) in orig if (s, k) not in work]
    for (s, k), e in work.items():
        before = orig.get((s, k))
        if before is None:
            ops.append(SetEntry(e.clone(), None))
        elif before.fields != e.fields:
            ops.append(SetEntry(e.clone(), k))
    return ops


@dataclass
class MergedRow:
    system: str
    key: str
    entries: dict[str, TagEntry]   # path -> entry (only files that have it)
    total: int                     # number of files in the view

    @property
    def first(self) -> TagEntry:
        return next(iter(self.entries.values()))

    @property
    def uniform(self) -> bool:
        vals = [e.fields for e in self.entries.values()]
        return all(v == vals[0] for v in vals[1:])

    @property
    def partial(self) -> bool:
        return len(self.entries) < self.total


class Session:
    def __init__(self) -> None:
        self.files: "OrderedDict[str, FileState]" = OrderedDict()

    # -- loading -------------------------------------------------------------
    def add(self, ft: FileTags) -> FileState:
        state = FileState(ft, [e.clone() for e in ft.entries])
        self.files[ft.path] = state
        return state

    def replace_original(self, ft: FileTags) -> None:
        """After a successful save: reloaded tags become the new baseline."""
        self.add(ft)

    def rename_path(self, old: str, ft: FileTags) -> None:
        """A file was saved and moved: re-key it in place with its new tags."""
        items = [(ft.path, FileState(ft, [e.clone() for e in ft.entries])) if p == old
                 else (p, st) for p, st in self.files.items()]
        self.files = OrderedDict(items)

    def remap_folder(self, old_dir: str, new_dir: str) -> dict[str, str]:
        """A folder was renamed on disk: move every file under it to its new
        path, keeping pending edits. Returns {old path: new path}."""
        from .folders import remap_path
        moved: dict[str, str] = {}
        items = []
        for p, st in self.files.items():
            new = remap_path(p, old_dir, new_dir)
            if new != p:
                st.original.path = new
                moved[p] = new
            items.append((new, st))
        self.files = OrderedDict(items)
        return moved

    def remove(self, paths) -> None:
        for p in paths:
            self.files.pop(p, None)

    def clear(self) -> None:
        self.files.clear()

    def __contains__(self, path: str) -> bool:
        return path in self.files

    # -- views ---------------------------------------------------------------
    def merged(self, paths: list[str]) -> list[MergedRow]:
        rows: "OrderedDict[GroupKey, MergedRow]" = OrderedDict()
        states = [self.files[p] for p in paths if p in self.files]
        for st in states:
            for e in st.working:
                gk = (e.system, e.key)
                row = rows.get(gk)
                if row is None:
                    row = rows[gk] = MergedRow(e.system, e.key, {}, len(states))
                row.entries[st.path] = e
        return list(rows.values())

    def dirty_files(self) -> list[FileState]:
        return [s for s in self.files.values() if s.dirty]

    # -- edits ---------------------------------------------------------------
    def set_entry(self, paths: list[str], entry: TagEntry, old_key: str | None,
                  only_existing: bool = True) -> dict[str, str]:
        """Set ``entry`` on every file; returns {path: error} for files skipped."""
        errors = {}
        for p in paths:
            st = self.files[p]
            if only_existing and old_key is not None and st.find(entry.system, old_key) is None:
                continue
            try:
                st.apply(SetEntry(entry.clone(), old_key))
            except TagError as e:
                errors[p] = str(e)
        return errors

    def delete(self, paths: list[str], system: str, key: str) -> None:
        for p in paths:
            st = self.files[p]
            if st.find(system, key) is not None:
                st.apply(DeleteEntry(system, key))

    def revert(self, paths: list[str]) -> None:
        for p in paths:
            self.files[p].revert()

    def save_plan(self, paths: list[str] | None = None) -> dict[str, list[EditOp]]:
        states = self.dirty_files() if paths is None else \
            [self.files[p] for p in paths if self.files[p].dirty]
        return {s.path: list(s.ops) for s in states}
