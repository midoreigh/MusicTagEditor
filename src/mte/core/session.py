"""In-memory editing session: loaded files, pending edits, merged views.

Nothing touches disk until :func:`Session.save_plan` is executed through
:func:`mte.core.batch.save_all`. Each file keeps its original tags, a working
copy that reflects pending edits, and the op log that will be replayed on a
freshly opened file at save time.
"""

from __future__ import annotations

import os
from collections import OrderedDict
from dataclasses import dataclass, field

from .formats import key_for
from .formats.base import TagError
from .model import DeleteEntry, EditOp, FileTags, SetEntry, TagEntry

GroupKey = tuple[str, str]  # (system, key)


@dataclass
class FileState:
    original: FileTags
    working: list[TagEntry]
    ops: list[EditOp] = field(default_factory=list)

    @property
    def path(self) -> str:
        return self.original.path

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
        if isinstance(op, DeleteEntry):
            idx = [i for i, e in enumerate(self.working)
                   if e.system == op.system and e.key == op.key]
            if not idx:
                return
            for i in reversed(idx):
                del self.working[i]
        else:
            if op.system not in self.original.systems:
                raise TagError(f"{os.path.basename(self.path)} can't hold {op.system} tags")
            new = op.entry.clone()
            new.key = key_for(new)
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
            op = SetEntry(new, op.old_key)
        self.ops.append(op)

    def revert(self) -> None:
        self.working = [e.clone() for e in self.original.entries]
        self.ops.clear()

    def entry_state(self, entry: TagEntry) -> str:
        """'' (unchanged), 'new' or 'modified'."""
        orig = self.original_entry(entry.system, entry.key)
        if orig is None:
            return "new"
        if orig.fields != entry.fields:
            return "modified"
        return ""


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
