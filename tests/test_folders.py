import os

import pytest

from mte.core.folders import ancestor_choices, remap_path, rename_folder, validate_folder_name


def test_validate_folder_name():
    assert validate_folder_name("Album (2013)") is None
    assert validate_folder_name("") and validate_folder_name("   ")
    assert validate_folder_name("a/b") and validate_folder_name('a:b') and validate_folder_name("..")
    assert validate_folder_name("trailing.") and validate_folder_name("trailing ")


def test_rename_folder(tmp_path):
    old = tmp_path / "Old"
    (old / "sub").mkdir(parents=True)
    (old / "sub" / "x.mp3").write_bytes(b"x")
    new = rename_folder(str(old), "New")
    assert new == str(tmp_path / "New") and (tmp_path / "New" / "sub" / "x.mp3").exists()
    assert remap_path(str(old / "sub" / "x.mp3"), str(old), new) == \
        str(tmp_path / "New" / "sub" / "x.mp3")
    assert remap_path(str(tmp_path / "Older" / "y.mp3"), str(old), new) == \
        str(tmp_path / "Older" / "y.mp3")  # prefix of a name is not a parent


def test_rename_folder_refuses_existing_and_allows_case_change(tmp_path):
    (tmp_path / "A").mkdir()
    (tmp_path / "B").mkdir()
    with pytest.raises(FileExistsError):
        rename_folder(str(tmp_path / "A"), "B")
    new = rename_folder(str(tmp_path / "A"), "a")
    assert os.path.basename(new) == "a" and "a" in os.listdir(tmp_path)


def test_ancestor_choices(tmp_path):
    a = str(tmp_path / "lib" / "Artist" / "Album" / "1.mp3")
    b = str(tmp_path / "lib" / "Other" / "2.mp3")
    assert ancestor_choices(a, [a, b]) == [str(tmp_path / "lib" / "Artist" / "Album"),
                                          str(tmp_path / "lib" / "Artist"),
                                          str(tmp_path / "lib")]
    assert ancestor_choices(a, [a]) == [str(tmp_path / "lib" / "Artist" / "Album")]
