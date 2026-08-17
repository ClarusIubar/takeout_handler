"""python -m eval.manual_probe 진입점.

eval/harness.py의 14개 태스크는 재현성과 grounding 증명(session_id) 때문에 전부 합성
픽스처(kyoto-trip-1 등)만 쓴다. 합성 decoy(예: "여행 일정" vs "여행 자금 저축 계획")가
실제 사용자의 진짜 대화 내용과는 무관한 상황을 시험하는 것일 수 있다는 지적에 따라, 그
합성 스위트는 건드리지 않고 같은 방법론(로컬 저추론 모델 + mcp_server의 실제
tool-calling 루프)을 사용자의 진짜 result/(또는 vault) 데이터에 대고 대화형으로 돌려볼
수 있게 하는 스크립트다.

실제 데이터는 정답을 미리 알 수 없어 자동 채점(pass/fail)을 할 수 없다 — tool 호출과
최종 답변을 그대로 보여주고 사람이 직접 판단한다. 디스크에는 아무 것도 저장하지 않는다
(eval/results/ 같은 리포트 파일을 만들지 않음) — 입출력에 진짜 개인 대화 내용이 그대로
들어가므로, 실수로 커밋/공유될 수 있는 새 파일 자체를 만들지 않는 게 안전하다."""

import json
import sys

from common.config import load_config
from eval.harness import SYSTEM_PROMPT, _call_tool, _list_tools
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
from mcp_server.config import build_arg_parser, resolve_server_paths

DEFAULT_MAX_ROUNDS = 5
_DETAIL_TRUNCATE = 500


def parse_args(argv=None):
    # mcp_server.config의 --source/--result-dir/--vault-dir을 그대로 재사용한다 —
    # python -m mcp_server와 동일한 경로 해석 규칙(CLI 플래그 > config.json > 기본값)을
    # 그대로 따라가려는 것.
    parser = build_arg_parser()
    parser.prog = "python -m eval.manual_probe"
    parser.description = (
        "실제 result/(또는 vault) 데이터를 대상으로 mcp_server tool을 대화형으로 "
        "수동 점검한다. 자동 채점 없음 — 개인 데이터라 정답을 미리 알 수 없다."
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"LM Studio 모델 id (기본: {DEFAULT_MODEL})")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"LM Studio API base URL (기본: {DEFAULT_BASE_URL})")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                         help=f"LM Studio 응답 대기 시간(초, 기본 {DEFAULT_TIMEOUT})")
    parser.add_argument("--max-rounds", type=int, default=DEFAULT_MAX_ROUNDS,
                         help="질문 하나당 tool 호출 라운드 상한(무한루프 방지용이지 채점 "
                              f"기준이 아님, 기본 {DEFAULT_MAX_ROUNDS})")
    return parser.parse_args(argv)


def _print_tool_call(call, result, error):
    is_error = error is not None or (result is not None and result.is_error)
    status = "ERROR" if is_error else "ok"
    if error:
        detail = error
    else:
        detail = json.dumps(result.structured_content, ensure_ascii=False)
    if len(detail) > _DETAIL_TRUNCATE:
        detail = detail[:_DETAIL_TRUNCATE] + "...(생략)"
    args_text = json.dumps(call["arguments"], ensure_ascii=False)
    print(f"  [tool:{status}] {call['name']}({args_text}) -> {detail}")


def _ask(server, openai_tools, prompt, model, base_url, timeout, max_rounds):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    for _round in range(max_rounds):
        response = chat_completion(messages, tools=openai_tools, model=model, base_url=base_url, timeout=timeout)
        msg = assistant_message(response)
        messages.append(msg)

        calls = extract_tool_calls(response)
        if not calls:
            break

        for call in calls:
            result, error = _call_tool(server, call["name"], call["arguments"])
            _print_tool_call(call, result, error)

            tool_text = error if error else json.dumps(result.structured_content, ensure_ascii=False)
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": tool_text,
            })

    final_text = messages[-1].get("content") or ""
    if messages[-1].get("role") != "assistant":
        response = chat_completion(messages, tools=None, model=model, base_url=base_url, timeout=timeout)
        final_text = assistant_message(response).get("content") or ""
    return final_text


def main(argv=None):
    args = parse_args(argv)

    try:
        from mcp_server.server import create_server
    except ImportError:
        print(
            "[오류] mcp 패키지가 설치돼 있지 않습니다. "
            "`pip install -e .[mcp]` 또는 `pip install -r requirements-mcp.txt`로 설치한 뒤 다시 실행하세요.",
            file=sys.stderr,
        )
        sys.exit(1)

    warning = check_context_length(model=args.model, base_url=args.base_url)
    if warning:
        print(warning, file=sys.stderr)

    try:
        result_dir, data_dirs = resolve_server_paths(args, load_config())
    except ValueError as exc:
        print(f"[오류] {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"[manual_probe] source={args.source} result_dir={result_dir}")
    print("자동 채점 없음 — tool 호출과 답변을 직접 읽고 판단하세요. 빈 줄/exit/Ctrl-D로 종료.\n")

    server = create_server(result_dir, data_dirs=data_dirs)
    openai_tools = [mcp_tool_to_openai(t) for t in _list_tools(server)]

    while True:
        try:
            prompt = input("질문> ").strip()
        except EOFError:
            print()
            break
        if not prompt or prompt in ("exit", "quit"):
            break

        try:
            final_text = _ask(server, openai_tools, prompt, args.model, args.base_url, args.timeout, args.max_rounds)
        except Exception as exc:
            # eval/harness.py::_run_task_once_safely와 같은 이유 — LM Studio/모델이
            # 특정 질문(특히 실제 데이터에만 있는, 합성 픽스처엔 없던 이모지 등 특이한
            # 문자를 tool-call 인자로 재생성하려다) 죽는 경우가 있다. 예외 하나로 대화형
            # 세션 전체가 끊기면 다음 질문을 이어서 던져볼 수가 없다.
            print(f"\n[오류] 이 질문에서 예외 발생, 이 질문만 건너뛰고 계속: {exc}\n")
            continue
        print(f"\n답변> {final_text}\n")


if __name__ == "__main__":
    main()
