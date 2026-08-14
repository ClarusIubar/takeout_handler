# run.main()을 통해 argparse -> resolve_source -> run_vendor -> convert()까지 전체
# 배선을 검증한다. 지금까지는 main()을 호출하는 테스트가 하나도 없었다 (grep으로 확인
# 됨) — 개별 함수는 다 맞아도 CLI에서 실제로 이어붙이면 깨지는 경우를 이 테스트가 잡는다.
#
# main()은 sys.argv를 직접 읽고, 무조건 실제 프로젝트의 config.json 경로로
# load_config()를 호출하므로 (`common/config.py`의 CONFIG_PATH), patched_config_path
# fixture로 그 경로를 tmp_path 아래로 돌려놓지 않으면 이 테스트가 진짜 프로젝트 파일을
# 건드리게 된다 — 아래 모든 테스트가 patched_config_path를 요청하는 이유.
import pytest

import run

pytestmark = pytest.mark.integration


def test_dry_run_does_not_write_files(tmp_path, minimal_chatgpt_export, patched_config_path, monkeypatch):
    data_dir = tmp_path / "chatgpt_src"
    minimal_chatgpt_export(data_dir, conversation_id="conv-1")
    result_dir = tmp_path / "result"

    monkeypatch.setattr("sys.argv", [
        "run.py",
        "--vendor", "chatgpt",
        "--input", f"chatgpt={data_dir}",
        "--output-dir", str(result_dir),
        "--dry-run",
    ])

    run.main()  # SystemExit을 던지면 이 테스트 자체가 실패해야 정상 — 여기선 성공 종료 기대

    assert not list(result_dir.glob("chatgpt/*.md"))


def test_write_after_dry_run_creates_file(tmp_path, minimal_chatgpt_export, patched_config_path, monkeypatch):
    data_dir = tmp_path / "chatgpt_src"
    minimal_chatgpt_export(data_dir, conversation_id="conv-1")
    result_dir = tmp_path / "result"

    argv = [
        "run.py",
        "--vendor", "chatgpt",
        "--input", f"chatgpt={data_dir}",
        "--output-dir", str(result_dir),
    ]

    monkeypatch.setattr("sys.argv", argv + ["--dry-run"])
    run.main()
    assert not list(result_dir.glob("chatgpt/*.md"))

    monkeypatch.setattr("sys.argv", argv)
    run.main()

    md_files = list(result_dir.glob("chatgpt/*.md"))
    assert len(md_files) == 1
    assert md_files[0].name == "conv-1.md"
