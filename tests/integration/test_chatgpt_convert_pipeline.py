# vendors.chatgpt.convert()를 단독으로(CLI를 거치지 않고) end-to-end로 검증한다.
# tests/unit/test_chatgpt_vendor.py는 _active_branch_nodes 같은 private 헬퍼를 개별
# 검증하지만, "conversations.json 하나를 넣으면 실제로 올바른 .md 한 개가 나오고,
# 다시 돌리면 unchanged로 안정화된다"는 배선 전체를 검증하는 테스트는 여기가 처음이다.
import pytest

from vendors.chatgpt import convert

pytestmark = pytest.mark.integration


def test_convert_produces_one_valid_session_note(tmp_path, minimal_chatgpt_export):
    data_dir = tmp_path / "data"
    minimal_chatgpt_export(data_dir, conversation_id="conv-1")
    result_dir = tmp_path / "result"

    stats = convert(data_dir, result_dir, dry_run=False)

    assert stats.sessions_found == 1
    assert stats.files_created == 1
    assert stats.parse_errors == 0

    md_files = list(result_dir.glob("*.md"))
    assert len(md_files) == 1
    assert md_files[0].name == "conv-1.md"

    text = md_files[0].read_text(encoding="utf-8")
    # frontmatter
    assert 'session_id: "conv-1"' in text
    assert "url: https://chatgpt.com/c/conv-1" in text
    assert "tags:" in text and "- chatgpt" in text
    assert "content_hash:" in text
    # turn 메타데이터 HTML 주석 + callout 둘 다 실제로 나왔는지
    assert '"turn_index": 0, "role": "user", "parent_turn_index": null' in text
    assert '"turn_index": 1, "role": "assistant", "parent_turn_index": 0' in text
    assert "> [!question]- User" in text
    assert "> [!tip]- ChatGPT" in text
    assert "Hello" in text
    assert "Hi there" in text


def test_convert_is_idempotent_on_rerun(tmp_path, minimal_chatgpt_export):
    data_dir = tmp_path / "data"
    minimal_chatgpt_export(data_dir, conversation_id="conv-1")
    result_dir = tmp_path / "result"

    first = convert(data_dir, result_dir, dry_run=False)
    assert first.files_created == 1

    second = convert(data_dir, result_dir, dry_run=False)

    assert second.files_created == 0
    assert second.files_updated == 0
    assert second.files_unchanged == 1
