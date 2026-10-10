"""Main window: file list | tag table + detail pane."""

from __future__ import annotations

import html
import os

from PySide6.QtCore import QSettings, Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar,
    QProgressDialog, QSplitter, QStyle, QTextBrowser, QToolBar, QVBoxLayout, QWidget,
)

from .. import __version__
from ..core.formats.base import TagError
from ..core.model import Field, FieldType, SetEntry, format_value
from ..core.scanner import DEFAULT_EXTENSIONS
from ..core.session import MergedRow, Session
from .add_tag import AddTagDialog
from .editors.entry_dialog import EntryDialog
from .editors.fields import image_pixmap
from .file_list import FileFilterProxy, FileListModel, FileListView
from .find_remove import FindRemoveDialog
from .tag_table import TagFilterProxy, TagTableModel, TagTableView, content_field, display_key
from .workers import LoadWorker, SaveWorker


def parse_inline(ftype: FieldType, text: str):
    text = text.strip() if ftype != FieldType.TEXT else text
    if ftype in (FieldType.TEXT, FieldType.LANG):
        return text
    if ftype == FieldType.INT:
        return int(text or "0", 0)
    if ftype == FieldType.TEXT_LIST:
        return [text] if text else []
    parts = [p.strip() for p in text.split(";") if p.strip()]
    if ftype == FieldType.INT_LIST:
        return [int(p, 0) for p in parts]
    if ftype == FieldType.PAIR_LIST:
        out = []
        for p in parts:
            a, _, b = p.partition("/")
            out.append((int(a or 0), int(b or 0)))
        return out
    raise ValueError(f"can't edit {ftype} inline")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Music Tag Editor")
        self.resize(1280, 780)
        self.setAcceptDrops(True)
        self.session = Session()
        self.pool = QThreadPool.globalInstance()
        self.settings = QSettings("Music Tag Editor", "Music Tag Editor")
        self._loader: LoadWorker | None = None
        self.confirm_on_close = True  # tests turn this off

        # --- file list -------------------------------------------------------
        self.file_model = FileListModel(self.session, self)
        self.file_proxy = FileFilterProxy(self)
        self.file_proxy.setSourceModel(self.file_model)
        self.file_view = FileListView()
        self.file_view.setModel(self.file_proxy)
        self.file_filter = QLineEdit()
        self.file_filter.setPlaceholderText("Filter files…")
        self.file_filter.setClearButtonEnabled(True)
        self.file_filter.textChanged.connect(self.file_proxy.setFilterFixedString)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(4, 4, 0, 4)
        ll.addWidget(self.file_filter)
        ll.addWidget(self.file_view)

        # --- tag table -------------------------------------------------------
        self.tag_model = TagTableModel(self.session, self)
        self.tag_proxy = TagFilterProxy(self)
        self.tag_proxy.setSourceModel(self.tag_model)
        self.tag_view = TagTableView()
        self.tag_view.setModel(self.tag_proxy)
        self.tag_filter = QLineEdit()
        self.tag_filter.setPlaceholderText("Filter tags… (key, value, system)")
        self.tag_filter.setClearButtonEnabled(True)
        self.tag_filter.textChanged.connect(self.tag_proxy.setFilterFixedString)
        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        self.info_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail = QTextBrowser()
        self.detail.setOpenLinks(False)

        tags_box = QWidget()
        tl = QVBoxLayout(tags_box)
        tl.setContentsMargins(0, 4, 4, 0)
        tl.addWidget(self.info_label)
        tl.addWidget(self.tag_filter)
        tl.addWidget(self.tag_view)
        right = QSplitter(Qt.Orientation.Vertical)
        right.addWidget(tags_box)
        right.addWidget(self.detail)
        right.setStretchFactor(0, 4)
        right.setStretchFactor(1, 1)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 5)
        split.setSizes([420, 860])
        self.setCentralWidget(split)
        self.splitter = split

        self.progress = QProgressBar()
        self.progress.setMaximumWidth(200)
        self.progress.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress)

        self._build_actions()
        self.file_view.selectionModel().selectionChanged.connect(self._files_selected)
        self.tag_view.selectionModel().selectionChanged.connect(self._tags_selected)
        self.tag_view.activated_row.connect(self.edit_row)
        self.tag_view.delete_pressed.connect(self.delete_tags)
        self.tag_model.inline_edited.connect(self._inline_edit)
        self.tag_model.modelReset.connect(self._tags_selected)
        self._update_actions()
        self._restore_state()

    # ------------------------------------------------------------------ setup
    def _build_actions(self) -> None:
        st = self.style()
        sp = QStyle.StandardPixmap

        def act(text, slot, shortcut=None, icon=None, tip=None):
            a = QAction(text, self)
            if shortcut:
                a.setShortcut(shortcut)
            if icon is not None:
                a.setIcon(st.standardIcon(icon))
            a.setToolTip(tip or text)
            a.triggered.connect(slot)
            return a

        self.a_open = act("Open Folder…", self.open_folder, QKeySequence.StandardKey.Open,
                          sp.SP_DirOpenIcon)
        self.a_add_files = act("Add Files…", self.add_files, "Ctrl+Shift+O", sp.SP_FileIcon)
        self.a_save = act("Save", self.save, QKeySequence.StandardKey.Save,
                          sp.SP_DialogSaveButton, "Write pending changes of all modified files")
        self.a_revert = act("Revert", self.revert, "Ctrl+R", sp.SP_DialogResetButton,
                            "Discard pending changes of the selected files")
        self.a_remove = act("Remove from List", self.remove_files, None, sp.SP_DialogCloseButton)
        self.a_clear = act("Clear List", self.clear_files)
        self.a_reload = act("Reload from Disk", self.reload_files, "F5", sp.SP_BrowserReload)
        self.a_quit = act("Quit", self.close, QKeySequence.StandardKey.Quit)
        self.a_add_tag = act("Add Tag…", self.add_tag, "Ctrl+T", sp.SP_FileDialogNewFolder)
        self.a_edit_tag = act("Edit Tag…", lambda: self.edit_row(self.tag_view.current_row()),
                              "Ctrl+E", sp.SP_FileDialogDetailedView)
        self.a_del_tag = act("Delete Tags", self.delete_tags, None, sp.SP_TrashIcon,
                             "Delete the selected tags (Del)")
        self.a_find = act("Find && Remove…", self.find_remove, "Ctrl+Shift+F",
                          sp.SP_FileDialogContentsView,
                          "Remove tags whose key/value contains some text")
        self.a_select_all = act("Select All Files", self.file_view.selectAll, "Ctrl+Shift+A")
        self.a_about = act("About Music Tag Editor", self.about)

        m = self.menuBar().addMenu("&File")
        for a in (self.a_open, self.a_add_files, None, self.a_save, self.a_revert, self.a_reload,
                  None, self.a_remove, self.a_clear, None, self.a_quit):
            m.addSeparator() if a is None else m.addAction(a)
        m = self.menuBar().addMenu("&Edit")
        for a in (self.a_add_tag, self.a_edit_tag, self.a_del_tag, None, self.a_find, None,
                  self.a_select_all):
            m.addSeparator() if a is None else m.addAction(a)
        self.menuBar().addMenu("&Help").addAction(self.a_about)

        tb = QToolBar("Main")
        tb.setObjectName("main_toolbar")
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        tb.setMovable(False)
        for a in (self.a_open, self.a_add_files, None, self.a_save, self.a_revert, None,
                  self.a_add_tag, self.a_edit_tag, self.a_del_tag, None, self.a_find):
            tb.addSeparator() if a is None else tb.addAction(a)
        self.addToolBar(tb)

    def _restore_state(self) -> None:
        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        sp = self.settings.value("splitter")
        if sp is not None:
            self.splitter.restoreState(sp)

    # ------------------------------------------------------------- selection
    def selected_paths(self) -> list[str]:
        return self.file_view.selected_paths()

    def _files_selected(self, *_):
        paths = [p for p in self.selected_paths() if p in self.session]
        self.tag_model.set_paths(paths)
        self._update_info(paths)
        self._update_actions()

    def _update_info(self, paths: list[str]) -> None:
        if not paths:
            self.info_label.setText("<i>Select one or more files.</i>")
            return
        if len(paths) == 1:
            st = self.session.files[paths[0]]
            if st.original.error:
                self.info_label.setText(f"<b>{html.escape(os.path.basename(paths[0]))}</b> — "
                                        f"<span style='color:#c0392b'>{html.escape(st.original.error)}</span>")
                return
            info = st.original.info
            parts = [info.get("format", "")]
            if "length" in info:
                m, s = divmod(int(info["length"]), 60)
                parts.append(f"{m}:{s:02d}")
            if info.get("bitrate"):
                parts.append(f"{info['bitrate'] // 1000} kbps")
            if info.get("sample_rate"):
                parts.append(f"{info['sample_rate']} Hz")
            if info.get("channels"):
                parts.append(f"{info['channels']} ch")
            if info.get("id3"):
                parts.append(info["id3"])
            self.info_label.setText(
                f"<b>{html.escape(os.path.basename(paths[0]))}</b> — "
                + html.escape(" · ".join(str(p) for p in parts if p))
                + f" — tag systems: {', '.join(st.original.systems)}")
        else:
            self.info_label.setText(f"<b>{len(paths)} files selected</b> — tags present in only "
                                    "some files show [in n/m files]; edits apply to all selected.")

    def _tags_selected(self, *_):
        rows = self.tag_view.selected_rows() if self.tag_view.selectionModel() else []
        self._update_actions()
        if len(rows) != 1:
            self.detail.setHtml("" if not rows else f"<i>{len(rows)} tags selected</i>")
            return
        self._show_detail(rows[0])

    def _show_detail(self, row: MergedRow) -> None:
        e = row.first
        out = [f"<h3 style='margin:0'>{html.escape(e.system)} · <code>{html.escape(display_key(e.key))}</code></h3>"]
        if e.description:
            out.append(f"<p style='margin:2px 0'>{html.escape(e.description)}</p>")
        if not row.uniform:
            out.append(f"<p><i>Values differ between the {len(row.entries)} files; "
                       "showing the first.</i></p>")
        out.append("<table cellspacing=0 cellpadding=3>")
        image_html = ""
        for f in e.fields:
            val = self._field_html(f)
            if f.ftype in (FieldType.BYTES, FieldType.PICTURES):
                image_html += self._image_html(f)
            out.append(f"<tr><td valign=top><b>{html.escape(f.title)}</b></td>"
                       f"<td>{val}</td></tr>")
        out.append("</table>")
        self.detail.setHtml("".join(out) + image_html)

    @staticmethod
    def _field_html(f: Field) -> str:
        if f.ftype == FieldType.TEXT_LIST:
            return "<br>".join(f"{i + 1}. " + html.escape(v).replace("\n", "<br>")
                               for i, v in enumerate(f.value)) or "<i>(no values)</i>"
        if f.ftype == FieldType.MULTILINE:
            return html.escape(f.value or "").replace("\n", "<br>")
        return html.escape(format_value(f))

    def _image_html(self, f: Field) -> str:
        import base64
        datas = [f.value] if f.ftype == FieldType.BYTES else [p.data for p in f.value]
        out = ""
        for data in datas:
            if image_pixmap(data, 64) is not None and len(data) < 8_000_000:
                b64 = base64.b64encode(data).decode()
                out += f"<img src='data:image;base64,{b64}' height=160> "
        return out

    def _update_actions(self) -> None:
        has_files = bool(self.selected_paths())
        rows = self.tag_view.selected_rows() if self.tag_view.selectionModel() else []
        self.a_add_tag.setEnabled(has_files)
        self.a_edit_tag.setEnabled(len(rows) == 1)
        self.a_del_tag.setEnabled(bool(rows))
        self.a_revert.setEnabled(any(self.session.files[p].dirty for p in self.selected_paths()
                                     if p in self.session))
        dirty = len(self.session.dirty_files())
        self.a_save.setEnabled(dirty > 0)
        self.a_find.setEnabled(bool(self.file_model.paths))
        self.setWindowModified(dirty > 0)
        self.setWindowTitle(f"Music Tag Editor{' — ' + str(dirty) + ' unsaved file(s)' if dirty else ''}")

    def _after_edit(self, paths=None) -> None:
        sel = self.tag_view.selected_rows()
        keep = {(r.system, r.key) for r in sel}
        self.tag_model.refresh()
        self.file_model.refresh(paths)
        # restore tag selection
        sm = self.tag_view.selectionModel()
        for i, row in enumerate(self.tag_model.rows):
            if (row.system, row.key) in keep:
                idx = self.tag_proxy.mapFromSource(self.tag_model.index(i, 0))
                sm.select(idx, sm.SelectionFlag.Select | sm.SelectionFlag.Rows)
        self._update_actions()

    # --------------------------------------------------------------- loading
    def open_folder(self) -> None:
        start = self.settings.value("last_dir", os.path.expanduser("~"))
        path = QFileDialog.getExistingDirectory(self, "Open music folder", start)
        if path:
            self.settings.setValue("last_dir", path)
            self.load_paths([path])

    def add_files(self) -> None:
        start = self.settings.value("last_dir", os.path.expanduser("~"))
        exts = " ".join(f"*.{e}" for e in sorted(DEFAULT_EXTENSIONS))
        paths, _ = QFileDialog.getOpenFileNames(self, "Add audio files", start,
                                                f"Audio files ({exts});;All files (*)")
        if paths:
            self.settings.setValue("last_dir", os.path.dirname(paths[0]))
            self.load_paths(paths)

    def load_paths(self, paths: list[str]) -> None:
        worker = LoadWorker(paths, skip=set(self.session.files))
        worker.signals.loaded.connect(self._on_loaded)
        worker.signals.progress.connect(self._on_load_progress)
        worker.signals.finished.connect(self._on_load_finished)
        self._loader = worker
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.statusBar().showMessage("Scanning…")
        self.pool.start(worker)

    def _on_loaded(self, chunk) -> None:
        first = not self.file_model.paths
        for ft in chunk:
            self.session.add(ft)
        self.file_model.add_paths([ft.path for ft in chunk])
        if first and self.file_model.paths:
            self.file_view.selectRow(0)
        self._update_actions()

    def _on_load_progress(self, done: int, total: int) -> None:
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done)
        self.statusBar().showMessage(f"Loading {done}/{total}…")

    def _on_load_finished(self) -> None:
        self.progress.setVisible(False)
        n = len(self.file_model.paths)
        errors = sum(1 for s in self.session.files.values() if s.original.error)
        self.statusBar().showMessage(f"{n} file(s) loaded" + (f", {errors} with errors" if errors
                                                               else ""), 8000)
        self._loader = None
        self._update_actions()

    def remove_files(self) -> None:
        paths = self.selected_paths()
        if not self._confirm_discard([p for p in paths if self.session.files[p].dirty]):
            return
        self.session.remove(paths)
        self.file_model.remove_paths(paths)
        self._files_selected()

    def clear_files(self) -> None:
        if not self._confirm_discard([s.path for s in self.session.dirty_files()]):
            return
        self.session.clear()
        self.file_model.clear()
        self._files_selected()

    def reload_files(self) -> None:
        paths = self.selected_paths() or list(self.file_model.paths)
        if not self._confirm_discard([p for p in paths if self.session.files[p].dirty]):
            return
        from ..core.tagfile import load
        for p in paths:
            self.session.replace_original(load(p))
        self.file_model.refresh()
        self._files_selected()

    def _confirm_discard(self, dirty: list[str]) -> bool:
        if not dirty:
            return True
        r = QMessageBox.question(self, "Discard changes?",
                                 f"{len(dirty)} file(s) have unsaved changes. Discard them?",
                                 QMessageBox.StandardButton.Discard
                                 | QMessageBox.StandardButton.Cancel)
        return r == QMessageBox.StandardButton.Discard

    # --------------------------------------------------------------- editing
    def _report_skipped(self, errors: dict[str, str]) -> None:
        if errors:
            names = "\n".join(f"• {os.path.basename(p)}: {m}" for p, m in list(errors.items())[:15])
            QMessageBox.information(self, "Some files skipped",
                                    f"{len(errors)} file(s) were not changed:\n\n{names}")

    def edit_row(self, row: MergedRow | None) -> None:
        if row is None:
            return
        first = row.first
        differing = set()
        for f in first.fields:
            for e in row.entries.values():
                other = e.field(f.name)
                if other is None or other.value != f.value:
                    differing.add(f.name)
                    break
        dlg = EntryDialog(first, file_count=len(row.entries), differing=differing, parent=self)
        if not dlg.exec():
            return
        changes = dlg.changes()
        if not changes:
            return
        errors = {}
        for path, entry in row.entries.items():
            new = entry.clone()
            for name, value in changes.items():
                new.set(name, value)
            try:
                self.session.files[path].apply(SetEntry(new, row.key))
            except (TagError, ValueError, TypeError) as e:
                errors[path] = str(e)
        self._report_skipped(errors)
        self._after_edit(list(row.entries))

    def _inline_edit(self, row: MergedRow, text: str) -> None:
        errors = {}
        for path, entry in row.entries.items():
            f = content_field(entry)
            if f is None:
                continue
            new = entry.clone()
            try:
                value = parse_inline(f.ftype, text)
                if value == f.value:
                    continue
                new.set(f.name, value)
                self.session.files[path].apply(SetEntry(new, row.key))
            except (TagError, ValueError, TypeError) as e:
                errors[path] = str(e)
        self._report_skipped(errors)
        # defer: we're inside the view's commit
        QTimer.singleShot(0, lambda: self._after_edit(list(row.entries)))

    def add_tag(self) -> None:
        paths = [p for p in self.selected_paths() if not self.session.files[p].original.error]
        if not paths:
            return
        systems: dict[str, str] = {}
        for p in paths:
            for s in self.session.files[p].original.systems:
                systems.setdefault(s, p)
        if not systems:
            return
        pick = AddTagDialog(systems, self)
        if not pick.exec() or (entry := pick.selected()) is None:
            return
        capable = [p for p in paths if entry.system in self.session.files[p].original.systems]
        dlg = EntryDialog(entry, file_count=len(capable), is_new=True, parent=self)
        if not dlg.exec():
            return
        new = dlg.result_entry
        errors = self.session.set_entry(capable, new, None, only_existing=False)
        skipped = {p: f"can't hold {entry.system} tags" for p in paths if p not in capable}
        self._report_skipped({**skipped, **errors})
        self._after_edit(paths)

    def delete_tags(self) -> None:
        rows = [r for r in self.tag_view.selected_rows()]
        if not rows:
            return
        for r in rows:
            self.session.delete(list(r.entries), r.system, r.key)
        self.tag_view.clearSelection()
        self._after_edit(self.tag_model.paths)
        self.statusBar().showMessage(f"{len(rows)} tag(s) marked for deletion — Save to write",
                                     5000)

    def find_remove(self) -> None:
        dlg = FindRemoveDialog(self.session, self.selected_paths(), list(self.file_model.paths),
                               self)
        if dlg.exec() and dlg.removed:
            self._after_edit()
            self.statusBar().showMessage(f"{dlg.removed} tag(s) marked for removal — Save to write",
                                         8000)

    def revert(self) -> None:
        paths = [p for p in self.selected_paths() if self.session.files[p].dirty]
        self.session.revert(paths)
        self._after_edit(paths)

    # ---------------------------------------------------------------- saving
    def save(self) -> None:
        plan = self.session.save_plan()
        if not plan:
            return
        self._save_dialog = QProgressDialog("Saving…", None, 0, len(plan), self)
        self._save_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._save_dialog.setMinimumDuration(300)
        worker = SaveWorker(plan)
        worker.signals.progress.connect(self._on_save_progress)
        worker.signals.finished.connect(self._on_saved)
        self.a_save.setEnabled(False)
        self.pool.start(worker)

    def _on_save_progress(self, done: int, total: int, path: str) -> None:
        self._save_dialog.setMaximum(total)
        self._save_dialog.setValue(done)
        if path:
            self._save_dialog.setLabelText(f"Saving {os.path.basename(path)}…")

    def _on_saved(self, result) -> None:
        self._save_dialog.close()
        for path, ft in result.saved.items():
            self.session.replace_original(ft)
        self.file_model.refresh()
        self._files_selected()
        msg = f"Saved {len(result.saved)} file(s)"
        if result.errors:
            details_ = "\n".join(f"• {p}: {e}" for p, e in result.errors.items())
            QMessageBox.warning(self, "Some files could not be saved",
                                f"{msg}; {len(result.errors)} failed (their changes are kept "
                                f"pending):\n\n{details_}")
        self.statusBar().showMessage(msg, 8000)

    # ------------------------------------------------------------------ misc
    def about(self) -> None:
        QMessageBox.about(self, "About Music Tag Editor",
                          f"<b>Music Tag Editor {__version__}</b><p>View and edit every raw tag in audio "
                          "files: ID3v2/ID3v1, MP4 atoms, Vorbis comments, FLAC pictures, "
                          "APEv2 and ASF.</p><p>Built with PySide6 and mutagen.</p>")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.load_paths(paths)

    def closeEvent(self, event):
        dirty = self.session.dirty_files()
        if dirty and self.confirm_on_close:
            r = QMessageBox.question(
                self, "Unsaved changes", f"{len(dirty)} file(s) have unsaved changes.",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel)
            if r == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if r == QMessageBox.StandardButton.Save:
                from ..core.batch import save_all
                result = save_all(self.session.save_plan())
                if result.errors:
                    QMessageBox.warning(self, "Save failed",
                                        "\n".join(f"{p}: {e}" for p, e in result.errors.items()))
                    event.ignore()
                    return
        if self._loader is not None:
            self._loader.cancelled = True
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("splitter", self.splitter.saveState())
        event.accept()
