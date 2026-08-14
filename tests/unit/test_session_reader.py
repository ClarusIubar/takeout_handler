import pytest

from common.session_markdown import build_session_markdown
from common.session_reader import parse_session_markdown


def _turns():
    return [
        {"role": "user", "text": "안녕", "time_str": "2024-01-01 00:00:00"},
        {"role": "assistant", "text": "안녕하세요", "time_str": "2024-01-01 00:00:01"},
    ]


def _build(turns, **overrides):
    kwargs = dict(
        vendor_tag="chatgpt", vendor_label="ChatGPT", title="t",
        session_id="s", url="https://x", date_str="2024-01-01", turns=turns,
    )
    kwargs.update(overrides)
    return build_session_markdown(**kwargs)


def test_round_trip_frontmatter_fields():
    md, content_hash = _build(_turns(), title="제목", session_id="abc123", url="https://y", date_str="2024-02-02")
    record = parse_session_markdown(md, vendor_tag="chatgpt")

    assert record.vendor_tag == "chatgpt"
    assert record.title == "제목"
    assert record.session_id == "abc123"
    assert record.url == "https://y"
    assert record.date == "2024-02-02"
    assert record.turns_count == 2
    assert record.content_hash == content_hash
    assert record.tags == ["chatgpt", "chat-session"]


def test_round_trip_turn_fields_normal_pair():
    md, _hash = _build(_turns())
    record = parse_session_markdown(md, vendor_tag="chatgpt")

    assert len(record.turns) == 2
    t0, t1 = record.turns
    assert t0.turn_index == 0
    assert t0.role == "user"
    assert t0.parent_turn_index is None
    assert t0.has_attachment is False
    assert t0.time_str == "2024-01-01 00:00:00"
    assert t0.text == "안녕"

    assert t1.turn_index == 1
    assert t1.role == "assistant"
    assert t1.parent_turn_index == 0
    assert t1.has_attachment is False
    assert t1.text == "안녕하세요"


def test_round_trip_explicit_turns_count_overrides_len():
    md, _hash = _build(_turns(), turns_count=1)
    record = parse_session_markdown(md, vendor_tag="gemini")
    assert record.turns_count == 1
    assert len(record.turns) == 2


def test_round_trip_consecutive_user_turns_have_no_parent():
    turns = [
        {"role": "user", "text": "질문1", "time_str": "t1"},
        {"role": "user", "text": "질문2", "time_str": "t2"},
    ]
    md, _hash = _build(turns)
    record = parse_session_markdown(md, vendor_tag="chatgpt")

    assert record.turns[0].parent_turn_index is None
    assert record.turns[1].parent_turn_index is None
    assert record.turns[0].role == record.turns[1].role == "user"


def test_round_trip_multiple_assistant_turns_share_same_parent():
    turns = [
        {"role": "user", "text": "질문", "time_str": "t0"},
        {"role": "assistant", "text": "답변1", "time_str": "t1"},
        {"role": "assistant", "text": "답변2", "time_str": "t2"},
    ]
    md, _hash = _build(turns)
    record = parse_session_markdown(md, vendor_tag="chatgpt")

    assert record.turns[1].parent_turn_index == 0
    assert record.turns[2].parent_turn_index == 0


def test_round_trip_has_attachment_and_after_md_not_leaked_into_text():
    turns = [
        {"role": "user", "text": "질문", "time_str": "t", "after_md": "> 첨부파일\n\n"},
        {"role": "assistant", "text": "답변", "time_str": "t"},
    ]
    md, _hash = _build(turns)
    record = parse_session_markdown(md, vendor_tag="gemini")

    assert record.turns[0].has_attachment is True
    # after_md 블록("> 첨부파일")이 앞 turn의 콜아웃 본문 텍스트에 섞여 들어가면 안 된다.
    assert record.turns[0].text == "질문"
    assert record.turns[1].has_attachment is False


def test_round_trip_multiline_text_preserves_internal_blank_line():
    turns = [
        {"role": "user", "text": "1문단\n\n2문단", "time_str": "t"},
    ]
    md, _hash = _build(turns)
    record = parse_session_markdown(md, vendor_tag="chatgpt")

    assert record.turns[0].text == "1문단\n\n2문단"


def test_round_trip_answer_only_question_has_no_following_assistant():
    turns = [{"role": "user", "text": "답 없는 질문", "time_str": "t1"}]
    md, _hash = _build(turns)
    record = parse_session_markdown(md, vendor_tag="chatgpt")

    assert len(record.turns) == 1
    assert record.turns[0].parent_turn_index is None


def test_parse_session_markdown_raises_when_frontmatter_missing():
    with pytest.raises(ValueError, match="frontmatter"):
        parse_session_markdown("이건 그냥 본문이고 frontmatter가 없음", vendor_tag="chatgpt")


def test_parse_frontmatter_tolerates_blank_line_between_fields():
    # 실제로 build_session_markdown()은 이런 마크다운을 만들지 않지만, 사용자가 직접
    # 편집한 노트를 열었을 때 빈 줄 하나 때문에 전체 파싱이 죽으면 안 된다.
    md, content_hash = _build(_turns())
    md_with_blank_line = md.replace('turns_count: 2\n', 'turns_count: 2\n\n')
    record = parse_session_markdown(md_with_blank_line, vendor_tag="chatgpt")
    assert record.content_hash == content_hash


def test_parse_frontmatter_tags_stop_before_next_top_level_field():
    # tags 블록 뒤에 다른 필드가 더 있어도(현재 렌더러는 tags를 마지막에 두지만,
    # 순서가 바뀔 가능성에 대비) tags 리스트가 그 필드까지 삼키면 안 된다.
    md, _hash = _build(_turns())
    reordered = md.replace(
        'tags:\n  - chatgpt\n  - chat-session\n---\n\n',
        'tags:\n  - chatgpt\n  - chat-session\nextra: ignored\n---\n\n',
    )
    record = parse_session_markdown(reordered, vendor_tag="chatgpt")
    assert record.tags == ["chatgpt", "chat-session"]


def test_parse_turns_raises_when_callout_header_missing_after_comment():
    broken = (
        '---\ntitle: "t"\nsession_id: "s"\nurl: u\ndate: d\nturns_count: 1\n'
        'content_hash: abc\ntags:\n  - chatgpt\n---\n\n'
        '# t\n\n<!-- turn: {"turn_index": 0, "role": "user", '
        '"parent_turn_index": null, "has_attachment": false} -->\n'
        '이건 콜아웃 헤더가 아님\n'
    )
    with pytest.raises(ValueError, match="callout header"):
        parse_session_markdown(broken, vendor_tag="chatgpt")
