"""Full frame-level editor for one tag entry (applied to one or many files)."""

from __future__ import annotations

import html

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QMessageBox, QScrollArea, QVBoxLayout,
    QWidget,
)

from ...core.formats import key_for
from ...core.formats.base import TagError, sniff_mime
from ...core.model import TagEntry
from .fields import BytesWidget, FieldWidget, widget_for


class EntryDialog(QDialog):
    def __init__(self, entry: TagEntry, *, file_count: int = 1, differing: set[str] = frozenset(),
                 is_new: bool = False, parent=None) -> None:
        super().__init__(parent)
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

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        if entry.readonly:
            buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        outer.addWidget(buttons)
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
