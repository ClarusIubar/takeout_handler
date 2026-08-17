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

from eval.harness import _error_result  # noqa: E402
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
