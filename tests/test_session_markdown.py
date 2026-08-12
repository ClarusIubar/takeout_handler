from common.session_markdown import build_session_markdown


def _turns():
    return [
        {"role": "user", "text": "안녕", "time_str": "2024-01-01 00:00:00"},
        {"role": "assistant", "text": "안녕하세요", "time_str": "2024-01-01 00:00:01"},
    ]


def test_build_session_markdown_default_turns_count():
    md = build_session_markdown(
        vendor_tag="chatgpt", vendor_label="ChatGPT", title="테스트",
        session_id="abc", url="https://x", date_str="2024-01-01", turns=_turns(),
    )
    assert 'turns_count: 2' in md
    assert '- chatgpt' in md
    assert '> [!question]- User (2024-01-01 00:00:00)' in md
    assert '> [!tip]- ChatGPT (2024-01-01 00:00:01)' in md


def test_build_session_markdown_explicit_turns_count_overrides_len():
    # Gemini는 질문+응답 쌍 하나 = turns 리스트에는 2개 항목(user+assistant)이지만
    # frontmatter의 turns_count는 '쌍' 기준 1이어야 한다.
    md = build_session_markdown(
        vendor_tag="gemini", vendor_label="Gemini", title="테스트",
        session_id="abc", url="https://x", date_str="2024-01-01", turns=_turns(),
        turns_count=1,
    )
    assert 'turns_count: 1' in md


def test_build_session_markdown_after_md_inserted_after_callout():
    turns = [
        {"role": "user", "text": "질문", "time_str": "t", "after_md": "> 첨부파일\n\n"},
        {"role": "assistant", "text": "답변", "time_str": "t"},
    ]
    md = build_session_markdown(
        vendor_tag="gemini", vendor_label="Gemini", title="t",
        session_id="s", url="u", date_str="d", turns=turns,
    )
    question_idx = md.index("[!question]")
    attachment_idx = md.index("> 첨부파일")
    tip_idx = md.index("[!tip]")
    assert question_idx < attachment_idx < tip_idx
