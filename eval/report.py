"""eval 결과 콘솔 요약 표 + JSON 리포트 작성. stdlib만 사용한다(tabulate/rich 등
불필요 — 이 저장소의 무의존성 기조를 eval/에서도 유지)."""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class TaskResult:
    task_id: str
    prompt: str
    tool_pass: bool
    tool_note: str
    answer_pass: bool
    answer_note: str
    executed_calls: list = field(default_factory=list)
    final_answer: str = ""
    # sync_takeout처럼 실제 파일시스템 상태를 확인하는 태스크에서만 채워진다(τ-bench식
    # state-based 채점). 해당 없는 태스크는 None으로 남는다 — False(실패)와 구분하기 위함.
    state_pass: Optional[bool] = None
    state_note: Optional[str] = None


def _serialize_call(call):
    return {
        "name": call.name,
        "arguments": call.arguments,
        "structured_content": call.structured_content,
        "is_error": call.is_error,
        "error": call.error,
    }


def _serialize_result(r):
    return {
        "task_id": r.task_id,
        "prompt": r.prompt,
        "tool_pass": r.tool_pass,
        "tool_note": r.tool_note,
        "answer_pass": r.answer_pass,
        "answer_note": r.answer_note,
        "final_answer": r.final_answer,
        "state_pass": r.state_pass,
        "state_note": r.state_note,
        "executed_calls": [_serialize_call(c) for c in r.executed_calls],
    }


def print_summary(results, reliability_summaries=None):
    reliability_summaries = reliability_summaries or {}

    header = f"{'task_id':28} {'tool':6} {'answer':6} {'state':6} note"
    print(header)
    print("-" * len(header))
    for r in results:
        if r.task_id in reliability_summaries:
            continue  # 아래 pass^k 요약 블록에서 따로 다룸
        note = r.tool_note if not r.tool_pass else (r.state_note if r.state_pass is False else r.answer_note)
        state_col = "PASS" if r.state_pass else ("FAIL" if r.state_pass is False else "-")
        print(f"{r.task_id:28} {'PASS' if r.tool_pass else 'FAIL':6} "
              f"{'PASS' if r.answer_pass else 'FAIL':6} {state_col:6} {note}")

    if reliability_summaries:
        print()
        print("-- reliability (pass^k) --")
        for task_id, (pass_k, pass_rate, k) in reliability_summaries.items():
            print(f"{task_id:28} pass^{k}: {'PASS' if pass_k else 'FAIL':6} "
                  f"(single_run_pass_rate={pass_rate:.0%})")

    single_run_results = [r for r in results if r.task_id not in reliability_summaries]
    total = len(single_run_results)
    passed = sum(1 for r in single_run_results if r.tool_pass and r.answer_pass and r.state_pass is not False)
    print(f"\n{passed}/{total} single-run tasks fully passed (tool 선택 + 최종 답변 + 상태 전부 통과)")
    if reliability_summaries:
        reliability_passed = sum(1 for pass_k, _rate, _k in reliability_summaries.values() if pass_k)
        print(f"{reliability_passed}/{len(reliability_summaries)} reliability tasks passed pass^k")


def write_report(results, report_dir, reliability_summaries=None):
    reliability_summaries = reliability_summaries or {}

    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    path = report_dir / f"{timestamp}-{uuid.uuid4().hex[:8]}.json"

    payload = {
        "results": [_serialize_result(r) for r in results],
        "reliability": {
            task_id: {"pass_k": pass_k, "pass_rate": pass_rate, "k": k}
            for task_id, (pass_k, pass_rate, k) in reliability_summaries.items()
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
