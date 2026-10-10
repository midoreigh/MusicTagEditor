"""GUI version of clean_audio_tags.py: find tags containing a term, remove them."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QRadioButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from ..core.cleaner import matching_entries
from ..core.model import FileTags
from ..core.session import Session


class FindRemoveDialog(QDialog):
    def __init__(self, session: Session, selected: list[str], all_paths: list[str],
                 parent=None) -> None:
        super().__init__(parent)
        self.session = session
        self.selected = selected
        self.all_paths = all_paths
        self.setWindowTitle("Find & remove tags")
        self.resize(760, 560)

        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self.term = QLineEdit()
        self.term.setPlaceholderText("Text to look for in tag keys or values, e.g. songs.pk")
        self.term.setClearButtonEnabled(True)
        self.search_btn = QPushButton("Search")
        self.search_btn.setDefault(True)
        row.addWidget(self.term, 1)
        row.addWidget(self.search_btn)
        lay.addLayout(row)

        opts = QHBoxLayout()
        self.keys_only = QCheckBox("Match keys only")
        self.scope_sel = QRadioButton(f"Selected files ({len(selected)})")
        self.scope_all = QRadioButton(f"All loaded files ({len(all_paths)})")
        (self.scope_sel if selected else self.scope_all).setChecked(True)
        self.scope_sel.setEnabled(bool(selected))
        for w in (self.keys_only, self.scope_sel, self.scope_all):
            opts.addWidget(w)
        opts.addStretch()
        lay.addLayout(opts)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["File / tag", "Value"])
        self.tree.setColumnWidth(0, 360)
        lay.addWidget(self.tree, 1)
        self.summary = QLabel("Matched tags are only queued for removal; use Save to write.")
        lay.addWidget(self.summary)

        buttons = QDialogButtonBox()
        self.remove_btn = buttons.addButton("Remove checked", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Close)
        self.remove_btn.setEnabled(False)
        buttons.accepted.connect(self._remove)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        self.search_btn.clicked.connect(self._search)
        self.term.returnPressed.connect(self._search)
        self.removed = 0

    def _scope(self) -> list[str]:
        return self.selected if self.scope_sel.isChecked() else self.all_paths

    def _search(self) -> None:
        self.tree.clear()
        term = self.term.text().strip()
        files = hits = 0
        for path in self._scope():
            st = self.session.files.get(path)
            if st is None or st.original.error:
                continue
            view = FileTags(path, st.original.format_name, st.original.systems, st.working)
            found = matching_entries(view, term, self.keys_only.isChecked())
            if not found:
                continue
            files += 1
            parent = QTreeWidgetItem([os.path.basename(path), os.path.dirname(path)])
            parent.setFlags(parent.flags() | Qt.ItemFlag.ItemIsAutoTristate
                            | Qt.ItemFlag.ItemIsUserCheckable)
            parent.setCheckState(0, Qt.CheckState.Checked)
            parent.setData(0, Qt.ItemDataRole.UserRole, path)
            for e in found:
                child = QTreeWidgetItem([f"[{e.system}] {e.key}", e.summary()[:200]])
                child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                child.setCheckState(0, Qt.CheckState.Checked)
                child.setData(0, Qt.ItemDataRole.UserRole, (e.system, e.key))
                parent.addChild(child)
                hits += 1
            self.tree.addTopLevelItem(parent)
            parent.setExpanded(True)
        self.summary.setText(f"{hits} matching tag(s) in {files} file(s)." if term
                             else "Enter a search term.")
        self.remove_btn.setEnabled(hits > 0)

    def _remove(self) -> None:
        n = 0
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            path = parent.data(0, Qt.ItemDataRole.UserRole)
            for j in range(parent.childCount()):
                child = parent.child(j)
                if child.checkState(0) == Qt.CheckState.Checked:
                    system, key = child.data(0, Qt.ItemDataRole.UserRole)
                    self.session.delete([path], system, key)
                    n += 1
        self.removed = n
        self.accept()
