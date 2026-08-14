import zipfile

import mcp_server.config as mcp_config
from mcp_server.config import ROOT, build_arg_parser, resolve_server_paths


def _args(source="result", result_dir=None, vault_dir=None):
    return build_arg_parser().parse_args(
        ["--source", source]
        + (["--result-dir", result_dir] if result_dir else [])
        + (["--vault-dir", vault_dir] if vault_dir else [])
    )


def test_default_result_dir_is_project_root_result(monkeypatch):
    result_dir, _data_dirs = resolve_server_paths(_args(), config={})
    assert result_dir == (ROOT / "result").resolve()


def test_config_markdown_output_dir_overrides_default():
    result_dir, _ = resolve_server_paths(_args(), config={"markdown_output_dir": "custom-out"})
    assert result_dir == (ROOT / "custom-out").resolve()


def test_cli_result_dir_overrides_config(tmp_path):
    result_dir, _ = resolve_server_paths(
        _args(result_dir=str(tmp_path / "cli-out")),
        config={"markdown_output_dir": "custom-out"},
    )
    assert result_dir == (tmp_path / "cli-out").resolve()


def test_source_vault_uses_config_vault_dir(tmp_path):
    vault = tmp_path / "MyVault"
    result_dir, _ = resolve_server_paths(_args(source="vault"), config={"obsidian_vault_dir": str(vault)})
    assert result_dir == vault.resolve()


def test_source_vault_cli_override_wins(tmp_path):
    cli_vault = tmp_path / "cli-vault"
    result_dir, _ = resolve_server_paths(
        _args(source="vault", vault_dir=str(cli_vault)),
        config={"obsidian_vault_dir": str(tmp_path / "config-vault")},
    )
    assert result_dir == cli_vault.resolve()


def test_source_vault_without_any_vault_dir_raises():
    try:
        resolve_server_paths(_args(source="vault"), config={})
        assert False, "ValueError를 기대했지만 발생하지 않음"
    except ValueError:
        pass


def test_data_dirs_default_to_data_subdir_per_vendor():
    _result_dir, data_dirs = resolve_server_paths(_args(), config={})
    assert data_dirs["chatgpt"] == ROOT / "data" / "chatgpt"
    assert data_dirs["gemini"] == ROOT / "data" / "gemini"


def test_data_dirs_use_configured_directory_path(tmp_path):
    custom = tmp_path / "my-chatgpt-export"
    custom.mkdir()
    _result_dir, data_dirs = resolve_server_paths(_args(), config={"takeout_paths": {"chatgpt": str(custom)}})
    assert data_dirs["chatgpt"] == custom.resolve()


def test_resolve_data_dir_falls_back_to_default_for_non_dir_non_zip_path(tmp_path):
    weird_file = tmp_path / "not-a-zip.txt"
    weird_file.write_text("hi", encoding="utf-8")

    _result_dir, data_dirs = resolve_server_paths(_args(), config={"takeout_paths": {"chatgpt": str(weird_file)}})

    assert data_dirs["chatgpt"] == ROOT / "data" / "chatgpt"


def test_resolve_server_paths_defaults_cli_args_when_omitted():
    result_dir, _data_dirs = resolve_server_paths(config={})
    assert result_dir == (ROOT / "result").resolve()


def test_resolve_server_paths_defaults_config_when_omitted(patched_config_path):
    # config를 생략하면 실제 load_config()가 호출되므로, patched_config_path로
    # 실제 프로젝트의 config.json 대신 tmp_path를 보게 한다.
    result_dir, _data_dirs = resolve_server_paths(_args())
    assert result_dir == (ROOT / "result").resolve()
    assert patched_config_path.exists()  # load_config()가 기본값으로 새로 만든 파일


def test_data_dirs_extracts_configured_zip_path(tmp_path, monkeypatch):
    # 실제 프로젝트의 data/ 아래에 압축을 풀면 안 되므로 DATA_DIR을 tmp_path로 돌린다
    # (conftest.py의 run.DATA_DIR 격리와 동일한 이유).
    monkeypatch.setattr(mcp_config, "DATA_DIR", tmp_path / "data")

    zip_path = tmp_path / "export.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("conversations.json", "[]")

    _result_dir, data_dirs = resolve_server_paths(_args(), config={"takeout_paths": {"chatgpt": str(zip_path)}})

    extracted = data_dirs["chatgpt"]
    assert (extracted / "conversations.json").exists()
