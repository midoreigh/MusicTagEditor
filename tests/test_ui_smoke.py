"""GUI smoke tests (run headless with QT_QPA_PLATFORM=offscreen)."""

from __future__ import annotations

import os

import pytest
from mutagen.id3 import ID3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mte.core.naming import NamingOptions  # noqa: E402
from mte.ui.main_window import MainWindow  # noqa: E402

from conftest import make_flac, make_mp3  # noqa: E402
from test_formats import seed_podcast_mp3  # noqa: E402


@pytest.fixture
def window(qtbot, tmp_path):
    for name in ("a.mp3", "b.mp3"):
        p = make_mp3(tmp_path / name)
        seed_podcast_mp3(p)
    make_flac(tmp_path / "c.flac")
    w = MainWindow()
    w.confirm_on_close = False
    w.naming = NamingOptions()  # don't depend on the user's saved settings
    qtbot.addWidget(w)
    w.show()
    w.load_paths([str(tmp_path)])
    qtbot.waitUntil(lambda: len(w.file_model.paths) == 3 and w._loader is None, timeout=5000)
    return w


def _select_files(w, names):
    paths = [p for p in w.file_view.all_paths() if os.path.basename(p) in names]
    w.file_view.select_paths(paths, current=paths[0] if paths else None)


def _row(w, system, key):
    for r in w.tag_model.rows:
        if r.system == system and r.key == key:
            return r
    return None


def test_load_select_inline_edit_and_save(window, qtbot, tmp_path):
    w = window
    _select_files(w, {"a.mp3", "b.mp3"})
    assert w.tag_model.paths and len(w.tag_model.paths) == 2
    row = _row(w, "ID3v2", "TXXX:podcastdesc")
    assert row is not None and row.uniform

    # inline-edit the title on both files
    title = _row(w, "ID3v2", "TIT2")
    w._inline_edit(title, "Batch title")
    qtbot.wait(10)
    assert all(w.session.files[p].dirty for p in w.tag_model.paths)

    # delete the junk tags through the selection + delete action
    w.tag_view.clearSelection()
    sm = w.tag_view.selectionModel()
    for i, r in enumerate(w.tag_model.rows):
        if r.key.startswith("TXXX:podcast"):
            idx = w.tag_proxy.mapFromSource(w.tag_model.index(i, 0))
            sm.select(idx, sm.SelectionFlag.Select | sm.SelectionFlag.Rows)
    w.delete_tags()
    assert _row(w, "ID3v2", "TXXX:podcastdesc") is None

    w.save()
    qtbot.waitUntil(lambda: not w.session.dirty_files(), timeout=5000)
    for name in ("a.mp3", "b.mp3"):
        tags = ID3(tmp_path / name)
        assert tags["TIT2"].text == ["Batch title"]
        assert "TXXX:podcastdesc" not in tags and "TXXX:podcastid" not in tags


def test_entry_dialog_builds_for_every_frame_type(window, qtbot):
    from mte.core.tagfile import TagFile
    from mte.ui.editors.entry_dialog import EntryDialog

    path = window.file_model.paths[0]
    for system in ("ID3v2", "ID3v1", "APEv2"):
        for t in TagFile(path).adapter(system).templates():
            dlg = EntryDialog(t, is_new=True)
            qtbot.addWidget(dlg)
            dlg.changes()


def test_screenshot(window, qtbot, tmp_path):
    _select_files(window, {"a.mp3"})
    window.resize(1200, 700)
    qtbot.wait(50)
    out = os.environ.get("MTE_SCREENSHOT")
    if out:
        window.grab().save(out)


def test_add_tag_dialog_lists_templates(window, qtbot):
    from mte.ui.add_tag import AddTagDialog

    path = window.file_model.paths[0]
    dlg = AddTagDialog({"ID3v2": path, "APEv2": path, "ID3v1": path})
    qtbot.addWidget(dlg)
    dlg.search.setText("TXXX")
    picked = dlg.selected()
    assert picked is not None and picked.frame_id == "TXXX"
    dlg.system_box.setCurrentText("APEv2")
    dlg.search.setText("")
    assert dlg.list.count() > 5


