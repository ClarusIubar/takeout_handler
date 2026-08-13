from common.session_markdown import build_session_markdown, extract_content_hash


def _turns():
    return [
        {"role": "user", "text": "안녕", "time_str": "2024-01-01 00:00:00"},
        {"role": "assistant", "text": "안녕하세요", "time_str": "2024-01-01 00:00:01"},
    ]


def test_build_session_markdown_default_turns_count():
    md, content_hash = build_session_markdown(
        vendor_tag="chatgpt", vendor_label="ChatGPT", title="테스트",
        session_id="abc", url="https://x", date_str="2024-01-01", turns=_turns(),
    )
    assert 'turns_count: 2' in md
    assert '- chatgpt' in md
    assert '> [!question]- User (2024-01-01 00:00:00)' in md
    assert '> [!tip]- ChatGPT (2024-01-01 00:00:01)' in md
    assert f'content_hash: {content_hash}' in md


def test_build_session_markdown_explicit_turns_count_overrides_len():
    # Gemini는 질문+응답 쌍 하나 = turns 리스트에는 2개 항목(user+assistant)이지만
    # frontmatter의 turns_count는 '쌍' 기준 1이어야 한다.
    md, _hash = build_session_markdown(
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
    md, _hash = build_session_markdown(
        vendor_tag="gemini", vendor_label="Gemini", title="t",
        session_id="s", url="u", date_str="d", turns=turns,
    )
    question_idx = md.index("[!question]")
    attachment_idx = md.index("> 첨부파일")
    tip_idx = md.index("[!tip]")
    assert question_idx < attachment_idx < tip_idx


def _build(turns, **overrides):
    kwargs = dict(
        vendor_tag="chatgpt", vendor_label="ChatGPT", title="t",
        session_id="s", url="u", date_str="d", turns=turns,
    )
    kwargs.update(overrides)
    return build_session_markdown(**kwargs)


def test_content_hash_stable_for_identical_input():
    _md1, hash1 = _build(_turns())
    _md2, hash2 = _build(_turns())
    assert hash1 == hash2


def test_content_hash_changes_when_a_turn_is_added():
    # upsert 판단의 핵심: 같은 session_id라도 나중에 대화가 더 늘어나면(같은 turns
    # 리스트에 항목이 추가되면) 본문 해시가 달라져야 "갱신" 대상으로 잡을 수 있다.
    _md1, hash1 = _build(_turns())
    extra_turns = _turns() + [{"role": "user", "text": "추가 질문", "time_str": "t2"}]
    _md2, hash2 = _build(extra_turns)
    assert hash1 != hash2


def test_content_hash_changes_when_title_changes():
    _md1, hash1 = _build(_turns(), title="제목1")
    _md2, hash2 = _build(_turns(), title="제목2")
    assert hash1 != hash2


def test_content_hash_unaffected_by_frontmatter_only_fields():
    # date_str/url/session_id는 본문에 안 들어가므로 본문 해시에 영향이 없어야 한다
    # (본문만 해시하는 설계 — frontmatter 필드는 전부 같은 소스에서 파생되므로 무관).
    _md1, hash1 = _build(_turns(), date_str="2024-01-01", url="https://a", session_id="x")
    _md2, hash2 = _build(_turns(), date_str="1999-12-31", url="https://b", session_id="y")
    assert hash1 == hash2


def test_extract_content_hash_reads_value_back():
    md, content_hash = _build(_turns())
    assert extract_content_hash(md) == content_hash


def test_extract_content_hash_missing_field_returns_none():
    assert extract_content_hash("---\ntitle: x\n---\nbody") is None
