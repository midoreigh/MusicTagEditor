"""Folder tree of loaded files (left pane).

Each folder you open becomes a root; files appear under their folders.
Selecting a folder selects every file below it.
"""

from __future__ import annotations

import os

from PySide6.QtCore import (QAbstractItemModel, QItemSelection, QItemSelectionModel,
                            QModelIndex, QSortFilterProxyModel, Qt, Signal)
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import QAbstractItemView, QApplication, QHeaderView, QStyle, QTreeView

from ..core.session import Session

COLUMNS = ["Name", "Format", "Tags"]
COL_NAME, COL_FORMAT, COL_TAGS = range(3)
IS_DIR_ROLE = Qt.ItemDataRole.UserRole + 1


def _home_short(path: str) -> str:
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if path == home or path.startswith(home + os.sep) else path


def _is_under(path: str, folder: str) -> bool:
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


class Node:
    __slots__ = ("name", "path", "is_dir", "parent", "children", "by_name", "row", "file_count")

    def __init__(self, name: str, path: str, is_dir: bool, parent: "Node | None") -> None:
        self.name = name
        self.path = path
        self.is_dir = is_dir
        self.parent = parent
        self.children: list[Node] = []
        self.by_name: dict[str, Node] = {}
        self.row = 0
        self.file_count = 0


