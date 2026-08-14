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


def test_resolve_source_priority_cli_over_config_over_default(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "DATA_DIR", tmp_path / "data")
    cli_dir = tmp_path / "cli_source"
    cli_dir.mkdir()
    config_dir = tmp_path / "config_source"
    config_dir.mkdir()

    monkeypatch.setattr(run, "CONFIG", {"takeout_paths": {"chatgpt": str(config_dir)}})
    assert run.resolve_source("chatgpt", str(cli_dir)) == cli_dir.resolve()  # CLI가 최우선
    assert run.resolve_source("chatgpt", None) == config_dir.resolve()  # 다음은 config

    monkeypatch.setattr(run, "CONFIG", {"takeout_paths": {}})
    assert run.resolve_source("chatgpt", None) == tmp_path / "data" / "chatgpt"  # 마지막은 기본값


def test_resolve_output_dir_priority_cli_over_config_over_default(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "ROOT", tmp_path)

    monkeypatch.setattr(run, "CONFIG", {"markdown_output_dir": "configured_output"})
    cli_out = tmp_path / "cli_output"
    assert run.resolve_output_dir(str(cli_out)) == cli_out.resolve()
    assert run.resolve_output_dir(None) == (tmp_path / "configured_output").resolve()

    monkeypatch.setattr(run, "CONFIG", {})
    assert run.resolve_output_dir(None) == (tmp_path / "result").resolve()


def test_resolve_vault_dir_priority_and_unset(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "CONFIG", {"obsidian_vault_dir": str(tmp_path / "configured_vault")})
    cli_vault = tmp_path / "cli_vault"
    assert run.resolve_vault_dir(str(cli_vault)) == cli_vault.resolve()
    assert run.resolve_vault_dir(None) == (tmp_path / "configured_vault").resolve()

    monkeypatch.setattr(run, "CONFIG", {"obsidian_vault_dir": None})
    assert run.resolve_vault_dir(None) is None
