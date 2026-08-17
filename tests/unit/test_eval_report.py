import json

from eval.report import TaskResult, print_summary, write_report
from eval.tasks import ToolCallRecord


def _result(task_id, tool_pass=True, answer_pass=True, state_pass=None):
    calls = [ToolCallRecord(name="list_sessions", arguments={}, structured_content={"result": []})]
    return TaskResult(
        task_id=task_id, prompt=f"prompt for {task_id}",
        tool_pass=tool_pass, tool_note="ok" if tool_pass else "tool 틀림",
        answer_pass=answer_pass, answer_note="ok" if answer_pass else "답 틀림",
        executed_calls=calls, final_answer="최종 답변 텍스트",
        state_pass=state_pass, state_note=("ok" if state_pass else "상태 틀림") if state_pass is not None else None,
    )


def test_print_summary_lists_every_task_and_totals(capsys):
    results = [_result("a", True, True), _result("b", False, True)]
    print_summary(results)
    out = capsys.readouterr().out
    assert "a" in out
    assert "b" in out
    assert "1/2" in out


def test_write_report_creates_json_file_with_full_detail(tmp_path):
    results = [_result("basic_listing", True, True)]
    path = write_report(results, tmp_path)

    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["results"][0]["task_id"] == "basic_listing"
    assert payload["results"][0]["tool_pass"] is True
    assert payload["results"][0]["executed_calls"][0]["name"] == "list_sessions"
    assert payload["results"][0]["final_answer"] == "최종 답변 텍스트"
    assert payload["reliability"] == {}


def test_write_report_creates_report_dir_if_missing(tmp_path):
    nested = tmp_path / "nested" / "results"
    path = write_report([_result("t")], nested)
    assert path.exists()
    assert path.parent == nested


def test_write_report_filenames_are_unique_across_calls(tmp_path):
    path1 = write_report([_result("t")], tmp_path)
    path2 = write_report([_result("t")], tmp_path)
    assert path1 != path2


def test_result_with_state_check_serialized_in_report(tmp_path):
    path = write_report([_result("sync_takeout_legitimate_refresh", state_pass=True)], tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["results"][0]["state_pass"] is True
    assert payload["results"][0]["state_note"] == "ok"


def test_result_without_state_check_serializes_state_pass_as_null(tmp_path):
    path = write_report([_result("basic_listing")], tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["results"][0]["state_pass"] is None


def test_print_summary_shows_state_failure_note(capsys):
    results = [_result("sync_takeout_legitimate_refresh", tool_pass=True, answer_pass=True, state_pass=False)]
    print_summary(results)
    out = capsys.readouterr().out
    assert "상태 틀림" in out


def test_print_summary_reports_reliability_pass_k_and_rate(capsys):
    results = [_result("ambiguous_disambiguation")] * 3
    print_summary(results, reliability_summaries={"ambiguous_disambiguation": (False, 2 / 3, 3)})
    out = capsys.readouterr().out
    assert "ambiguous_disambiguation" in out
    assert "pass^3" in out
    assert "FAIL" in out


def test_write_report_includes_reliability_summary_section(tmp_path):
    results = [_result("ambiguous_disambiguation")] * 3
    path = write_report(
        results, tmp_path, reliability_summaries={"ambiguous_disambiguation": (True, 1.0, 3)},
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    assert payload["reliability"]["ambiguous_disambiguation"] == {"pass_k": True, "pass_rate": 1.0, "k": 3}
    assert len(payload["results"]) == 3