class FileTreeModel(QAbstractItemModel):
    folders_added = Signal(list)   # folder paths created by an insertion (to auto-expand)

    def __init__(self, session: Session, parent=None) -> None:
        super().__init__(parent)
        self.session = session
        self.paths: list[str] = []          # every loaded file, in load order
        self.roots: list[str] = []          # folders shown at top level
        self._root = Node("", "", True, None)
        self._files: dict[str, Node] = {}
        self._dirty_dirs: set[str] = set()
        self.last_remap: dict[str, str] = {}  # old -> new paths of the last structural change
        style = QApplication.style()
        self._dir_icon = style.standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        self._file_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)

    # ------------------------------------------------------------ structure
    def _root_for(self, path: str) -> str:
        best = ""
        for r in self.roots:
            if _is_under(path, r) and len(r) > len(best):
                best = r
        return best or os.path.dirname(path)

    def add_root(self, folder: str) -> None:
        """Register a folder the user opened (so it shows as a top-level node)."""
        folder = os.path.abspath(folder)
        if any(_is_under(folder, r) for r in self.roots):
            return  # already inside a root
        swallowed = [r for r in self.roots if _is_under(r, folder)]
        self.roots = [r for r in self.roots if r not in swallowed] + [folder]
        if swallowed:  # a new root above existing ones: restructure
            self._rebuild({})

    def _new_child(self, parent: Node, name: str, path: str, is_dir: bool,
                   insert: bool, created: list[str]) -> Node:
        node = Node(name, path, is_dir, parent)
        row = len(parent.children)
        if insert:
            self.beginInsertRows(self._index_of(parent), row, row)
        node.row = row
        parent.children.append(node)
        parent.by_name[name] = node
        if insert:
            self.endInsertRows()
        if is_dir:
            created.append(path)
        return node

    def _place(self, path: str, insert: bool, created: list[str]) -> None:
        root_path = self._root_for(path)
        if root_path not in self.roots:
            self.roots.append(root_path)
        node = self._root.by_name.get(root_path)
        if node is None:
            node = self._new_child(self._root, root_path, root_path, True, insert, created)
        rel = os.path.relpath(os.path.dirname(path), root_path)
        if rel != ".":
            for part in rel.split(os.sep):
                child = node.by_name.get(part)
                if child is None:
                    child = self._new_child(node, part, os.path.join(node.path, part), True,
                                            insert, created)
                node = child
        leaf = self._new_child(node, os.path.basename(path), path, False, insert, created)
        self._files[path] = leaf
        n = node
        while n is not None:
            n.file_count += 1
            n = n.parent

    def _rebuild(self, remap: dict[str, str]) -> None:
        self.last_remap = remap
        self.beginResetModel()
        self._root = Node("", "", True, None)
        self._files = {}
        for p in self.paths:
            self._place(p, insert=False, created=[])
        self._update_dirty()
        self.endResetModel()
        self.last_remap = {}

    # ------------------------------------------------- public (list-like) API
    def add_paths(self, paths: list[str]) -> None:
        created: list[str] = []
        for p in paths:
            if p in self._files:
                continue
            self.paths.append(p)
            self._place(p, insert=True, created=created)
        self._update_dirty()
        if created:
            self.folders_added.emit(created)

    def remove_paths(self, paths) -> None:
        gone = set(paths)
        self.paths = [p for p in self.paths if p not in gone]
        self.roots = [r for r in self.roots if any(_is_under(p, r) for p in self.paths)]
        self._rebuild({})

    def clear(self) -> None:
        self.paths = []
        self.roots = []
        self._rebuild({})

    def remap(self, moved: dict[str, str], old_dir: str | None = None,
              new_dir: str | None = None) -> None:
        """Files moved (renamed on save, folder renamed). Rebuilds the tree."""
        if not moved and old_dir is None:
            return
        self.paths = [moved.get(p, p) for p in self.paths]
        if old_dir is not None and new_dir is not None:
            from ..core.folders import remap_path
            self.roots = [remap_path(r, old_dir, new_dir) for r in self.roots]
            moved = dict(moved)
            moved[old_dir] = new_dir  # lets the view keep that folder expanded/selected
        self._rebuild(moved)

    def replace_path(self, old: str, new: str) -> None:
        self.remap({old: new})

    def refresh(self, paths=None) -> None:
        """Repaint after edits (dirty markers, tag counts)."""
        self._update_dirty()
        if not self._root.children:
            return
        # simplest correct thing: everything may have changed state
        self._emit_changed(self._root)

    def _emit_changed(self, node: Node) -> None:
        if node.children:
            parent = self._index_of(node)
            self.dataChanged.emit(self.index(0, 0, parent),
                                  self.index(len(node.children) - 1, len(COLUMNS) - 1, parent))
            for c in node.children:
                if c.is_dir:
                    self._emit_changed(c)

    def _update_dirty(self) -> None:
        dirs: set[str] = set()
        for st in self.session.dirty_files():
            node = self._files.get(st.path)
            n = node.parent if node else None
            while n is not None and n.path:
                dirs.add(n.path)
                n = n.parent
        self._dirty_dirs = dirs

    # ---------------------------------------------------------- indexes
    def _index_of(self, node: Node, column: int = 0) -> QModelIndex:
        if node is self._root or node is None:
            return QModelIndex()
        return self.createIndex(node.row, column, node)

    def node(self, index: QModelIndex) -> Node:
        return index.internalPointer() if index.isValid() else self._root

    def index_for_path(self, path: str) -> QModelIndex:
        node = self._files.get(path)
        if node is None:
            node = self._find_dir(path)
        return self._index_of(node) if node else QModelIndex()

    def _find_dir(self, path: str) -> Node | None:
        stack = list(self._root.children)
        while stack:
            n = stack.pop()
            if n.is_dir:
                if n.path == path:
                    return n
                if _is_under(path, n.path):
                    stack.extend(n.children)
        return None

    def index(self, row, column, parent=QModelIndex()):
        node = self.node(parent)
        if 0 <= row < len(node.children) and 0 <= column < len(COLUMNS):
            return self.createIndex(row, column, node.children[row])
        return QModelIndex()

    def parent(self, index=QModelIndex()):
        if not index.isValid():
            return QModelIndex()
        node: Node = index.internalPointer()
        return self._index_of(node.parent)

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid() and parent.column() != 0:
            return 0
        return len(self.node(parent).children)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def hasChildren(self, parent=QModelIndex()):
        return bool(self.node(parent).children)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        n: Node = index.internalPointer()
        col = index.column()
        if role == Qt.ItemDataRole.UserRole:
            return n.path
        if role == IS_DIR_ROLE:
            return n.is_dir
        if n.is_dir:
            return self._dir_data(n, col, role)
        st = self.session.files.get(n.path)
        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_NAME:
                return ("● " if st and st.dirty else "") + n.name
            if col == COL_FORMAT:
                return st.original.format_name if st else ""
            if col == COL_TAGS:
                if st and st.original.error:
                    return "error"
                return len(st.working) if st else ""
        if role == Qt.ItemDataRole.DecorationRole and col == COL_NAME:
            return self._file_icon
        if role == Qt.ItemDataRole.ToolTipRole:
            if st and st.original.error:
                return f"{n.path}\n\n{st.original.error}"
            if st:
                return n.path + "\n" + ", ".join(f"{k}: {v}" for k, v in st.original.info.items())
            return n.path
        if role == Qt.ItemDataRole.ForegroundRole:
            if st and st.original.error:
                return QBrush(QColor("#c0392b"))
            if st and st.dirty and col == COL_NAME:
                return QBrush(QColor("#e67e22"))
        if role == Qt.ItemDataRole.FontRole and st and st.dirty and col == COL_NAME:
            f = QFont()
            f.setBold(True)
            return f
        if role == Qt.ItemDataRole.TextAlignmentRole and col == COL_TAGS:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def _dir_data(self, n: Node, col: int, role):
        top = n.parent is self._root
        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_NAME:
                return os.path.basename(n.path) or n.path if top else n.name
            if col == COL_FORMAT:
                return f"{n.file_count} file{'s' if n.file_count != 1 else ''}"
            return None
        if role == Qt.ItemDataRole.DecorationRole and col == COL_NAME:
            return self._dir_icon
        if role == Qt.ItemDataRole.ToolTipRole:
            return _home_short(n.path)
        if role == Qt.ItemDataRole.FontRole and col == COL_NAME and n.path in self._dirty_dirs:
            f = QFont()
            f.setBold(True)
            return f
        if role == Qt.ItemDataRole.ForegroundRole and col == COL_FORMAT:
            return QBrush(QColor("#888"))
        return None


