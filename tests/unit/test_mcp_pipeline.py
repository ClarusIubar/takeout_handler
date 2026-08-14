import contextlib
import io

from mcp_server import pipeline


def test_discover_vendors_matches_vendors_base(monkeypatch):
    assert "chatgpt" in pipeline.discover_vendors()
    assert "gemini" in pipeline.discover_vendors()


def test_sync_vendor_returns_stats_and_captures_stdout(tmp_path, minimal_chatgpt_export):
    data_dir = tmp_path / "data" / "chatgpt"
    minimal_chatgpt_export(data_dir)
    result_dir = tmp_path / "result" / "chatgpt"

    vendors = pipeline.discover_vendors()
    module = vendors["chatgpt"]

    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        stats, log_text = pipeline.sync_vendor("chatgpt", module, False, data_dir, result_dir)

    assert stats is not None
    assert stats.sessions_found == 1
    assert (result_dir / "conv-1.md").exists()
    # run_vendor()의 print() 출력이 진짜 stdout으로 새지 않고 log_text로만 회수됐는지 확인
    # (MCP stdio transport 오염 방지가 이 함수의 핵심 목적).
    assert captured.getvalue() == ""
    assert "ChatGPT" in log_text


def test_sync_vendor_returns_none_stats_when_data_dir_missing(tmp_path):
    vendors = pipeline.discover_vendors()
    module = vendors["chatgpt"]

    stats, log_text = pipeline.sync_vendor(
        "chatgpt", module, False, tmp_path / "no-such-dir", tmp_path / "result"
    )

    assert stats is None
    assert "찾지 못했습니다" in log_text
