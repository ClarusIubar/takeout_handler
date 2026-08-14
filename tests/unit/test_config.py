import json

from common.config import DEFAULTS, load_config


def test_load_config_creates_default_file_when_missing(tmp_path, capsys):
    path = tmp_path / "config.json"
    config = load_config(path)

    assert path.exists()
    assert config == DEFAULTS
    assert "기본값으로 새로 만들었습니다" in capsys.readouterr().out


def test_load_config_reads_existing_file(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"markdown_output_dir": "my_output"}), encoding="utf-8")

    config = load_config(path)

    assert config["markdown_output_dir"] == "my_output"
    # 파일에 없는 키는 기본값으로 채워진다 (마이그레이션 걱정 없음)
    assert config["vault_subdirs"] == DEFAULTS["vault_subdirs"]


def test_load_config_falls_back_to_defaults_on_corrupted_json(tmp_path, capsys):
    path = tmp_path / "config.json"
    path.write_text("{ 이건 json이 아님", encoding="utf-8")

    config = load_config(path)

    assert config == DEFAULTS
    assert "파싱 실패" in capsys.readouterr().out
    # 손상된 파일은 그대로 둔다(사용자가 직접 고칠 수 있게)
    assert path.read_text(encoding="utf-8") == "{ 이건 json이 아님"


def test_load_config_falls_back_when_top_level_is_not_object(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    config = load_config(path)

    assert config == DEFAULTS


def test_load_config_does_not_overwrite_existing_valid_file(tmp_path):
    path = tmp_path / "config.json"
    custom = {"markdown_output_dir": "custom"}
    path.write_text(json.dumps(custom), encoding="utf-8")

    load_config(path)

    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk == custom  # load_config가 기본값으로 덮어쓰지 않았는지
