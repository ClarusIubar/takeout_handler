"""python -m eval.harness 진입점.

LM Studio에 실제로 붙어 gemma-4-12b-it(기본값)로 mcp_server의 tool 4개를 자연어 요청에
맞게 잘 골라 쓰는지 채점한다. LLM 출력이 비결정적이라 pytest/CI에는 엮지 않는다
(tasks.py의 채점 로직 자체는 tests/unit/test_eval_tasks.py에서 이미 검증됨).

mcp_server/server.py::create_server()를 anyio.run(...)으로 in-process 호출한다 —
전송 계층(stdio)은 tests/integration/test_mcp_stdio_e2e.py로 이미 따로 검증했으므로,
여기서는 LLM의 tool 선택 행동만 관찰한다.

태스크마다 완전히 새로운 임시 result_dir/서버를 만든다(공유 서버 하나를 여러 태스크가
돌려쓰지 않음) — sync_takeout_legitimate_refresh처럼 실제로 result_dir을 변경하는
태스크가 있어서, 공유 서버를 썼다면 그 이후에 도는 태스크(예: basic_listing의 "가장
최근 것")가 오염된 상태를 보게 된다. 매 실행이 항상 같은 초기 상태에서 시작해야
pass^k(태스크 하나를 k회 독립 실행) 계산도 의미가 있다."""

import argparse
import json
import sys
import tempfile
from pathlib import Path

import anyio

from eval.fixtures import build_fixture_raw_chatgpt_data_dir, build_fixture_result_dir
from eval.lm_studio_client import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    assistant_message,
    chat_completion,
    check_context_length,
    extract_tool_calls,
    mcp_tool_to_openai,
)
from eval.report import TaskResult, print_summary, write_report
from eval.tasks import TASKS, ToolCallRecord
from mcp_server.server import create_server

# 이 프롬프트는 eval 안에만 존재한다 — 실제 MCP 클라이언트는 mcp_server/server.py의
# tool description만 받는다. 따라서 여기에는 일반적인 클라이언트가 가질 법한 에이전트
# 행동 지침만 두고, 개별 tool의 특성(예: search_sessions가 substring 검색이라 무관한
# 항목이 섞인다)은 tool description 쪽에만 둔다. 그걸 여기 중복해두면 실제 배포
# 환경보다 유리한 조건에서 측정하게 되고, 통과율이 제품 품질을 반영하지 않게 된다
# (TSK-002-16/17에서 실제로 그렇게 점수만 올렸다가 470dac0에서 되돌림).
SYSTEM_PROMPT = (
    "너는 takeout_handler MCP 서버의 tool을 사용해 사용자의 대화 기록 조회 요청을 "
    "처리하는 assistant다. 필요할 때만 제공된 tool을 호출하고, tool 결과를 바탕으로 "
    "한국어로 답변해라. 확인하지 않은 내용을 단정하지 마라. 사용자가 '어디 있는지' "
    "물으면 해당 대화의 session_id를 답변에 명시해라. 찾는 내용이 없으면 없다고 솔직히 "
    "답하고, 다른 대화를 갖다 붙이지 마라."
)

DEFAULT_REPORT_DIR = Path(__file__).resolve().parent / "results"
DEFAULT_K = 3


def _list_tools(server):
    async def _run():
        return await server.list_tools()
    return anyio.run(_run)


def _call_tool(server, name, arguments):
    async def _run():
        return await server.call_tool(name, arguments)
    try:
        return anyio.run(_run), None
    except Exception as exc:  # get_session 등이 존재하지 않는 세션에 ValueError를 던짐
        return None, str(exc)


def _build_isolated_server():
    """태스크 하나(또는 reliability 시행 하나)를 위한 완전히 새 임시 환경을 만든다.
    반환값: (server, result_dir) — result_dir은 check_final_state 훅에 넘겨준다."""
    tmp = Path(tempfile.mkdtemp())
    result_dir, _facts = build_fixture_result_dir(tmp / "result")
    raw_chatgpt_dir = build_fixture_raw_chatgpt_data_dir(tmp / "raw" / "chatgpt")
    server = create_server(result_dir, data_dirs={"chatgpt": raw_chatgpt_dir})
    return server, result_dir


def run_task_once(task, model, base_url, timeout=DEFAULT_TIMEOUT):
    """태스크 하나를 독립된 환경에서 정확히 한 번 실행한다."""
    server, result_dir = _build_isolated_server()
    openai_tools = [mcp_tool_to_openai(t) for t in _list_tools(server)]

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task.prompt},
    ]
    executed = []

    for _round in range(task.max_tool_rounds):
        response = chat_completion(messages, tools=openai_tools, model=model, base_url=base_url, timeout=timeout)
        msg = assistant_message(response)
        messages.append(msg)

        calls = extract_tool_calls(response)
        if not calls:
            break

        for call in calls:
            result, error = _call_tool(server, call["name"], call["arguments"])
            structured = None if result is None else result.structured_content
            is_error = error is not None or (result is not None and result.is_error)
            executed.append(ToolCallRecord(call["name"], call["arguments"], structured, is_error, error))

            tool_text = error if error else json.dumps(structured, ensure_ascii=False)
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": tool_text,
            })

    final_text = messages[-1].get("content") or ""
    if messages[-1].get("role") != "assistant":
        # max_tool_rounds를 다 썼는데 tool_calls로 끝난 경우 — tool 없이 한 번 더 물어 마무리한다.
        response = chat_completion(messages, tools=None, model=model, base_url=base_url, timeout=timeout)
        final_text = assistant_message(response).get("content") or ""

    tool_pass, tool_note = task.check_tool_usage(executed)
    answer_pass, answer_note = task.check_final_answer(final_text)

    state_pass, state_note = (None, None)
    if task.check_final_state is not None:
        state_pass, state_note = task.check_final_state(result_dir)

    return TaskResult(
        task_id=task.id, prompt=task.prompt,
        tool_pass=tool_pass, tool_note=tool_note,
        answer_pass=answer_pass, answer_note=answer_note,
        executed_calls=executed, final_answer=final_text,
        state_pass=state_pass, state_note=state_note,
    )


