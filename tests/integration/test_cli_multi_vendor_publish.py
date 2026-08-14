# --publish까지 포함한 전체 배선: run.main()이 두 벤더를 동시에 돌리고, publish_vendors()
# 가 각 벤더의 result_dir/<name>/을 vault_dir/<vault_subdirs[name]>/으로 미러링하는지
# 검증한다. vault_subdirs 매핑(ChatGPT/Gemini)이 config 기본값에서 실제로 적용되는지도
# 확인 — 지금까지 이 전체 사슬을 main()으로 검증한 테스트는 없었다.
import pytest

import run

pytestmark = pytest.mark.integration


def test_multi_vendor_publish_mirrors_result_to_vault_subdirs(
    tmp_path, minimal_chatgpt_export, minimal_gemini_export, patched_config_path, monkeypatch
):
    chatgpt_src = tmp_path / "chatgpt_src"
    gemini_src = tmp_path / "gemini_src"
    minimal_chatgpt_export(chatgpt_src, conversation_id="conv-1")
    minimal_gemini_export(gemini_src, session_id="session-abc123")

    result_dir = tmp_path / "result"
    vault_dir = tmp_path / "vault"

    monkeypatch.setattr("sys.argv", [
        "run.py",
        "--vendor", "chatgpt", "--vendor", "gemini",
        "--input", f"chatgpt={chatgpt_src}",
        "--input", f"gemini={gemini_src}",
        "--output-dir", str(result_dir),
        "--vault-dir", str(vault_dir),
        "--publish",
    ])

    run.main()

    chatgpt_result = result_dir / "chatgpt" / "conv-1.md"
    gemini_result = result_dir / "gemini" / "session-abc123.md"
    assert chatgpt_result.exists()
    assert gemini_result.exists()

    # config 기본값의 vault_subdirs = {"chatgpt": "ChatGPT", "gemini": "Gemini"}
    chatgpt_vault = vault_dir / "ChatGPT" / "conv-1.md"
    gemini_vault = vault_dir / "Gemini" / "session-abc123.md"
    assert chatgpt_vault.read_bytes() == chatgpt_result.read_bytes()
    assert gemini_vault.read_bytes() == gemini_result.read_bytes()


def test_publish_rerun_is_idempotent(
    tmp_path, minimal_chatgpt_export, patched_config_path, monkeypatch
):
    chatgpt_src = tmp_path / "chatgpt_src"
    minimal_chatgpt_export(chatgpt_src, conversation_id="conv-1")
    result_dir = tmp_path / "result"
    vault_dir = tmp_path / "vault"

    argv = [
        "run.py",
        "--vendor", "chatgpt",
        "--input", f"chatgpt={chatgpt_src}",
        "--output-dir", str(result_dir),
        "--vault-dir", str(vault_dir),
        "--publish",
    ]
    monkeypatch.setattr("sys.argv", argv)

    run.main()
    first_vault_mtime = (vault_dir / "ChatGPT" / "conv-1.md").stat().st_mtime_ns

    run.main()
    second_vault_mtime = (vault_dir / "ChatGPT" / "conv-1.md").stat().st_mtime_ns

    # unchanged로 판정되면 파일을 다시 안 쓰므로 mtime이 그대로여야 한다.
    assert second_vault_mtime == first_vault_mtime
