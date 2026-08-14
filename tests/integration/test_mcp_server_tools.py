"""mcp_server.server.create_server()가 실제 mcp SDK 배선(도구 등록/호출, 리소스 읽기)
아래에서 end-to-end로 동작하는지 검증한다. mcp가 설치돼 있지 않으면 스킵한다."""

import json

import anyio
import pytest

mcp = pytest.importorskip("mcp")

from common.session_markdown import build_session_markdown  # noqa: E402
from mcp_server.server import create_server  # noqa: E402

pytestmark = [pytest.mark.integration, pytest.mark.mcp]


def _write_session(dir_path, vendor, session_id, title, date_str, turns):
    dir_path.mkdir(parents=True, exist_ok=True)
    md, _hash = build_session_markdown(
        vendor_tag=vendor, vendor_label=vendor, title=title,
        session_id=session_id, url="https://x", date_str=date_str, turns=turns,
    )
    (dir_path / f"{session_id}.md").write_text(md, encoding="utf-8")


def _turns():
    return [
        {"role": "user", "text": "MCP 서버가 뭐야?", "time_str": "t0"},
        {"role": "assistant", "text": "Model Context Protocol입니다", "time_str": "t1"},
    ]


def _call_tool(server, name, arguments):
    async def _run():
        return await server.call_tool(name, arguments)
    return anyio.run(_run)


def _read_resource(server, uri):
    async def _run():
        return list(await server.read_resource(uri))
    return anyio.run(_run)


def test_no_write_tools_beyond_sync_takeout_are_registered(tmp_path):
    server = create_server(tmp_path)

    async def _run():
        return await server.list_tools()
    listed = anyio.run(_run)
    names = {t.name for t in listed}

    assert names == {"list_sessions", "search_sessions", "get_session", "sync_takeout"}
    assert not any("publish" in n or "vault" in n or "delete" in n for n in names)


def test_list_sessions_tool_returns_summaries(tmp_path):
    _write_session(tmp_path / "chatgpt", "chatgpt", "s1", "제목", "2024-01-01", _turns())

    server = create_server(tmp_path)
    result = _call_tool(server, "list_sessions", {})

    assert result.is_error is False
    sessions = result.structured_content["result"]
    assert [s["session_id"] for s in sessions] == ["s1"]
    assert "turns" not in sessions[0]


def test_search_sessions_tool_finds_by_turn_text(tmp_path):
    _write_session(tmp_path / "chatgpt", "chatgpt", "s1", "제목", "2024-01-01", _turns())

    server = create_server(tmp_path)
    result = _call_tool(server, "search_sessions", {"query": "model context protocol"})

    hits = result.structured_content["result"]
    assert [h["session_id"] for h in hits] == ["s1"]
    assert "matched_snippet" in hits[0]


def test_get_session_tool_returns_full_turns_as_json(tmp_path):
    _write_session(tmp_path / "chatgpt", "chatgpt", "s1", "제목", "2024-01-01", _turns())

    server = create_server(tmp_path)
    result = _call_tool(server, "get_session", {"vendor": "chatgpt", "session_id": "s1"})

    record = result.structured_content["result"]
    assert record["session_id"] == "s1"
    assert len(record["turns"]) == 2


def test_get_session_tool_markdown_format_returns_raw_rendered_text(tmp_path):
    _write_session(tmp_path / "chatgpt", "chatgpt", "s1", "제목", "2024-01-01", _turns())

    server = create_server(tmp_path)
    result = _call_tool(server, "get_session", {"vendor": "chatgpt", "session_id": "s1", "format": "markdown"})

    text = result.content[0].text
    assert text.startswith("---\n")
    assert "<!-- turn:" in text


def test_get_session_tool_raises_for_missing_session(tmp_path):
    server = create_server(tmp_path)
    with pytest.raises(Exception, match="세션을 찾을 수 없음"):
        _call_tool(server, "get_session", {"vendor": "chatgpt", "session_id": "missing"})


def test_sync_takeout_populates_result_dir_and_refreshes_index(tmp_path, minimal_chatgpt_export):
    data_dir = tmp_path / "data" / "chatgpt"
    minimal_chatgpt_export(data_dir)
    result_dir = tmp_path / "result"

    server = create_server(result_dir, data_dirs={"chatgpt": data_dir})
    sync_result = _call_tool(server, "sync_takeout", {"vendor": "chatgpt"})
    summary = sync_result.structured_content["chatgpt"]

    assert summary["sessions_found"] == 1
    assert (result_dir / "chatgpt" / "conv-1.md").exists()

    listed = _call_tool(server, "list_sessions", {})
    assert [s["session_id"] for s in listed.structured_content["result"]] == ["conv-1"]


def test_sync_takeout_never_touches_a_vault_directory(tmp_path, minimal_chatgpt_export):
    data_dir = tmp_path / "data" / "chatgpt"
    minimal_chatgpt_export(data_dir)
    result_dir = tmp_path / "result"
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()

    server = create_server(result_dir, data_dirs={"chatgpt": data_dir})
    _call_tool(server, "sync_takeout", {"vendor": "chatgpt"})

    assert list(vault_dir.iterdir()) == []


def test_sync_takeout_reports_skip_when_data_dir_not_configured(tmp_path):
    server = create_server(tmp_path)
    result = _call_tool(server, "sync_takeout", {"vendor": "chatgpt"})
    assert result.structured_content["chatgpt"]["skipped"] is True


def test_sessions_resource_lists_all_sessions(tmp_path):
    _write_session(tmp_path / "chatgpt", "chatgpt", "s1", "제목", "2024-01-01", _turns())

    server = create_server(tmp_path)
    contents = _read_resource(server, "takeout://sessions")

    payload = json.loads(contents[0].content)
    assert [s["session_id"] for s in payload] == ["s1"]


def test_session_json_resource_returns_full_record(tmp_path):
    _write_session(tmp_path / "chatgpt", "chatgpt", "s1", "제목", "2024-01-01", _turns())

    server = create_server(tmp_path)
    contents = _read_resource(server, "takeout://sessions/chatgpt/s1.json")

    payload = json.loads(contents[0].content)
    assert len(payload["turns"]) == 2


def test_session_markdown_resource_returns_raw_file_bytes(tmp_path):
    _write_session(tmp_path / "chatgpt", "chatgpt", "s1", "제목", "2024-01-01", _turns())
    raw = (tmp_path / "chatgpt" / "s1.md").read_text(encoding="utf-8")

    server = create_server(tmp_path)
    contents = _read_resource(server, "takeout://sessions/chatgpt/s1.md")

    assert contents[0].content == raw
