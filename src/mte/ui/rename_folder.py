"""File › Rename Folder… dialog."""

from __future__ import annotations

import html
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout,
)

from ..core.folders import validate_folder_name


class RenameFolderDialog(QDialog):
    def __init__(self, folders: list[str], loaded_paths: list[str], dirty_paths: set[str],
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Rename Folder")
        self.setMinimumWidth(620)
        self.loaded = loaded_paths
        self.dirty = dirty_paths

        lay = QVBoxLayout(self)
        form = QFormLayout()
        # macOS defaults to FieldsStayAtSizeHint, which leaves the name field narrow
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.folder = QComboBox()
        self.folder.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.folder.setMinimumContentsLength(40)
        base = os.path.dirname(folders[-1]) if folders else ""
        for i, f in enumerate(folders):
            shown = os.path.relpath(f, base) if base else f
            label = "Its folder" if i == 0 else "Parent" if i == 1 else f"Parent ×{i}"
            self.folder.addItem(f"{shown}   ({label})", f)
            self.folder.setItemData(i, f, Qt.ItemDataRole.ToolTipRole)
        form.addRow("Folder:", self.folder)
        self.name = QLineEdit()
        form.addRow("New name:", self.name)
        lay.addLayout(form)
        self.info = QLabel()
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        self.ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok.setText("Rename")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        # wide enough to show long folder names without scrolling (within reason)
        longest = max((self.name.fontMetrics().horizontalAdvance(os.path.basename(f))
                       for f in folders), default=0)
        self.setMinimumWidth(min(max(620, longest + 160), 1000))

        self.folder.currentIndexChanged.connect(self._folder_changed)
        self.name.textChanged.connect(self._validate)
        self._folder_changed()

    def selected_folder(self) -> str:
        return self.folder.currentData()

    def new_name(self) -> str:
        return self.name.text()

    def _folder_changed(self, *_) -> None:
        self.name.setText(os.path.basename(self.selected_folder()))
        self.name.selectAll()
        self.name.setFocus()
        self._validate()

    def _validate(self, *_) -> None:
        folder = self.selected_folder()
        name = self.new_name()
        inside = [p for p in self.loaded if p.startswith(folder + os.sep)]
        dirty = [p for p in inside if p in self.dirty]
        err = validate_folder_name(name)
        if err is None and name != os.path.basename(folder):
            target = os.path.join(os.path.dirname(folder), name)
            if os.path.exists(target) and target.lower() != folder.lower():
                err = f"A folder named “{name}” already exists there."
        unchanged = name == os.path.basename(folder)
        self.ok.setEnabled(err is None and not unchanged)
        lines = [f"Renames the folder on disk now (not on Save). "
                 f"{len(inside)} loaded file(s) are inside it."]
        if dirty:
            lines.append(f"{len(dirty)} of them {'has' if len(dirty) == 1 else 'have'} unsaved "
                         "tag edits; those are kept.")
        if err:
            lines.append(f"<span style='color:#c0392b'>{html.escape(err)}</span>")
        self.info.setText("<br>".join(lines))
        self.adjustSize()  # grow/shrink with the (wrapping) info text