def test_find_remove_dialog_queues_deletes(window, qtbot):
    from mte.ui.find_remove import FindRemoveDialog

    paths = list(window.file_model.paths)
    dlg = FindRemoveDialog(window.session, [], paths)
    qtbot.addWidget(dlg)
    dlg.term.setText("songs.pk")
    dlg._search()
    assert dlg.tree.topLevelItemCount() == 2  # two seeded mp3s
    dlg._remove()
    assert dlg.removed == 6  # TXXX x2 + WFED per file
    assert len(window.session.dirty_files()) == 2


def test_naming_dialog_preview_and_rename_on_save(window, qtbot, tmp_path):
    from mte.ui.naming_dialog import NamingDialog

    w = window
    _select_files(w, {"a.mp3"})
    st = w.session.files[w.tag_model.paths[0]]
    dlg = NamingDialog(NamingOptions(), [(st.original, st.working)])
    qtbot.addWidget(dlg)
    dlg.rename_box.setChecked(True)
    dlg.script.setPlainText("%artist% - $if2(%album%,none) - %title%")
    dlg._refresh()
    assert dlg.ok.isEnabled()
    assert dlg.table.item(0, 1).text() == "- none - Song.mp3"  # leading space trimmed
    dlg.script.setPlainText("$if(%title%")
    dlg._refresh()
    assert not dlg.ok.isEnabled() and "Script error" in dlg.status.text()

    # rename on save through the window
    w.naming = NamingOptions(rename=True, script="renamed - %title%")
    title = _row(w, "ID3v2", "TIT2")
    w._inline_edit(title, "Fresh")
    qtbot.wait(10)
    w.save()
    qtbot.waitUntil(lambda: not w.session.dirty_files(), timeout=5000)
    new = str(tmp_path / "renamed - Fresh.mp3")
    assert os.path.exists(new) and not (tmp_path / "a.mp3").exists()
    assert new in w.session.files and new in w.file_model.paths


