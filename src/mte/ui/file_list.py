"""List of loaded files."""

from __future__ import annotations

import os

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView

from ..core.session import Session

COLUMNS = ["", "File", "Format", "Tags", "Folder"]
COL_DIRTY, COL_NAME, COL_FORMAT, COL_TAGS, COL_FOLDER = range(5)


class FileListModel(QAbstractTableModel):
    def __init__(self, session: Session, parent=None) -> None:
        super().__init__(parent)
        self.session = session
        self.paths: list[str] = []

    def add_paths(self, paths: list[str]) -> None:
        new = [p for p in paths if p not in self.paths]
        if not new:
            return
        self.beginInsertRows(QModelIndex(), len(self.paths), len(self.paths) + len(new) - 1)
        self.paths.extend(new)
        self.endInsertRows()

    def replace_path(self, old: str, new: str) -> None:
        if old in self.paths:
            r = self.paths.index(old)
            self.paths[r] = new
            self.dataChanged.emit(self.index(r, 0), self.index(r, len(COLUMNS) - 1))

    def remove_paths(self, paths) -> None:
        gone = set(paths)
        self.beginResetModel()
        self.paths = [p for p in self.paths if p not in gone]
        self.endResetModel()

    def clear(self) -> None:
        self.beginResetModel()
        self.paths = []
        self.endResetModel()

    def refresh(self, paths=None) -> None:
        if not self.paths:
            return
        if paths is None:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.paths) - 1, len(COLUMNS) - 1))
            return
        for p in paths:
            if p in self.paths:
                r = self.paths.index(p)
                self.dataChanged.emit(self.index(r, 0), self.index(r, len(COLUMNS) - 1))

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.paths)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        path = self.paths[index.row()]
        st = self.session.files.get(path)
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_DIRTY:
                return "●" if st and st.dirty else ""
            if col == COL_NAME:
                return os.path.basename(path)
            if col == COL_FOLDER:
                return os.path.dirname(path)
            if col == COL_FORMAT:
                return st.original.format_name if st else ""
            if col == COL_TAGS:
                if st and st.original.error:
                    return "error"
                return len(st.working) if st else ""
        if role == Qt.ItemDataRole.ToolTipRole:
            if st and st.original.error:
                return f"{path}\n\n{st.original.error}"
            if st:
                info = ", ".join(f"{k}: {v}" for k, v in st.original.info.items())
                return f"{path}\n{info}"
            return path
        if role == Qt.ItemDataRole.ForegroundRole:
            if st and st.original.error:
                return QBrush(QColor("#c0392b"))
            if col == COL_DIRTY:
                return QBrush(QColor("#e67e22"))
        if role == Qt.ItemDataRole.FontRole and st and st.dirty and col == COL_NAME:
            f = QFont()
            f.setBold(True)
            return f
        if role == Qt.ItemDataRole.UserRole:
            return path
        if role == Qt.ItemDataRole.TextAlignmentRole and col == COL_TAGS:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None


class FileFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterKeyColumn(-1)

    def lessThan(self, left, right):
        if left.column() == COL_TAGS:
            a, b = left.data(), right.data()
            if isinstance(a, int) and isinstance(b, int):
                return a < b
        return super().lessThan(left, right)


class FileListView(QTableView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSortingEnabled(True)
        self.setWordWrap(False)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(22)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

    def setModel(self, model):
        super().setModel(model)
        self.setColumnWidth(COL_DIRTY, 22)
        self.setColumnWidth(COL_NAME, 240)
        self.setColumnWidth(COL_FORMAT, 70)
        self.setColumnWidth(COL_TAGS, 45)
        self.sortByColumn(-1, Qt.SortOrder.AscendingOrder)

    def selected_paths(self) -> list[str]:
        return [i.data(Qt.ItemDataRole.UserRole) for i in self.selectionModel().selectedRows()]

    def all_paths(self) -> list[str]:
        m = self.model()
        return [m.index(r, 0).data(Qt.ItemDataRole.UserRole) for r in range(m.rowCount())]
