"""One editor widget per :class:`FieldType`."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QSize, Qt, Signal
from PySide6.QtGui import QFontDatabase, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListView, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...core.formats.base import sniff_mime
from ...core.model import Field, FieldType, Picture, format_value

HEX_PREVIEW_BYTES = 4096


def mono_font():
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)


def hexdump(data: bytes, limit: int = HEX_PREVIEW_BYTES) -> str:
    lines = []
    for off in range(0, min(len(data), limit), 16):
        chunk = data[off:off + 16]
        hexpart = " ".join(f"{b:02x}" for b in chunk)
        text = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{off:08x}  {hexpart:<47}  {text}")
    if len(data) > limit:
        lines.append(f"… {len(data) - limit} more bytes")
    return "\n".join(lines)


def image_pixmap(data: bytes, max_side: int = 220) -> QPixmap | None:
    img = QImage()
    if not img.loadFromData(QByteArray(data)):
        return None
    pm = QPixmap.fromImage(img)
    if max(pm.width(), pm.height()) > max_side:
        pm = pm.scaled(max_side, max_side, Qt.AspectRatioMode.KeepAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
    return pm


def _small_button(text: str, tip: str = "") -> QPushButton:
    b = QPushButton(text)
    b.setToolTip(tip)
    b.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return b


class FieldWidget(QWidget):
    changed = Signal()

    def __init__(self, field: Field, parent=None) -> None:
        super().__init__(parent)
        self.field = field
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(0, 0, 0, 0)

    def value(self):
        raise NotImplementedError

    def set_value(self, value) -> None:
        raise NotImplementedError

    def set_readonly(self, ro: bool) -> None:
        self.setEnabled(not ro)


class TextWidget(FieldWidget):
    def __init__(self, field, parent=None):
        super().__init__(field, parent)
        self.edit = QLineEdit()
        if field.ftype == FieldType.LANG:
            self.edit.setMaxLength(3)
            self.edit.setPlaceholderText("eng / xxx")
            self.edit.setMaximumWidth(80)
        self.layout_.addWidget(self.edit)
        self.edit.textChanged.connect(self.changed)
        self.set_value(field.value)

    def value(self):
        return self.edit.text()

    def set_value(self, value):
        self.edit.setText("" if value is None else str(value))

    def set_readonly(self, ro):
        self.edit.setReadOnly(ro)


class MultilineWidget(FieldWidget):
    def __init__(self, field, parent=None):
        super().__init__(field, parent)
        self.edit = QPlainTextEdit()
        self.edit.setMinimumHeight(120)
        self.layout_.addWidget(self.edit)
        self.edit.textChanged.connect(self.changed)
        self.set_value(field.value)

    def value(self):
        return self.edit.toPlainText()

    def set_value(self, value):
        self.edit.setPlainText("" if value is None else str(value))

    def set_readonly(self, ro):
        self.edit.setReadOnly(ro)


class TextListWidget(FieldWidget):
    """Multi-value text: list of values + full-text editor for the selected one
    (values may contain newlines, e.g. lyrics)."""

    def __init__(self, field, parent=None):
        super().__init__(field, parent)
        row = QHBoxLayout()
        self.list = QListWidget()
        self.list.setMaximumHeight(110)
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        row.addWidget(self.list, 1)
        buttons = QVBoxLayout()
        self.add_btn = _small_button("+", "Add a value")
        self.del_btn = _small_button("−", "Remove the selected value")
        buttons.addWidget(self.add_btn)
        buttons.addWidget(self.del_btn)
        buttons.addStretch()
        row.addLayout(buttons)
        self.layout_.addLayout(row)
        self.detail = QPlainTextEdit()
        self.detail.setPlaceholderText("Selected value (multi-line allowed)")
        self.detail.setMaximumHeight(160)
        self.layout_.addWidget(self.detail)
        self._syncing = False
        self.add_btn.clicked.connect(self._add)
        self.del_btn.clicked.connect(self._remove)
        self.list.currentRowChanged.connect(self._show_current)
        self.detail.textChanged.connect(self._detail_edited)
        self.list.model().rowsMoved.connect(lambda *a: self.changed.emit())
        self.set_value(field.value)

    def _label(self, text: str) -> str:
        return text.replace("\n", " ⏎ ") if text else "(empty)"

    def _add(self):
        item = QListWidgetItem(self._label(""))
        item.setData(Qt.ItemDataRole.UserRole, "")
        self.list.addItem(item)
        self.list.setCurrentItem(item)
        self.detail.setFocus()
        self.changed.emit()

    def _remove(self):
        row = self.list.currentRow()
        if row >= 0:
            self.list.takeItem(row)
            self.changed.emit()
            self._show_current(self.list.currentRow())

    def _show_current(self, row):
        self._syncing = True
        item = self.list.item(row) if row >= 0 else None
        self.detail.setEnabled(item is not None)
        self.detail.setPlainText(item.data(Qt.ItemDataRole.UserRole) if item else "")
        self._syncing = False

    def _detail_edited(self):
        if self._syncing:
            return
        item = self.list.currentItem()
        if item is None:
            # typing with no values yet creates the first value
            self._add()
            item = self.list.currentItem()
        text = self.detail.toPlainText()
        item.setData(Qt.ItemDataRole.UserRole, text)
        item.setText(self._label(text))
        self.changed.emit()

    def value(self):
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]

    def set_value(self, value):
        self.list.clear()
        for v in value or []:
            item = QListWidgetItem(self._label(str(v)))
            item.setData(Qt.ItemDataRole.UserRole, str(v))
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        else:
            self._show_current(-1)
            self.detail.setEnabled(True)

    def set_readonly(self, ro):
        self.add_btn.setEnabled(not ro)
        self.del_btn.setEnabled(not ro)
        self.detail.setReadOnly(ro)


class IntWidget(FieldWidget):
    def __init__(self, field, parent=None):
        super().__init__(field, parent)
        self.edit = QLineEdit()
        self.edit.setMaximumWidth(200)
        self.layout_.addWidget(self.edit)
        self.edit.textChanged.connect(self.changed)
        self.set_value(field.value)

    def value(self):
        text = self.edit.text().strip() or "0"
        try:
            return int(text, 0)
        except ValueError:
            raise ValueError(f"{self.field.title}: {text!r} is not an integer") from None

    def set_value(self, value):
        self.edit.setText("" if value is None else str(value))

    def set_readonly(self, ro):
        self.edit.setReadOnly(ro)


class ListLineWidget(FieldWidget):
    """INT_LIST ("1 ; 2") and PAIR_LIST ("3/12 ; 1/2") as a single line."""

    def __init__(self, field, parent=None):
        super().__init__(field, parent)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("3/12 ; 1/2" if field.ftype == FieldType.PAIR_LIST
                                     else "values separated by ;")
        self.layout_.addWidget(self.edit)
        self.edit.textChanged.connect(self.changed)
        self.set_value(field.value)

    def value(self):
        parts = [p.strip() for p in self.edit.text().split(";") if p.strip()]
        try:
            if self.field.ftype == FieldType.PAIR_LIST:
                out = []
                for p in parts:
                    a, _, b = p.partition("/")
                    out.append((int(a or 0), int(b or 0)))
                return out
            return [int(p, 0) for p in parts]
        except ValueError:
            raise ValueError(f"{self.field.title}: can't parse {self.edit.text()!r}") from None

    def set_value(self, value):
        self.edit.setText(format_value(Field("", self.field.ftype, value or [])))

    def set_readonly(self, ro):
        self.edit.setReadOnly(ro)


class PeopleWidget(FieldWidget):
    def __init__(self, field, parent=None):
        super().__init__(field, parent)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Involvement", "Person"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setMaximumHeight(150)
        self.layout_.addWidget(self.table)
        row = QHBoxLayout()
        add, rem = _small_button("+"), _small_button("−")
        row.addWidget(add)
        row.addWidget(rem)
        row.addStretch()
        self.layout_.addLayout(row)
        add.clicked.connect(lambda: (self.table.insertRow(self.table.rowCount()), self.changed.emit()))
        rem.clicked.connect(lambda: (self.table.removeRow(self.table.currentRow()), self.changed.emit()))
        self.table.itemChanged.connect(lambda *_: self.changed.emit())
        self.set_value(field.value)

    def value(self):
        out = []
        for r in range(self.table.rowCount()):
            cells = [self.table.item(r, c) for c in (0, 1)]
            out.append(tuple(c.text() if c else "" for c in cells))
        return out

    def set_value(self, value):
        self.table.setRowCount(0)
        for a, b in value or []:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(a))
            self.table.setItem(r, 1, QTableWidgetItem(b))


class BoolWidget(FieldWidget):
    def __init__(self, field, parent=None):
        super().__init__(field, parent)
        self.box = QCheckBox()
        self.layout_.addWidget(self.box)
        self.box.toggled.connect(self.changed)
        self.set_value(field.value)

    def value(self):
        return self.box.isChecked()

    def set_value(self, value):
        self.box.setChecked(bool(value))


class ChoiceWidget(FieldWidget):
    def __init__(self, field, parent=None):
        super().__init__(field, parent)
        self.combo = QComboBox()
        for v, label in field.choices or []:
            self.combo.addItem(label, v)
        self.layout_.addWidget(self.combo)
        self.combo.currentIndexChanged.connect(self.changed)
        self.set_value(field.value)

    def value(self):
        return self.combo.currentData()

    def set_value(self, value):
        idx = self.combo.findData(value)
        if idx < 0:  # value outside the known choices: keep it selectable
            self.combo.addItem(f"{value} (unknown)", value)
            idx = self.combo.count() - 1
        self.combo.setCurrentIndex(idx)


class BytesWidget(FieldWidget):
    """Binary payload: image preview or hex dump, plus import/export."""

    imported = Signal(bytes)

    def __init__(self, field, parent=None):
        super().__init__(field, parent)
        self._data = b""
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.layout_.addWidget(self.preview)
        self.hex = QPlainTextEdit()
        self.hex.setReadOnly(True)
        self.hex.setFont(mono_font())
        self.hex.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.hex.setMinimumHeight(110)
        self.layout_.addWidget(self.hex)
        row = QHBoxLayout()
        self.info = QLabel()
        self.import_btn = QPushButton("Import…")
        self.export_btn = QPushButton("Export…")
        row.addWidget(self.info, 1)
        row.addWidget(self.import_btn)
        row.addWidget(self.export_btn)
        self.layout_.addLayout(row)
        self.import_btn.clicked.connect(self._import)
        self.export_btn.clicked.connect(self._export)
        self.set_value(field.value)

    def _refresh(self):
        data = self._data
        mime = sniff_mime(data, "")
        pm = image_pixmap(data) if mime.startswith("image/") else None
        self.preview.setVisible(pm is not None)
        self.hex.setVisible(pm is None)
        if pm is not None:
            self.preview.setPixmap(pm)
        else:
            self.hex.setPlainText(hexdump(data))
        self.info.setText(f"{len(data):,} bytes" + (f" · {mime}" if mime else ""))
        self.export_btn.setEnabled(bool(data))

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import binary data")
        if not path:
            return
        with open(path, "rb") as f:
            self._data = f.read()
        self._refresh()
        self.imported.emit(self._data)
        self.changed.emit()

    def _export(self):
        ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif"}.get(
            sniff_mime(self._data, ""), ".bin")
        path, _ = QFileDialog.getSaveFileName(self, "Export binary data", f"{self.field.name}{ext}")
        if path:
            with open(path, "wb") as f:
                f.write(self._data)

    def value(self):
        return self._data

    def set_value(self, value):
        self._data = bytes(value or b"")
        self._refresh()

    def set_readonly(self, ro):
        self.import_btn.setEnabled(not ro)


class PicturesWidget(FieldWidget):
    """MP4 ``covr``: several images in one atom."""

    def __init__(self, field, parent=None):
        super().__init__(field, parent)
        self.list = QListWidget()
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setIconSize(QSize(120, 120))
        self.list.setMinimumHeight(160)
        self.list.setMovement(QListView.Movement.Snap)
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.layout_.addWidget(self.list)
        row = QHBoxLayout()
        self.add_btn, self.del_btn, self.exp_btn = (
            QPushButton("Add image…"), QPushButton("Remove"), QPushButton("Export…"))
        for b in (self.add_btn, self.del_btn, self.exp_btn):
            row.addWidget(b)
        row.addStretch()
        self.layout_.addLayout(row)
        self.add_btn.clicked.connect(self._add)
        self.del_btn.clicked.connect(self._remove)
        self.exp_btn.clicked.connect(self._export)
        self.set_value(field.value)

    def _item(self, pic: Picture) -> QListWidgetItem:
        pm = image_pixmap(pic.data, 120)
        item = QListWidgetItem(QIcon(pm) if pm else QIcon(), f"{pic.mime}\n{len(pic.data):,} B")
        item.setData(Qt.ItemDataRole.UserRole, pic)
        return item

    def _add(self):
        path, _ = QFileDialog.getOpenFileName(self, "Add image", filter="Images (*.jpg *.jpeg *.png)")
        if not path:
            return
        with open(path, "rb") as f:
            data = f.read()
        mime = sniff_mime(data, "")
        if mime not in ("image/jpeg", "image/png"):
            QMessageBox.warning(self, "Unsupported image", "MP4 cover art must be JPEG or PNG.")
            return
        self.list.addItem(self._item(Picture(data, mime)))
        self.changed.emit()

    def _remove(self):
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))
        self.changed.emit()

    def _export(self):
        item = self.list.currentItem()
        if not item:
            return
        pic: Picture = item.data(Qt.ItemDataRole.UserRole)
        ext = ".png" if pic.mime == "image/png" else ".jpg"
        path, _ = QFileDialog.getSaveFileName(self, "Export image", f"cover{ext}")
        if path:
            with open(path, "wb") as f:
                f.write(pic.data)

    def value(self):
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]

    def set_value(self, value):
        self.list.clear()
        for pic in value or []:
            self.list.addItem(self._item(pic))


class OpaqueWidget(FieldWidget):
    def __init__(self, field, parent=None):
        super().__init__(field, parent)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumHeight(120)
        self.layout_.addWidget(self.view)
        self._value = None
        self.set_value(field.value)

    def value(self):
        return self._value

    def set_value(self, value):
        self._value = value
        self.view.setPlainText(format_value(Field("", FieldType.OPAQUE, value)))


WIDGETS = {
    FieldType.TEXT: TextWidget,
    FieldType.LANG: TextWidget,
    FieldType.MULTILINE: MultilineWidget,
    FieldType.TEXT_LIST: TextListWidget,
    FieldType.INT: IntWidget,
    FieldType.INT_LIST: ListLineWidget,
    FieldType.PAIR_LIST: ListLineWidget,
    FieldType.PEOPLE: PeopleWidget,
    FieldType.BOOL: BoolWidget,
    FieldType.CHOICE: ChoiceWidget,
    FieldType.BYTES: BytesWidget,
    FieldType.PICTURES: PicturesWidget,
    FieldType.OPAQUE: OpaqueWidget,
}


def widget_for(field: Field) -> FieldWidget:
    w = WIDGETS[field.ftype](field)
    if field.readonly:
        w.set_readonly(True)
    return w