def test_entry_dialog_prev_next_buttons(qtbot, monkeypatch):
    from mte.core.formats.id3 import blank_frame_entry
    from mte.ui.editors.entry_dialog import EntryDialog

    e = blank_frame_entry("TIT2")
    first = EntryDialog(e, position=(0, 3))
    qtbot.addWidget(first)
    assert not first.prev_btn.isEnabled() and first.next_btn.isEnabled()
    last = EntryDialog(e, position=(2, 3))
    qtbot.addWidget(last)
    assert last.prev_btn.isEnabled() and not last.next_btn.isEnabled()
    plain = EntryDialog(e)
    qtbot.addWidget(plain)
    assert not hasattr(plain, "prev_btn")

    # Next with an invalid edit stays on the dialog
    bad = EntryDialog(blank_frame_entry("PCNT"), position=(1, 3))
    qtbot.addWidget(bad)
    import mte.ui.editors.entry_dialog as ed
    monkeypatch.setattr(ed.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    bad.widgets["count"].edit.setText("not a number")
    bad._navigate(1)
    assert bad.nav == 0 and bad.result() != bad.DialogCode.Accepted


def test_edit_row_walks_previous_next(window, qtbot, monkeypatch):
    import mte.ui.main_window as mw

    w = window
    _select_files(w, {"a.mp3"})
    order = [w.tag_view.source_row(w.tag_proxy.index(r, 0)).key
             for r in range(w.tag_proxy.rowCount())]
    seen = []
    script = iter([("edit", 1), ("noop", 1), ("noop", -1), ("cancel", 0)])

    class Scripted(mw.EntryDialog):
        def exec(self):
            seen.append(self.entry.key)
            action, step = next(script)
            if action == "cancel":
                return 0
            if action == "edit":
                self.widgets["text"].set_value(["Edited via dialog"])
            self._navigate(step)
            return int(self.result())

    monkeypatch.setattr(mw, "EntryDialog", Scripted)
    w.edit_row(w.tag_view.source_row(w.tag_proxy.index(0, 0)))
    assert seen == [order[0], order[1], order[2], order[1]]
    assert _row(w, "ID3v2", order[0]).first.get("text") == ["Edited via dialog"]
    assert w.tag_view.current_row().key == order[1]  # table follows the dialog


def test_edit_row_previous_next_file_keeps_tag(qtbot, tmp_path, monkeypatch):
    import mte.ui.main_window as mw

    seed_podcast_mp3(make_mp3(tmp_path / "1.mp3"))
    make_mp3(tmp_path / "2.mp3")                 # no tags at all
    make_flac(tmp_path / "3.flac")               # can't hold ID3v2: skipped
    seed_podcast_mp3(make_mp3(tmp_path / "4.mp3"))
    w = MainWindow()
    w.confirm_on_close = False
    w.naming = NamingOptions()
    qtbot.addWidget(w)
    w.show()
    w.load_paths([str(tmp_path)])
    qtbot.waitUntil(lambda: len(w.file_model.paths) == 4 and w._loader is None, timeout=5000)
    _select_files(w, {"1.mp3"})

    seen = []

    def step(dlg):
        name = os.path.basename(next(iter(w.tag_model.paths)))
        seen.append((name, dlg.entry.key, dlg.missing))
        if len(seen) == 1:
            dlg.widgets["text"].set_value(["One"])
            return "next"
        if len(seen) == 2:
            assert dlg.missing and dlg.widgets["text"].value() == []
            return "next"                         # unchanged: nothing is added
        if len(seen) == 3:
            assert dlg.prev_file_btn.isEnabled() and not dlg.next_file_btn.isEnabled()
            return "prev"
        if len(seen) == 4:
            assert dlg.missing                    # still missing, wasn't added
            dlg.widgets["text"].set_value(["Two"])
            return "prev"
        assert dlg.widgets["text"].value() == ["One"]
        return "cancel"

    class Scripted(mw.EntryDialog):
        def exec(self):
            action = step(self)
            if action == "cancel":
                return 0
            self._navigate(1 if action == "next" else -1, files=True)
            return int(self.result())

    monkeypatch.setattr(mw, "EntryDialog", Scripted)
    w.edit_row(_row(w, "ID3v2", "TIT2"))
    assert seen == [("1.mp3", "TIT2", False), ("2.mp3", "TIT2", True), ("4.mp3", "TIT2", False),
                    ("2.mp3", "TIT2", True), ("1.mp3", "TIT2", False)]
    files = {os.path.basename(p): st for p, st in w.session.files.items()}
    assert files["1.mp3"].find("ID3v2", "TIT2").get("text") == ["One"]
    assert files["2.mp3"].find("ID3v2", "TIT2").get("text") == ["Two"]
    assert files["4.mp3"].find("ID3v2", "TIT2").get("text") == ["Song"]  # only visited
    assert not files["4.mp3"].dirty


def test_rename_folder_keeps_pending_edits(qtbot, tmp_path, monkeypatch):
    import mte.ui.main_window as mw

    album = tmp_path / "lib" / "Old Album"
    album.mkdir(parents=True)
    seed_podcast_mp3(make_mp3(album / "1.mp3"))
    seed_podcast_mp3(make_mp3(tmp_path / "lib" / "outside.mp3"))
    w = MainWindow()
    w.confirm_on_close = False
    w.naming = NamingOptions()
    qtbot.addWidget(w)
    w.show()
    w.load_paths([str(tmp_path / "lib")])
    qtbot.waitUntil(lambda: len(w.file_model.paths) == 2 and w._loader is None, timeout=5000)
    _select_files(w, {"1.mp3"})
    w._inline_edit(_row(w, "ID3v2", "TIT2"), "Pending title")
    qtbot.wait(10)

    class Scripted(mw.RenameFolderDialog):
        def exec(self):
            assert self.selected_folder() == str(album)
            assert self.folder.count() == 2  # album folder + common "lib" root
            self.name.setText("New Album")
            assert self.ok.isEnabled()
            return 1

    monkeypatch.setattr(mw, "RenameFolderDialog", Scripted)
    w.rename_folder()
    new_path = str(tmp_path / "lib" / "New Album" / "1.mp3")
    assert os.path.exists(new_path) and not album.exists()
    assert new_path in w.file_model.paths and new_path in w.session.files
    st = w.session.files[new_path]
    assert st.dirty and st.find("ID3v2", "TIT2").get("text") == ["Pending title"]
    assert str(tmp_path / "lib" / "outside.mp3") in w.session.files  # untouched

    w.save()
    qtbot.waitUntil(lambda: not w.session.dirty_files(), timeout=5000)
    from mutagen.id3 import ID3
    assert ID3(new_path)["TIT2"].text == ["Pending title"]
