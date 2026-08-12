import zipfile

import pytest

import run


def test_resolve_input_directory_used_as_is(tmp_path):
    d = tmp_path / "some_folder"
    d.mkdir()
    assert run.resolve_input("chatgpt", str(d)) == d.resolve()


def test_resolve_input_missing_path_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        run.resolve_input("chatgpt", str(tmp_path / "does-not-exist"))


def test_resolve_input_non_zip_non_dir_raises(tmp_path):
    f = tmp_path / "not_a_zip.txt"
    f.write_text("hi", encoding="utf-8")
    with pytest.raises(ValueError):
        run.resolve_input("chatgpt", str(f))


def test_resolve_input_extracts_zip_into_data_dir_without_touching_source(tmp_path, monkeypatch):
    # 원본 zip은 프로젝트 밖(예: 다운로드 폴더) 아무 곳에나 있어도 되고, 압축 해제
    # 결과물은 항상 이 프로젝트가 관리하는 DATA_DIR/<vendor>/ 아래에만 생겨야 한다.
    monkeypatch.setattr(run, "DATA_DIR", tmp_path / "data")
    src_zip = tmp_path / "outside_project" / "export.zip"
    src_zip.parent.mkdir(parents=True)
    with zipfile.ZipFile(src_zip, "w") as zf:
        zf.writestr("conversations.json", "[]")

    result = run.resolve_input("chatgpt", str(src_zip))

    assert result == run.DATA_DIR / "chatgpt"
    assert (result / "conversations.json").exists()
    assert src_zip.exists()  # 원본은 그대로
