from pathlib import Path

from common.fs_discovery import is_junk_path, is_junk_segment


def test_is_junk_segment_macosx():
    assert is_junk_segment("__MACOSX") is True


def test_is_junk_segment_dotfile():
    assert is_junk_segment(".DS_Store") is True


def test_is_junk_segment_normal_name():
    assert is_junk_segment("conversations.json") is False


def test_is_junk_path_detects_macosx_ancestor(tmp_path):
    p = tmp_path / "__MACOSX" / "conversations.json"
    assert is_junk_path(p, tmp_path) is True


def test_is_junk_path_detects_dotfile_itself(tmp_path):
    p = tmp_path / ".conversations.json"
    assert is_junk_path(p, tmp_path) is True


def test_is_junk_path_normal_path_not_junk(tmp_path):
    p = tmp_path / "chatgpt-export" / "conversations.json"
    assert is_junk_path(p, tmp_path) is False
