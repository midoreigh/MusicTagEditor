"""Options › File Naming (modelled on Picard's page)."""

from __future__ import annotations

import html
import os

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.model import FileTags, TagEntry
from ..core.naming import PICARD_DEFAULT, PRESETS, NamingOptions, ScriptError, parse, preview
from ..core.naming.script import FUNCTIONS
from ..core.naming.variables import COMMON_VARIABLES
from .editors.fields import mono_font

MAX_EXAMPLES = 10


def load_naming(settings: QSettings) -> NamingOptions:
    def b(key, default):
        v = settings.value(key, default)
        return v in (True, "true", "1", 1) if not isinstance(v, bool) else v

    return NamingOptions(
        rename=b("naming/rename", False),
        script=str(settings.value("naming/script", PICARD_DEFAULT)),
        move=b("naming/move", False),
        dest_dir=str(settings.value("naming/dest_dir", "")),
        delete_empty_dirs=b("naming/delete_empty_dirs", True),
    )


def save_naming(settings: QSettings, opts: NamingOptions) -> None:
    settings.setValue("naming/rename", opts.rename)
    settings.setValue("naming/script", opts.script)
    settings.setValue("naming/move", opts.move)
    settings.setValue("naming/dest_dir", opts.dest_dir)
    settings.setValue("naming/delete_empty_dirs", opts.delete_empty_dirs)


class NamingDialog(QDialog):
    def __init__(self, opts: NamingOptions,
                 examples: list[tuple[FileTags, list[TagEntry]]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("File Naming")
        self.resize(900, 680)
        self.examples = examples[:MAX_EXAMPLES]

        lay = QVBoxLayout(self)

        # --- move ------------------------------------------------------------
        self.move_box = QCheckBox("Move files when saving")
        lay.addWidget(self.move_box)
        self.move_group = QGroupBox()
        mg = QVBoxLayout(self.move_group)
        row = QHBoxLayout()
        row.addWidget(QLabel("Destination directory:"))
        self.dest = QLineEdit()
        self.dest.setPlaceholderText(os.path.expanduser("~/Music"))
        browse = QPushButton("Browse…")
        row.addWidget(self.dest, 1)
        row.addWidget(browse)
        mg.addLayout(row)
        self.delete_empty = QCheckBox("Delete empty directories")
        mg.addWidget(self.delete_empty)
        lay.addWidget(self.move_group)

        # --- rename ----------------------------------------------------------
        self.rename_box = QCheckBox("Rename files when saving")
        lay.addWidget(self.rename_box)

        split = QSplitter(Qt.Orientation.Vertical)
        script_host = QWidget()
        sl = QVBoxLayout(script_host)
        sl.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addWidget(QLabel("File naming script:"))
        row.addStretch()
        self.presets = QComboBox()
        self.presets.addItem("Load preset…")
        for name in PRESETS:
            self.presets.addItem(name)
        row.addWidget(self.presets)
        sl.addLayout(row)
        self.script = QPlainTextEdit()
        self.script.setFont(mono_font())
        self.script.setPlaceholderText("%artist% - %title%")
        sl.addWidget(self.script, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        sl.addWidget(self.status)
        help_ = QLabel(
            "<small>Variables: " + ", ".join(f"<code>%{html.escape(v)}%</code>"
                                             for v in COMMON_VARIABLES)
            + "<br>Functions: " + ", ".join(f"<code>${f}</code>" for f in FUNCTIONS)
            + "<br>Use <code>/</code> to create folders; newlines in the script are ignored;"
              " the original extension is kept.</small>")
        help_.setWordWrap(True)
        help_.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        sl.addWidget(help_)
        split.addWidget(script_host)

        prev_host = QWidget()
        pl = QVBoxLayout(prev_host)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.addWidget(QLabel("Files will be named like this"
                            + ("" if self.examples else " (select files to see examples)") + ":"))
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Before", "After"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(False)
        pl.addWidget(self.table)
        split.addWidget(prev_host)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        lay.addWidget(split, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel
                                   | QDialogButtonBox.StandardButton.RestoreDefaults)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            lambda: self.script.setPlainText(PICARD_DEFAULT))
        lay.addWidget(buttons)
        self.ok = buttons.button(QDialogButtonBox.StandardButton.Ok)

        # --- state -----------------------------------------------------------
        self.move_box.setChecked(opts.move)
        self.dest.setText(opts.dest_dir)
        self.delete_empty.setChecked(opts.delete_empty_dirs)
        self.rename_box.setChecked(opts.rename)
        self.script.setPlainText(opts.script)

        self._timer = QTimer(self, singleShot=True, interval=200)
        self._timer.timeout.connect(self._refresh)
        for sig in (self.move_box.toggled, self.rename_box.toggled, self.dest.textChanged,
                    self.script.textChanged):
            sig.connect(lambda *_: self._timer.start())
        self.move_box.toggled.connect(self._enable)
        self.rename_box.toggled.connect(self._enable)
        browse.clicked.connect(self._browse)
        self.presets.activated.connect(self._load_preset)
        self._enable()
        self._refresh()

    def options(self) -> NamingOptions:
        return NamingOptions(
            rename=self.rename_box.isChecked(),
            script=self.script.toPlainText(),
            move=self.move_box.isChecked(),
            dest_dir=self.dest.text().strip(),
            delete_empty_dirs=self.delete_empty.isChecked(),
        )

    def _enable(self) -> None:
        self.move_group.setEnabled(self.move_box.isChecked())
        on = self.rename_box.isChecked()
        self.script.setEnabled(on)
        self.presets.setEnabled(on)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Destination directory",
                                                self.dest.text() or os.path.expanduser("~"))
        if path:
            self.dest.setText(path)

    def _load_preset(self, index: int) -> None:
        if index > 0:
            self.script.setPlainText(PRESETS[self.presets.itemText(index)])
        self.presets.setCurrentIndex(0)

    def _validate(self) -> str | None:
        opts = self.options()
        if opts.move and not opts.dest_dir:
            return "Choose a destination directory (or turn off moving)."
        if opts.rename:
            try:
                parse(opts.script.replace("\n", "").replace("\t", ""))
            except ScriptError as e:
                return f"Script error: {e}"
            if not opts.script.strip():
                return "The naming script is empty."
        return None

    def _refresh(self) -> None:
        err = self._validate()
        self.ok.setEnabled(err is None)
        if err:
            self.status.setText(f"<span style='color:#c0392b'>{html.escape(err)}</span>")
        else:
            self.status.setText("<span style='color:#27ae60'>Script OK</span>"
                                if self.rename_box.isChecked() else "")
        opts = self.options()
        self.table.setRowCount(len(self.examples))
        for r, (ft, entries) in enumerate(self.examples):
            before = QTableWidgetItem(os.path.basename(ft.path))
            before.setToolTip(ft.path)
            if err or not opts.active:
                after_text = os.path.basename(ft.path) if not opts.active else "—"
            else:
                after_text = preview(ft, opts, entries)
            shown = after_text
            if not after_text.startswith("⚠") and opts.active and not err:
                base = (os.path.abspath(os.path.expanduser(opts.dest_dir)) if opts.move
                        else os.path.dirname(ft.path))
                shown = os.path.relpath(after_text, base) if after_text.startswith(base) \
                    else after_text
            after = QTableWidgetItem(shown)
            after.setToolTip(after_text)
            self.table.setItem(r, 0, before)
            self.table.setItem(r, 1, after)

    def _accept(self) -> None:
        if self._validate() is None:
            self.accept()
