"""Pick a tag system + frame/atom/field to add."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QVBoxLayout,
)

from ..core.model import TagEntry
from ..core.tagfile import TagFile

HINTS = {
    "ID3v2": "Custom text tags: pick TXXX (user-defined text) and set its description.",
    "MP4": "Custom tags: pick ---- (freeform) and set its key, e.g. ----:com.apple.iTunes:MOOD.",
    "Vorbis": "Any field name works: pick one and change its name.",
    "APEv2": "Any item key works: pick one and change its key.",
    "ASF": "Any attribute name works: pick one and change its name.",
}


class AddTagDialog(QDialog):
    def __init__(self, systems: dict[str, str], parent=None) -> None:
        """``systems``: system -> path of a selected file that supports it."""
        super().__init__(parent)
        self.setWindowTitle("Add tag")
        self.resize(520, 560)
        self.systems = systems
        self._cache: dict[str, list[TagEntry]] = {}

        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("Tag system:"))
        self.system_box = QComboBox()
        for s in systems:
            self.system_box.addItem(s)
        row.addWidget(self.system_box, 1)
        lay.addLayout(row)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: palette(mid);")
        lay.addWidget(self.hint)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter frames… (e.g. TXXX, podcast, comment)")
        self.search.setClearButtonEnabled(True)
        lay.addWidget(self.search)
        self.list = QListWidget()
        lay.addWidget(self.list, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.ok = buttons.button(QDialogButtonBox.StandardButton.Ok)

        self.system_box.currentTextChanged.connect(self._populate)
        self.search.textChanged.connect(self._filter)
        self.list.itemDoubleClicked.connect(lambda *_: self.accept())
        self.list.currentItemChanged.connect(lambda cur, _: self.ok.setEnabled(cur is not None))
        self._populate(self.system_box.currentText())
        self.search.setFocus()

    def _templates(self, system: str) -> list[TagEntry]:
        if system not in self._cache:
            try:
                self._cache[system] = TagFile(self.systems[system]).adapter(system).templates()
            except Exception:
                self._cache[system] = []
        return self._cache[system]

    def _populate(self, system: str) -> None:
        self.hint.setText(HINTS.get(system, ""))
        self.list.clear()
        for t in self._templates(system):
            label = t.frame_id if t.frame_id != "----" else t.key
            item = QListWidgetItem(f"{label}  —  {t.description}" if t.description else label)
            item.setData(Qt.ItemDataRole.UserRole, t)
            self.list.addItem(item)
        self._filter(self.search.text())

    def _filter(self, text: str) -> None:
        text = text.lower()
        first = None
        for i in range(self.list.count()):
            item = self.list.item(i)
            hidden = bool(text) and text not in item.text().lower()
            item.setHidden(hidden)
            if not hidden and first is None:
                first = item
        self.list.setCurrentItem(first)
        self.ok.setEnabled(first is not None)

    def selected(self) -> TagEntry | None:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole).clone() if item else None
