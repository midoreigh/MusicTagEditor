"""Left-pane folder tree."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QModelIndex, Qt  # noqa: E402

from mte.core.naming import NamingOptions  # noqa: E402
from mte.ui.file_tree import IS_DIR_ROLE  # noqa: E402
from mte.ui.main_window import MainWindow  # noqa: E402

from conftest import make_flac, make_mp3  # noqa: E402
from test_formats import seed_podcast_mp3  # noqa: E402


def _tree(view, parent=QModelIndex(), depth=0):
    """Displayed tree as indented names (folders end with '/')."""
    m = view.model()
    out = []
    for r in range(m.rowCount(parent)):
        idx = m.index(r, 0, parent)
        is_dir = idx.data(IS_DIR_ROLE)
        name = os.path.basename(idx.data(Qt.ItemDataRole.UserRole)) if depth else "<root>"
        out.append("  " * depth + name + ("/" if is_dir and depth else ""))
        out.extend(_tree(view, idx, depth + 1))
    return out


@pytest.fixture
def lib(tmp_path):
    root = tmp_path / "lib"
    (root / "Artist B" / "Album 1").mkdir(parents=True)
    (root / "Artist A").mkdir(parents=True)
    seed_podcast_mp3(make_mp3(root / "Artist B" / "Album 1" / "02.mp3"))
    seed_podcast_mp3(make_mp3(root / "Artist B" / "Album 1" / "01.mp3"))
    make_flac(root / "Artist A" / "x.flac")
    make_mp3(root / "loose.mp3")
    return root


@pytest.fixture
def win(qtbot, lib):
    w = MainWindow()
    w.confirm_on_close = False
    w.naming = NamingOptions()
    qtbot.addWidget(w)
    w.show()
    w.load_paths([str(lib)])
    qtbot.waitUntil(lambda: len(w.file_model.paths) == 4 and w._loader is None, timeout=5000)
    return w


def test_tree_structure_sorted_folders_first(win):
    assert _tree(win.file_view) == [
        "<root>",
        "  Artist A/", "    x.flac",
        "  Artist B/", "    Album 1/", "      01.mp3", "      02.mp3",
        "  loose.mp3",
    ]
    root = win.file_proxy.index(0, 0)
    assert root.siblingAtColumn(1).data() == "4 files"
    assert win.file_view.isExpanded(root)


def test_selecting_folder_selects_its_files(win, lib):
    album = str(lib / "Artist B" / "Album 1")
    win.file_view.select_paths([album], current=album)
    assert sorted(os.path.basename(p) for p in win.selected_paths()) == ["01.mp3", "02.mp3"]
    assert len(win.tag_model.paths) == 2  # tag table shows the merged view


def test_filter_keeps_parent_folders(win):
    win.file_filter.setText("02")
    assert [l.strip() for l in _tree(win.file_view)] == \
        ["<root>", "Artist B/", "Album 1/", "02.mp3"]
    win.file_filter.setText("artist a")  # matching folder shows its contents
    assert [l.strip() for l in _tree(win.file_view)] == ["<root>", "Artist A/", "x.flac"]


def test_rename_folder_from_tree_keeps_expansion_and_selection(win, lib, monkeypatch):
    import mte.ui.main_window as mw

    album = str(lib / "Artist B" / "Album 1")
    win.file_view.select_paths([album], current=album)

    class Scripted(mw.RenameFolderDialog):
        def exec(self):
            assert self.selected_folder() == album
            self.name.setText("Album One")
            return 1

    monkeypatch.setattr(mw, "RenameFolderDialog", Scripted)
    win.rename_folder()
    new_album = str(lib / "Artist B" / "Album One")
    assert os.path.isdir(new_album)
    idx = win.file_view.proxy_index(new_album)
    assert idx.isValid() and win.file_view.isExpanded(idx)
    assert win.file_view.current_path() == new_album
    assert sorted(win.selected_paths()) == [os.path.join(new_album, "01.mp3"),
                                           os.path.join(new_album, "02.mp3")]


def test_opening_parent_folder_merges_roots(win, lib, qtbot):
    other = lib.parent / "other"
    other.mkdir()
    make_mp3(other / "y.mp3")
    win.load_paths([str(other)])
    qtbot.waitUntil(lambda: len(win.file_model.paths) == 5 and win._loader is None, timeout=5000)
    assert win.file_proxy.rowCount() == 2  # lib and other side by side
    win.load_paths([str(lib.parent)])  # parent of both: becomes the single root
    qtbot.waitUntil(lambda: win._loader is None, timeout=5000)
    assert win.file_proxy.rowCount() == 1
    assert len(win.file_view.all_paths()) == 5


def test_rename_on_save_moves_file_in_tree(win, lib, qtbot):
    from test_ui_smoke import _row
    win.naming = NamingOptions(rename=True, script="Sorted/%title%")
    f = str(lib / "Artist B" / "Album 1" / "01.mp3")
    win.file_view.select_path(f)
    win._inline_edit(_row(win, "ID3v2", "TIT2"), "Moved")
    qtbot.wait(10)
    win.save()
    qtbot.waitUntil(lambda: not win.session.dirty_files(), timeout=5000)
    new = str(lib / "Artist B" / "Album 1" / "Sorted" / "Moved.mp3")
    assert os.path.exists(new)
    assert new in win.file_view.all_paths() and f not in win.file_view.all_paths()
    assert win.file_view.current_path() == new  # selection follows the file
