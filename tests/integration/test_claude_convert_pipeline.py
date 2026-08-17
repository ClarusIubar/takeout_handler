# vendors.claude.convert()를 단독으로(CLI를 거치지 않고) end-to-end로 검증한다.
# tests/unit/test_claude_vendor.py는 개별 헬퍼/케이스를 검증하지만, "conversations.json
# (일반 대화)과 design_chats/*.json(프로젝트 대화)이 섞인 export 하나를 넣으면 두 스키마가
# 실제로 같은 convert() 배선을 함께 타고, 프로젝트 대화만 하위 폴더로 분리되며, 재실행하면
# unchanged로 안정화된다"는 전체 배선을 검증하는 테스트는 여기가 처음이다.
import pytest

from vendors.claude import convert

pytestmark = pytest.mark.integration


def test_convert_produces_standalone_and_project_notes(tmp_path, minimal_claude_export):
    data_dir = tmp_path / "data"
    minimal_claude_export(data_dir, standalone_uuid="conv-solo", project_uuid="chat-proj",
                           project_name="Jamissue")
    result_dir = tmp_path / "result"

    stats = convert(data_dir, result_dir, dry_run=False)

    assert stats.sessions_found == 2
    assert stats.files_created == 2
    assert stats.parse_errors == 0

    standalone_path = result_dir / "conv-solo.md"
    project_path = result_dir / "Jamissue" / "chat-proj.md"
    assert standalone_path.exists()
    assert project_path.exists()

    standalone_text = standalone_path.read_text(encoding="utf-8")
    assert 'session_id: "conv-solo"' in standalone_text
    assert "tags:" in standalone_text and "- claude" in standalone_text
    assert "> [!question]- User" in standalone_text
    assert "> [!tip]- Claude" in standalone_text
    assert "질문입니다" in standalone_text
    assert "답변입니다" in standalone_text

    project_text = project_path.read_text(encoding="utf-8")
    assert 'session_id: "chat-proj"' in project_text
    assert "저장소를 확인해줘" in project_text
    assert "확인했습니다" in project_text
    assert "github_list_repos" in project_text


def test_convert_is_idempotent_on_rerun(tmp_path, minimal_claude_export):
    data_dir = tmp_path / "data"
    minimal_claude_export(data_dir)
    result_dir = tmp_path / "result"

    first = convert(data_dir, result_dir, dry_run=False)
    assert first.files_created == 2

    second = convert(data_dir, result_dir, dry_run=False)

    assert second.files_created == 0
    assert second.files_updated == 0
    assert second.files_unchanged == 2


def test_convert_dry_run_creates_no_files(tmp_path, minimal_claude_export):
    data_dir = tmp_path / "data"
    minimal_claude_export(data_dir)
    result_dir = tmp_path / "result"

    stats = convert(data_dir, result_dir, dry_run=True)

    assert stats.sessions_found == 2
    assert stats.files_created == 2
    assert not result_dir.exists()