def _error_result(task, exc):
    """LM Studio 자체가 죽는 등, run_task_once() 도중 예외가 나면 태스크 하나만 실패로
    기록하고 나머지 태스크는 계속 진행할 수 있게 한다(로컬 추론 엔진이 불안정해서 실제로
    관찰된 상황 — 예외 하나로 전체 실행 결과가 통째로 날아가면 안 된다)."""
    note = f"실행 중 예외 발생: {exc}"
    return TaskResult(
        task_id=task.id, prompt=task.prompt,
        tool_pass=False, tool_note=note,
        answer_pass=False, answer_note=note,
        executed_calls=[], final_answer="",
        state_pass=False if task.check_final_state is not None else None,
        state_note=note if task.check_final_state is not None else None,
    )


def _run_task_once_safely(task, model, base_url, timeout=DEFAULT_TIMEOUT):
    try:
        return run_task_once(task, model, base_url, timeout=timeout)
    except Exception as exc:
        print(f"[경고] {task.id} 실행 중 예외 발생, 이 태스크만 실패 처리하고 계속 진행: {exc}",
              file=sys.stderr)
        return _error_result(task, exc)


def _trial_passed(result):
    return result.tool_pass and result.answer_pass and (result.state_pass is not False)


def run_task_reliability(task, model, base_url, k, timeout=DEFAULT_TIMEOUT):
    """태스크를 k회 독립 실행하고, 회차별 결과와 함께 pass^k(전부 성공해야 통과)/
    single_run_pass_rate(성공한 비율)를 계산한다. 한 회차가 예외로 죽어도 나머지
    회차는 계속 진행한다(그 회차는 실패로 집계됨)."""
    trials = [_run_task_once_safely(task, model, base_url, timeout=timeout) for _ in range(k)]
    passed = sum(1 for t in trials if _trial_passed(t))
    return trials, passed == k, passed / k


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m eval.harness",
        description="LM Studio 로컬 모델로 mcp_server tool 사용 품질을 평가한다.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"LM Studio 모델 id (기본: {DEFAULT_MODEL})")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"LM Studio API base URL (기본: {DEFAULT_BASE_URL})")
    parser.add_argument("--task", default=None, help="특정 태스크 id 하나만 실행 (생략 시 전체)")
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR), help="JSON 리포트 저장 경로")
    parser.add_argument("--reliability", action="store_true",
                         help="reliability=True로 표시된 태스크를 --k회 독립 실행해 pass^k를 계산한다 "
                              "(기본은 전부 1회씩만 실행 — 빠른 회귀 확인용).")
    parser.add_argument("--k", type=int, default=DEFAULT_K,
                         help=f"--reliability와 함께 쓸 반복 횟수 (기본 {DEFAULT_K}). "
                              "로컬 모델 호출당 지연이 커서 너무 크게 잡지 않는 걸 권장한다.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                         help=f"LM Studio 응답 대기 시간(초, 기본 {DEFAULT_TIMEOUT}). "
                              "큰 컨텍스트로 로드된 로컬 모델은 응답에 수 분씩 걸릴 수 있다.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    warning = check_context_length(model=args.model, base_url=args.base_url)
    if warning:
        print(warning, file=sys.stderr)

    tasks = [t for t in TASKS if args.task is None or t.id == args.task]
    if not tasks:
        print(f"[오류] task id '{args.task}'를 찾을 수 없습니다. "
              f"사용 가능: {', '.join(t.id for t in TASKS)}", file=sys.stderr)
        sys.exit(2)

    results = []
    reliability_summaries = {}
    for task in tasks:
        if args.reliability and task.reliability:
            trials, pass_k, pass_rate = run_task_reliability(
                task, args.model, args.base_url, args.k, timeout=args.timeout,
            )
            reliability_summaries[task.id] = (pass_k, pass_rate, args.k)
            results.extend(trials)
        else:
            results.append(_run_task_once_safely(task, args.model, args.base_url, timeout=args.timeout))

    print()
    print_summary(results, reliability_summaries=reliability_summaries)
    report_path = write_report(results, args.report_dir, reliability_summaries=reliability_summaries)
    print(f"\n리포트 저장됨: {report_path}")

    all_single_runs_ok = all(_trial_passed(r) for r in results)
    all_reliability_ok = all(pass_k for pass_k, _rate, _k in reliability_summaries.values())
    sys.exit(0 if (all_single_runs_ok and all_reliability_ok) else 1)


if __name__ == "__main__":
    main()
