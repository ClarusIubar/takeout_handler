# eval/README.md의 태스크 목록이 eval/tasks.py::TASKS와 어긋나지 않는지 확인한다 —
# 문서가 코드보다 뒤처지는 걸 자동으로 잡기 위함(TSK-002-12).
import re
from pathlib import Path

from eval.tasks import TASKS

_README_PATH = Path(__file__).resolve().parent.parent.parent / "eval" / "README.md"
_TASK_ID_RE = re.compile(r'\*\*([a-z][a-z0-9_]*)\*\*')


def _task_ids_mentioned_in_readme():
    text = _README_PATH.read_text(encoding="utf-8")
    section = text.split("## 태스크")[1].split("## 범위 밖")[0]
    return set(_TASK_ID_RE.findall(section))


def test_readme_task_section_lists_every_task_id():
    documented = _task_ids_mentioned_in_readme()
    actual = {t.id for t in TASKS}
    missing = actual - documented
    assert not missing, f"README 태스크 표에 빠진 태스크: {missing}"


def test_readme_task_section_does_not_mention_stale_ids():
    documented = _task_ids_mentioned_in_readme()
    actual = {t.id for t in TASKS}
    stale = documented - actual
    assert not stale, f"README에 있지만 실제로는 없는 태스크: {stale}"


def test_readme_mentions_current_task_count():
    text = _README_PATH.read_text(encoding="utf-8")
    assert f"{len(TASKS)}개" in text


def test_readme_does_not_claim_no_repeated_run_statistics():
    # pass^k를 도입한 뒤로는 "재시도/여러 번 실행한 분산 통계 없음"이라는 옛 범위-밖
    # 문구가 남아있으면 안 된다(TSK-002-11에서 이미 틀린 서술이 됨).
    text = _README_PATH.read_text(encoding="utf-8")
    assert "재시도/여러 번 실행한 분산 통계 없음" not in text


def test_readme_has_limitations_section():
    text = _README_PATH.read_text(encoding="utf-8")
    assert "## 한계" in text
    for keyword in ["모델 일반화", "pass^k", "decoy", "시스템 프롬프트", "프롬프트 인젝션"]:
        assert keyword in text, f"한계 섹션에 '{keyword}' 관련 내용이 없음"
