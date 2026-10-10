"""Table of (merged) tag entries for the selected files."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPalette
from PySide6.QtWidgets import QAbstractItemView, QApplication, QHeaderView, QTableView

from ..core.model import KEY_FIELDS, META_FIELDS, FieldType, TagEntry, details
from ..core.session import MergedRow, Session

COLUMNS = ["System", "Key", "Description", "Value", "Details"]
COL_SYSTEM, COL_KEY, COL_DESC, COL_VALUE, COL_DETAILS = range(5)

INLINE_TYPES = {FieldType.TEXT, FieldType.LANG, FieldType.INT, FieldType.TEXT_LIST,
                FieldType.INT_LIST, FieldType.PAIR_LIST}


def content_field(entry: TagEntry):
    """The single editable content field, if the entry can be edited inline."""
    if entry.readonly:
        return None
    content = [f for f in entry.fields if f.name not in META_FIELDS | KEY_FIELDS]
    if len(content) != 1:
        return None
    f = content[0]
    if f.readonly or f.ftype not in INLINE_TYPES:
        return None
    if f.ftype == FieldType.TEXT_LIST and (len(f.value) > 1 or any("\n" in v for v in f.value)):
        return None
    return f


def display_key(key: str) -> str:
    """Keys can embed raw bytes (e.g. ID3 PRIV/UFID data); escape them."""
    return "".join(c if c.isprintable() else f"\\x{ord(c):02x}" for c in key)


def _dark() -> bool:
    return QApplication.palette().color(QPalette.ColorRole.Base).lightness() < 128


class TagTableModel(QAbstractTableModel):
    # (row, new inline text)
    inline_edited = Signal(object, str)

    def __init__(self, session: Session, parent=None) -> None:
        super().__init__(parent)
        self.session = session
        self.rows: list[MergedRow] = []
        self.paths: list[str] = []

    def set_paths(self, paths: list[str]) -> None:
        self.beginResetModel()
        self.paths = list(paths)
        self.rows = self.session.merged(self.paths)
        self.endResetModel()

    def refresh(self) -> None:
        self.set_paths(self.paths)

    # -- helpers -------------------------------------------------------------
    def row_state(self, row: MergedRow) -> str:
        states = {self.session.files[p].entry_state(e) for p, e in row.entries.items()}
        if "modified" in states:
            return "modified"
        if "new" in states:
            return "new"
        return ""

    def value_text(self, row: MergedRow) -> str:
        if not row.uniform:
            return f"<{len(row.entries)} different values>"
        return row.first.summary()

    # -- Qt model API --------------------------------------------------------
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        e = row.first
        col = index.column()
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            if col == COL_SYSTEM:
                return e.system
            if col == COL_KEY:
                return display_key(e.key)
            if col == COL_DESC:
                desc = e.description
                if row.partial:
                    desc = f"{desc} [in {len(row.entries)}/{row.total} files]".strip()
                return desc
            if col == COL_VALUE:
                text = self.value_text(row)
                if role == Qt.ItemDataRole.DisplayRole and len(text) > 300:
                    text = text[:300] + "…"
                return text
            if col == COL_DETAILS:
                return details(e) if row.uniform else ""
        if role == Qt.ItemDataRole.EditRole and col == COL_VALUE:
            f = content_field(e)
            if f is None:
                return None
            if f.ftype == FieldType.TEXT_LIST:
                return f.value[0] if f.value else ""
            return self.value_text(row) if row.uniform else ""
        if role == Qt.ItemDataRole.FontRole:
            state = self.row_state(row)
            font = QFont()
            if state:
                font.setBold(True)
            if e.readonly:
                font.setItalic(True)
            if col == COL_KEY:
                font.setFamily("monospace")
                font.setStyleHint(QFont.StyleHint.Monospace)
            return font
        if role == Qt.ItemDataRole.BackgroundRole:
            state = self.row_state(row)
            if state == "new":
                return QBrush(QColor("#1f4d2b" if _dark() else "#e3f6e6"))
            if state == "modified":
                return QBrush(QColor("#5a4a12" if _dark() else "#fff4cc"))
        if role == Qt.ItemDataRole.ForegroundRole and (row.partial or not row.uniform) \
                and col == COL_VALUE and not row.uniform:
            return QBrush(QColor("#888"))
        return None

    def flags(self, index):
        base = super().flags(index)
        if index.isValid() and index.column() == COL_VALUE:
            row = self.rows[index.row()]
            if all(content_field(e) is not None for e in row.entries.values()):
                return base | Qt.ItemFlag.ItemIsEditable
        return base

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or index.column() != COL_VALUE:
            return False
        self.inline_edited.emit(self.rows[index.row()], str(value))
        return True


class TagFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterKeyColumn(-1)


class TagTableView(QTableView):
    activated_row = Signal(object)   # MergedRow
    delete_pressed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.EditKeyPressed
                             | QAbstractItemView.EditTrigger.SelectedClicked)
        self.setSortingEnabled(True)
        self.setWordWrap(False)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(24)
        h = self.horizontalHeader()
        h.setStretchLastSection(True)
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.doubleClicked.connect(self._double_clicked)

    def setModel(self, model):
        super().setModel(model)
        self.setColumnWidth(COL_SYSTEM, 70)
        self.setColumnWidth(COL_KEY, 220)
        self.setColumnWidth(COL_DESC, 200)
        self.setColumnWidth(COL_VALUE, 360)
        self.sortByColumn(-1, Qt.SortOrder.AscendingOrder)

    def source_row(self, proxy_index) -> MergedRow:
        proxy = self.model()
        src = proxy.mapToSource(proxy_index)
        return proxy.sourceModel().rows[src.row()]

    def selected_rows(self) -> list[MergedRow]:
        return [self.source_row(i) for i in self.selectionModel().selectedRows()]

    def current_row(self) -> MergedRow | None:
        idx = self.currentIndex()
        return self.source_row(idx) if idx.isValid() else None

    def _double_clicked(self, index):
        self.activated_row.emit(self.source_row(index))

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.state() != \
                QAbstractItemView.State.EditingState:
            self.delete_pressed.emit()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.currentIndex().isValid() \
                and self.state() != QAbstractItemView.State.EditingState:
            self.activated_row.emit(self.source_row(self.currentIndex()))
            return
        super().keyPressEvent(event)
