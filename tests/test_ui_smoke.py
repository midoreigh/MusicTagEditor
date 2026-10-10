"""GUI smoke tests (run headless with QT_QPA_PLATFORM=offscreen)."""

from __future__ import annotations

import os

import pytest
from mutagen.id3 import ID3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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
    qtbot.addWidget(w)
    w.show()
    w.load_paths([str(tmp_path)])
    qtbot.waitUntil(lambda: len(w.file_model.paths) == 3 and w._loader is None, timeout=5000)
    return w


def _select_files(w, names):
    w.file_view.clearSelection()
    sm = w.file_view.selectionModel()
    for r in range(w.file_proxy.rowCount()):
        idx = w.file_proxy.index(r, 0)
        if os.path.basename(idx.data(0x0100)) in names:
            sm.select(idx, sm.SelectionFlag.Select | sm.SelectionFlag.Rows)


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
