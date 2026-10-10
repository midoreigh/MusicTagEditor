"""Full frame-level editor for one tag entry (applied to one or many files)."""

from __future__ import annotations

import html
from dataclasses import dataclass

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from ...core.formats import key_for
from ...core.formats.base import TagError, sniff_mime
from ...core.model import TagEntry
from .fields import BytesWidget, FieldWidget, widget_for


@dataclass
class FileNav:
    has_prev: bool
    has_next: bool
    label: str = ""       # current file name
    position: str = ""    # e.g. "3 of 12"


class EntryDialog(QDialog):
    def __init__(self, entry: TagEntry, *, file_count: int = 1, differing: set[str] = frozenset(),
                 is_new: bool = False, position: tuple[int, int] | None = None,
                 file_nav: "FileNav | None" = None, missing: bool = False,
                 parent=None) -> None:
        """``position`` = (index, total) of the tag in the table; enables the
        Previous/Next (tag) buttons. ``file_nav`` enables Previous/Next file,
        which keep the same tag. ``missing``: the current file doesn't have
        this tag yet (it is only added if the user enters something).

        After exec(), ``nav`` is -1/+1 for tag navigation and ``file_nav_step``
        -1/+1 for file navigation (0 = OK / Cancel)."""
        super().__init__(parent)
        self.nav = 0
        self.file_nav_step = 0
        self.missing = missing
        self.entry = entry.clone()
        self.is_new = is_new
        self.differing = set(differing)
        self.setWindowTitle(("Add " if is_new else "Edit ") + f"{entry.system} {entry.frame_id}")
        self.resize(620, 520)

        outer = QVBoxLayout(self)
        head = QLabel(f"<b>{entry.system}</b> · <code>{entry.frame_id}</code>"
                      + (f" — {entry.description}" if entry.description else ""))
        head.setWordWrap(True)
        outer.addWidget(head)
        self.key_label = QLabel()
        outer.addWidget(self.key_label)
        if file_nav is not None and file_nav.label:
            fl = QLabel(f"File: <b>{html.escape(file_nav.label)}</b>")
            fl.setWordWrap(True)
            outer.addWidget(fl)
        if missing:
            miss = QLabel("This file doesn't have this tag. Enter a value to add it; "
                          "leave it unchanged to skip this file.")
            miss.setWordWrap(True)
            miss.setStyleSheet("color: #b35c00;")
            outer.addWidget(miss)

        if file_count > 1:
            note = QLabel(
                f"Applies to <b>{file_count}</b> files. "
                + ("Only the fields you change are written; " if not is_new else "")
                + ("fields marked ≠ currently differ between files." if self.differing else ""))
            note.setWordWrap(True)
            note.setStyleSheet("color: palette(highlight);")
            outer.addWidget(note)
        if entry.readonly:
            ro = QLabel("This entry is read-only (it can only be deleted).")
            ro.setStyleSheet("color: #b35c00;")
            outer.addWidget(ro)

        form_host = QWidget()
        form = QFormLayout(form_host)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.widgets: dict[str, FieldWidget] = {}
        for f in self.entry.fields:
            w = widget_for(f)
            if entry.readonly:
                w.set_readonly(True)
            label = f.title + (" ≠" if f.name in self.differing else "")
            form.addRow(label, w)
            self.widgets[f.name] = w
            w.changed.connect(self._update_key)
        # importing an image into a picture frame updates its MIME type field
        if "mime" in self.widgets and isinstance(self.widgets.get("data"), BytesWidget):
            self.widgets["data"].imported.connect(self._on_image_imported)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_host)
        outer.addWidget(scroll, 1)

        nav_row = QHBoxLayout()
        bottom = QHBoxLayout()
        if position is not None:
            index, total = position
            self.prev_btn = QPushButton("◀ Previous")
            self.next_btn = QPushButton("Next ▶")
            self.prev_btn.setShortcut(QKeySequence("Ctrl+["))
            self.next_btn.setShortcut(QKeySequence("Ctrl+]"))
            self.prev_btn.setToolTip("Keep changes and edit the previous tag (Ctrl+[)")
            self.next_btn.setToolTip("Keep changes and edit the next tag (Ctrl+])")
            for b in (self.prev_btn, self.next_btn):
                b.setAutoDefault(False)
            self.prev_btn.setEnabled(index > 0)
            self.next_btn.setEnabled(index < total - 1)
            self.prev_btn.clicked.connect(lambda: self._navigate(-1))
            self.next_btn.clicked.connect(lambda: self._navigate(1))
            nav_row.addWidget(QLabel("Tag:"))
            nav_row.addWidget(self.prev_btn)
            nav_row.addWidget(self.next_btn)
            pos_label = QLabel(f"{index + 1} of {total}")
            pos_label.setStyleSheet("color: palette(mid);")
            nav_row.addWidget(pos_label)
            nav_row.addSpacing(16)
        if file_nav is not None:
            self.prev_file_btn = QPushButton("▲ Previous file")
            self.next_file_btn = QPushButton("Next file ▼")
            self.prev_file_btn.setShortcut(QKeySequence("Ctrl+PgUp"))
            self.next_file_btn.setShortcut(QKeySequence("Ctrl+PgDown"))
            self.prev_file_btn.setToolTip("Keep changes and edit this tag in the previous file "
                                          "(Ctrl+PgUp)")
            self.next_file_btn.setToolTip("Keep changes and edit this tag in the next file "
                                          "(Ctrl+PgDown)")
            for b in (self.prev_file_btn, self.next_file_btn):
                b.setAutoDefault(False)
            self.prev_file_btn.setEnabled(file_nav.has_prev)
            self.next_file_btn.setEnabled(file_nav.has_next)
            self.prev_file_btn.clicked.connect(lambda: self._navigate(-1, files=True))
            self.next_file_btn.clicked.connect(lambda: self._navigate(1, files=True))
            nav_row.addWidget(QLabel("File:"))
            nav_row.addWidget(self.prev_file_btn)
            nav_row.addWidget(self.next_file_btn)
            if file_nav.position:
                fpos = QLabel(file_nav.position)
                fpos.setStyleSheet("color: palette(mid);")
                nav_row.addWidget(fpos)
        nav_row.addStretch()
        if nav_row.count() > 1:
            outer.addLayout(nav_row)
        bottom.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        if entry.readonly:
            buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        bottom.addWidget(buttons)
        outer.addLayout(bottom)
        self._initial = {name: w.value() for name, w in self.widgets.items()
                         if not w.field.readonly}
        self._update_key()

    def _on_image_imported(self, data: bytes) -> None:
        mime = sniff_mime(data, "")
        if mime:
            self.widgets["mime"].set_value(mime)

    def _collect(self) -> TagEntry:
        e = self.entry.clone()
        for name, w in self.widgets.items():
            if not w.field.readonly:
                e.set(name, w.value())
        return e

    def _update_key(self) -> None:
        try:
            key = key_for(self._collect())
            from ..tag_table import display_key
            self.key_label.setText(f"Key: <code>{html.escape(display_key(key))}</code>")
        except (TagError, ValueError, TypeError) as e:
            self.key_label.setText(f"<span style='color:#c00'>Key: {html.escape(str(e))}</span>")

    def _navigate(self, step: int, files: bool = False) -> None:
        """Keep the current edits (if valid) and ask the caller to move on."""
        if not self.entry.readonly:
            try:
                dirty = bool(self.changes())
            except ValueError as ex:
                QMessageBox.warning(self, "Invalid value", str(ex))
                return
            if dirty:
                self._accept()
                if self.result() != QDialog.DialogCode.Accepted:
                    return  # invalid value, stay here
        if files:
            self.file_nav_step = step
        else:
            self.nav = step
        self.accept()

    def _accept(self) -> None:
        try:
            e = self._collect()
            key_for(e)  # validates (e.g. builds the ID3 frame)
        except (TagError, ValueError, TypeError) as ex:
            QMessageBox.warning(self, "Invalid value", str(ex))
            return
        self.result_entry = e
        self.accept()

    def changes(self) -> dict:
        """Field name -> new value for fields the user actually changed."""
        out = {}
        for name, w in self.widgets.items():
            if w.field.readonly:
                continue
            v = w.value()
            if v != self._initial.get(name):
                out[name] = v
        return out
