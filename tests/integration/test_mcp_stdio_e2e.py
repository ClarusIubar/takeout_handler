"""python -m mcp_server를 진짜 서브프로세스로 띄우고, 진짜 stdio(JSON-RPC over
stdin/stdout) 클라이언트로 붙어서 검증한다.

앞선 통합 테스트(test_mcp_server_tools.py)는 create_server()를 테스트 안에서 직접
만들어 mcp SDK의 call_tool()/read_resource()를 in-process로 호출한다 — 이건
__main__.py가 조립하는 전체 흐름(config 로딩 -> 경로 해석 -> 서버 생성 -> stdio 루프
진입)은 검증하지 못한다. 실제로 이 테스트를 처음 짤 때, common.config.load_config()가
config.json이 없으면 안내 메시지를 stdout에 print()한다는 사실이 진짜 stdio 클라이언트를
붙여보고 나서야 드러났다 — 그 한 줄이 MCP JSON-RPC 프레이밍을 깨서 클라이언트가 "Invalid
JSON" 에러를 냈다. in-process 호출 테스트로는 이 클래스의 버그(stdout 오염)를 원천적으로
잡을 수 없다.

서브프로세스는 별도 프로세스라 monkeypatch로 common.config.CONFIG_PATH를 격리할 수
없으므로(patched_config_path는 같은 프로세스에서만 유효), 필요한 모듈만 tmp_path에
복사해서 그 사본을 대상으로 띄운다 — 실제 프로젝트의 config.json을 절대 건드리지 않는다.
"""

import shutil
import sys
from pathlib import Path

import anyio
import pytest

mcp = pytest.importorskip("mcp")

from mcp.client.session import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402

from common.session_markdown import build_session_markdown  # noqa: E402

pytestmark = [pytest.mark.integration, pytest.mark.mcp]

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _make_isolated_repo_copy(dest):
    """mcp_server 실행에 필요한 최소 모듈만 dest 아래로 복사한다 (common/, vendors/,
    mcp_server/, run.py) — 실제 프로젝트 config.json과 완전히 분리된 사본."""
    for name in ("common", "vendors", "mcp_server"):
        shutil.copytree(REPO_ROOT / name, dest / name)
    shutil.copy2(REPO_ROOT / "run.py", dest / "run.py")


def _write_session(result_dir, vendor, session_id, title, date_str):
    vendor_dir = result_dir / vendor
    vendor_dir.mkdir(parents=True, exist_ok=True)
    md, _hash = build_session_markdown(
        vendor_tag=vendor, vendor_label=vendor, title=title, session_id=session_id,
        url="https://x", date_str=date_str,
        turns=[
            {"role": "user", "text": "MCP 서버가 뭐야?", "time_str": "t0"},
            {"role": "assistant", "text": "Model Context Protocol입니다", "time_str": "t1"},
        ],
    )
    (vendor_dir / f"{session_id}.md").write_text(md, encoding="utf-8")


async def _run_session(repo_copy, result_dir, call):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server", "--result-dir", str(result_dir)],
        cwd=str(repo_copy),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await call(session)


def test_real_stdio_subprocess_initializes_and_lists_tools(tmp_path):
    repo_copy = tmp_path / "repo"
    _make_isolated_repo_copy(repo_copy)
    result_dir = tmp_path / "result"
    _write_session(result_dir, "chatgpt", "s1", "e2e 제목", "2024-01-01")

    async def call(session):
        return await session.list_tools()

    listed = anyio.run(_run_session, repo_copy, result_dir, call)
    assert {t.name for t in listed.tools} == {"list_sessions", "search_sessions", "get_session", "sync_takeout"}


def test_real_stdio_subprocess_list_sessions_returns_real_data(tmp_path):
    repo_copy = tmp_path / "repo"
    _make_isolated_repo_copy(repo_copy)
    result_dir = tmp_path / "result"
    _write_session(result_dir, "chatgpt", "s1", "e2e 제목", "2024-01-01")

    async def call(session):
        return await session.call_tool("list_sessions", {})

    result = anyio.run(_run_session, repo_copy, result_dir, call)
    assert result.is_error is False
    sessions = result.structured_content["result"]
    assert [s["session_id"] for s in sessions] == ["s1"]


def test_real_stdio_subprocess_search_and_get_session_round_trip(tmp_path):
    repo_copy = tmp_path / "repo"
    _make_isolated_repo_copy(repo_copy)
    result_dir = tmp_path / "result"
    _write_session(result_dir, "chatgpt", "s1", "e2e 제목", "2024-01-01")

    async def call(session):
        search_result = await session.call_tool("search_sessions", {"query": "model context protocol"})
        get_result = await session.call_tool("get_session", {"vendor": "chatgpt", "session_id": "s1"})
        return search_result, get_result

    search_result, get_result = anyio.run(_run_session, repo_copy, result_dir, call)

    hits = search_result.structured_content["result"]
    assert [h["session_id"] for h in hits] == ["s1"]

    record = get_result.structured_content["result"]
    assert len(record["turns"]) == 2


def test_real_stdio_subprocess_never_creates_the_real_project_config(tmp_path):
    # 이 테스트 스위트 자체가 실제 config.json을 실수로 만들지는 않는지 확인하는 안전망.
    real_config = REPO_ROOT / "config.json"
    existed_before = real_config.exists()

    repo_copy = tmp_path / "repo"
    _make_isolated_repo_copy(repo_copy)
    result_dir = tmp_path / "result"

    async def call(session):
        return await session.list_tools()

    anyio.run(_run_session, repo_copy, result_dir, call)

    assert real_config.exists() == existed_before
    assert (repo_copy / "config.json").exists()