class FileTreeProxy(QSortFilterProxyModel):
    """Folders first, natural-ish name order; filtering keeps matching
    files' folders and the contents of matching folders."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterKeyColumn(COL_NAME)
        self.setRecursiveFilteringEnabled(True)
        self.setAutoAcceptChildRows(True)
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def lessThan(self, left, right):
        ld, rd = left.data(IS_DIR_ROLE), right.data(IS_DIR_ROLE)
        if ld != rd:  # folders before files, whatever the sort order
            asc = self.sortOrder() == Qt.SortOrder.AscendingOrder
            return bool(ld) if asc else bool(rd)
        if left.column() == COL_TAGS:
            a, b = left.data(), right.data()
            if isinstance(a, int) and isinstance(b, int):
                return a < b
        a = (left.data(Qt.ItemDataRole.UserRole) if left.column() == COL_NAME else left.data()) or ""
        b = (right.data(Qt.ItemDataRole.UserRole) if right.column() == COL_NAME else right.data()) or ""
        return str(a).lower() < str(b).lower()


class FileTreeView(QTreeView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSortingEnabled(True)
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(True)
        self.setAnimated(False)
        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._state = None

    def setModel(self, proxy):
        super().setModel(proxy)
        src = proxy.sourceModel()
        src.modelAboutToBeReset.connect(self._save_state)
        src.modelReset.connect(self._restore_state)
        src.folders_added.connect(self._expand_paths)
        self.header().setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        self.setColumnWidth(COL_FORMAT, 70)
        self.setColumnWidth(COL_TAGS, 45)
        self.sortByColumn(COL_NAME, Qt.SortOrder.AscendingOrder)

    # ---------------------------------------------------------- helpers
    @property
    def proxy(self) -> FileTreeProxy:
        return self.model()

    @property
    def source(self) -> FileTreeModel:
        return self.model().sourceModel()

    def proxy_index(self, path: str) -> QModelIndex:
        return self.proxy.mapFromSource(self.source.index_for_path(path))

    def leaf_paths(self, parent: QModelIndex = QModelIndex()) -> list[str]:
        """Files below ``parent`` in display order (respects filter and sort)."""
        out: list[str] = []
        m = self.proxy
        for r in range(m.rowCount(parent)):
            idx = m.index(r, 0, parent)
            if idx.data(IS_DIR_ROLE):
                out.extend(self.leaf_paths(idx))
            else:
                out.append(idx.data(Qt.ItemDataRole.UserRole))
        return out

    def selected_paths(self) -> list[str]:
        seen: dict[str, None] = {}
        for idx in self.selectionModel().selectedRows():
            if idx.data(IS_DIR_ROLE):
                for p in self.leaf_paths(idx):
                    seen.setdefault(p, None)
            else:
                seen.setdefault(idx.data(Qt.ItemDataRole.UserRole), None)
        return list(seen)

    def all_paths(self) -> list[str]:
        return self.leaf_paths()

    def current_path(self) -> str | None:
        idx = self.currentIndex()
        return idx.data(Qt.ItemDataRole.UserRole) if idx.isValid() else None

    def current_is_dir(self) -> bool:
        idx = self.currentIndex()
        return bool(idx.isValid() and idx.data(IS_DIR_ROLE))

    def select_paths(self, paths: list[str], current: str | None = None) -> None:
        sel = QItemSelection()
        for p in paths:
            idx = self.proxy_index(p)
            if idx.isValid():
                sel.select(idx, idx)
                self._expand_to(idx)
        sm = self.selectionModel()
        flags = QItemSelectionModel.SelectionFlag
        cur = self.proxy_index(current) if current else QModelIndex()
        if cur.isValid():
            sm.setCurrentIndex(cur, flags.NoUpdate)
        sm.select(sel, flags.ClearAndSelect | flags.Rows)
        if cur.isValid():
            self.scrollTo(cur)

    def select_path(self, path: str) -> None:
        self.select_paths([path], current=path)

    def _expand_to(self, idx: QModelIndex) -> None:
        p = idx.parent()
        while p.isValid():
            self.expand(p)
            p = p.parent()

    def _expand_paths(self, paths: list[str]) -> None:
        for p in paths:
            idx = self.proxy_index(p)
            if idx.isValid():
                self.expand(idx)

    # ---------------------------------------- keep state across rebuilds
    def _save_state(self) -> None:
        expanded: list[str] = []

        def walk(parent):
            m = self.proxy
            for r in range(m.rowCount(parent)):
                idx = m.index(r, 0, parent)
                if idx.data(IS_DIR_ROLE):
                    if self.isExpanded(idx):
                        expanded.append(idx.data(Qt.ItemDataRole.UserRole))
                    walk(idx)

        walk(QModelIndex())
        selected = [i.data(Qt.ItemDataRole.UserRole) for i in self.selectionModel().selectedRows()]
        self._state = (expanded, selected, self.current_path())

    def _restore_state(self) -> None:
        if self._state is None:
            return
        expanded, selected, current = self._state
        self._state = None
        remap = self.source.last_remap

        def fix(p):
            if p is None:
                return None
            if p in remap:
                return remap[p]
            for old, new in remap.items():  # folder renames move everything below
                if p.startswith(old + os.sep):
                    return new + p[len(old):]
            return p

        for p in expanded:
            idx = self.proxy_index(fix(p))
            if idx.isValid():
                self.expand(idx)
        self.select_paths([fix(p) for p in selected], current=fix(current))
