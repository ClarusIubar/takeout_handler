# 어떤 지침이 어느 표면에 있어야 하는지를 고정한다(TSK-002-18).
#
# 배경: TSK-002-16/17에서 eval/harness.py의 SYSTEM_PROMPT를 고쳐 통과율을 올렸다가
# 과적합으로 판정해 되돌렸다(470dac0). SYSTEM_PROMPT는 eval 안에만 존재하고 실제 MCP
# 클라이언트는 mcp_server/server.py의 tool description만 받으므로, 하네스 프롬프트에만
# 넣은 개선은 제품을 바꾸지 않고 점수만 올린다.
#
# 그래서 두 표면의 역할을 분리해 고정한다:
#   - tool description(배포됨) — tool의 실제 속성과 그로부터 나오는 사용 지침
#   - SYSTEM_PROMPT(eval 전용) — 일반적인 에이전트 행동만. tool 특성 서술을 여기
#     중복해두면 배포 환경보다 유리한 조건에서 측정하게 된다.
import pytest

mcp = pytest.importorskip("mcp")

from eval.harness import SYSTEM_PROMPT  # noqa: E402

pytestmark = pytest.mark.mcp


def _search_sessions_description():
    from mcp_server.server import create_server
    import anyio, tempfile
    from pathlib import Path
    from eval.fixtures import build_fixture_result_dir

    tmp = Path(tempfile.mkdtemp())
    result_dir, _facts = build_fixture_result_dir(tmp / "result")
    server = create_server(result_dir)

    async def _run():
        return await server.list_tools()

    tools = anyio.run(_run)
    return next(t.description for t in tools if t.name == "search_sessions")


def test_search_sessions_description_guides_verifying_candidates_before_judging():
    # 관련성 판단을 위한 확인은 "사용자가 전체 내용을 원할 때"와는 다른 트리거다 —
    # 후보가 여러 개일 때 snippet만으로 관련/무관을 단정하지 말라는 유도가 배포되는
    # 표면에 있어야 한다. snippet이 짧다는 건 이 tool의 실제 속성이므로 fixture 특정이
    # 아니고, 실제 사용자에게도 그대로 유용하다.
    description = _search_sessions_description()
    assert "get_session" in description
    assert "판단" in description
    assert "snippet" in description


def test_system_prompt_does_not_duplicate_tool_specific_caveats():
    # search_sessions가 substring 검색이라 무관한 항목이 섞인다는 건 tool의 속성이고
    # 이미 tool description에 있다. 하네스 프롬프트에 같은 내용을 또 넣으면 실제 배포
    # 환경보다 유리한 조건에서 측정하게 된다(= 점수가 제품 품질을 반영하지 않음).
    assert "무관한 항목이 섞여" not in SYSTEM_PROMPT
    assert "matched_snippet" not in SYSTEM_PROMPT


def test_system_prompt_still_guides_general_agent_behavior():
    # 다만 일반적인 에이전트 행동 유도까지 버리는 건 과잉교정이다 — 확인 안 한 내용을
    # 단정하지 말라는 건 fixture와 무관하게 참인 지침이라 남긴다.
    assert "단정" in SYSTEM_PROMPT
