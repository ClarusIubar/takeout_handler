# eval/harness.py의 예외 -> TaskResult 변환 순수 로직만 테스트한다. run_task_once
# 자체는 실제 LM Studio HTTP 호출이 필요해서(하네스의 나머지 부분과 동일하게) 여기서
# 검증하지 않는다 — LM Studio 엔진이 요청 도중 죽는 것처럼 태스크 하나의 예외가 전체
# 실행을 끊지 않아야 한다는 요구사항만 고정한다.
#
# eval.harness는 모듈 최상단에서 mcp_server.server를 import하고, 그게 다시 mcp SDK를
# 요구한다(mcp_server.__main__과 달리 지연 import가 아님 — eval 하네스는 애초에 mcp
# 없이는 아무 의미가 없으므로). mcp 미설치 환경(전역 pytest 스위트)에서도 전체가
# 깨지지 않게 여기서 건너뛴다.
import pytest

mcp = pytest.importorskip("mcp")

from eval.harness import SYSTEM_PROMPT, _error_result  # noqa: E402
from eval.tasks import TASKS  # noqa: E402

pytestmark = pytest.mark.mcp


def test_error_result_marks_all_axes_failed():
    task = next(t for t in TASKS if t.id == "basic_listing")
    result = _error_result(task, RuntimeError("Engine protocol predict request failed: fetch failed"))

    assert result.task_id == "basic_listing"
    assert result.tool_pass is False
    assert result.answer_pass is False
    assert "fetch failed" in result.tool_note


def test_error_result_state_axis_stays_none_when_task_has_no_state_check():
    task = next(t for t in TASKS if t.id == "basic_listing")
    result = _error_result(task, RuntimeError("boom"))
    assert result.state_pass is None


def test_error_result_state_axis_marked_failed_when_task_has_state_check():
    task = next(t for t in TASKS if t.id == "sync_takeout_legitimate_refresh")
    result = _error_result(task, RuntimeError("boom"))
    assert result.state_pass is False


def test_system_prompt_requires_verification_before_finalizing_answer():
    # 실측(gemma-4-12b-it, TSK-002-16): search_sessions 결과만 보고 get_session
    # 검증 없이 decoy(career-chat-1)를 정답처럼 나열한 사례 — 검증을 생략하면
    # "모른다"고 답하는 대신 snippet만으로 확신에 찬 오답을 낸다. SYSTEM_PROMPT에
    # 후보가 여럿이면 확정 전에 get_session으로 확인하라는 지침을 명시적으로 요구.
    assert "get_session" in SYSTEM_PROMPT


def test_system_prompt_requires_explicit_per_candidate_judgment():
    # 실측(gemma-4-12b-it, TSK-002-16): "무조건 get_session으로 확인해라"까지만
    # 지시했더니, 실제로 get_session은 부르는데 읽은 내용을 판단에 안 쓰고 후보를
    # 전부 정답처럼 나열했다(검증과 판단이 분리됨) — 야오 외(2022)의 리액트 기법이
    # 보이는 것처럼, 도구 결과를 본 뒤 최종 답변 전에 "관련 있는가: 예/아니오"를
    # 명시적으로 판정하게 하는 중간 추론 단계가 빠져 있었다. 이 지침이 실제로
    # 박혀 있는지 고정한다.
    assert "관련 있는가" in SYSTEM_PROMPT
