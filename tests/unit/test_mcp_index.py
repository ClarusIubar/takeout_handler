from common.session_markdown import build_session_markdown
from mcp_server.index import SessionIndex


def _write_session(dir_path, vendor, session_id, title, date_str, turns, filename=None):
    dir_path.mkdir(parents=True, exist_ok=True)
    md, _hash = build_session_markdown(
        vendor_tag=vendor, vendor_label=vendor, title=title,
        session_id=session_id, url="https://x", date_str=date_str, turns=turns,
    )
    path = dir_path / (filename or f"{session_id}.md")
    path.write_text(md, encoding="utf-8")
    return path


def _turns(user_text="질문", assistant_text="답변"):
    return [
        {"role": "user", "text": user_text, "time_str": "t0"},
        {"role": "assistant", "text": assistant_text, "time_str": "t1"},
    ]


def test_rebuild_finds_sessions_across_vendor_subdirs(tmp_path):
    _write_session(tmp_path / "chatgpt", "chatgpt", "s1", "첫 대화", "2024-01-01", _turns())
    _write_session(tmp_path / "gemini", "gemini", "s2", "두 번째 대화", "2024-01-02", _turns())

    index = SessionIndex()
    index.rebuild(tmp_path)

    all_sessions = index.list_sessions()
    assert {s.session_id for s in all_sessions} == {"s1", "s2"}


def test_rebuild_on_missing_root_yields_empty_index(tmp_path):
    index = SessionIndex()
    index.rebuild(tmp_path / "does-not-exist")
    assert index.list_sessions() == []


def test_list_sessions_filters_by_vendor(tmp_path):
    _write_session(tmp_path / "chatgpt", "chatgpt", "s1", "a", "2024-01-01", _turns())
    _write_session(tmp_path / "gemini", "gemini", "s2", "b", "2024-01-02", _turns())

    index = SessionIndex()
    index.rebuild(tmp_path)

    chatgpt_only = index.list_sessions(vendor="chatgpt")
    assert [s.session_id for s in chatgpt_only] == ["s1"]


def test_list_sessions_sorted_newest_first_and_respects_limit_offset(tmp_path):
    _write_session(tmp_path / "chatgpt", "chatgpt", "old", "old", "2024-01-01", _turns())
    _write_session(tmp_path / "chatgpt", "chatgpt", "new", "new", "2024-06-01", _turns())
    _write_session(tmp_path / "chatgpt", "chatgpt", "mid", "mid", "2024-03-01", _turns())

    index = SessionIndex()
    index.rebuild(tmp_path)

    ordered = index.list_sessions()
    assert [s.session_id for s in ordered] == ["new", "mid", "old"]

    page = index.list_sessions(limit=1, offset=1)
    assert [s.session_id for s in page] == ["mid"]


def test_search_sessions_matches_title(tmp_path):
    _write_session(tmp_path / "chatgpt", "chatgpt", "s1", "파이썬 공부", "2024-01-01", _turns())
    _write_session(tmp_path / "chatgpt", "chatgpt", "s2", "다른 주제", "2024-01-02", _turns())

    index = SessionIndex()
    index.rebuild(tmp_path)

    results = index.search_sessions("파이썬")
    assert [s.session_id for s, _snippet in results] == ["s1"]


def test_search_sessions_matches_turn_text_case_insensitive(tmp_path):
    _write_session(
        tmp_path / "chatgpt", "chatgpt", "s1", "제목", "2024-01-01",
        _turns(user_text="MCP 서버가 뭐야?", assistant_text="Model Context Protocol입니다"),
    )

    index = SessionIndex()
    index.rebuild(tmp_path)

    results = index.search_sessions("model context protocol")
    assert [s.session_id for s, _snippet in results] == ["s1"]


def test_search_sessions_filters_by_date_range(tmp_path):
    _write_session(tmp_path / "chatgpt", "chatgpt", "old", "찾는말", "2024-01-01", _turns())
    _write_session(tmp_path / "chatgpt", "chatgpt", "new", "찾는말", "2024-06-01", _turns())

    index = SessionIndex()
    index.rebuild(tmp_path)

    results = index.search_sessions("찾는말", date_from="2024-03-01")
    assert [s.session_id for s, _snippet in results] == ["new"]


def test_get_session_returns_full_record_with_turns(tmp_path):
    _write_session(tmp_path / "chatgpt", "chatgpt", "s1", "제목", "2024-01-01", _turns())

    index = SessionIndex()
    index.rebuild(tmp_path)

    record = index.get_session("chatgpt", "s1")
    assert record is not None
    assert record.title == "제목"
    assert len(record.turns) == 2


def test_get_session_returns_none_when_not_found(tmp_path):
    index = SessionIndex()
    index.rebuild(tmp_path)
    assert index.get_session("chatgpt", "missing") is None


def test_rebuild_with_explicit_vendor_list_ignores_other_dirs(tmp_path):
    _write_session(tmp_path / "chatgpt", "chatgpt", "s1", "a", "2024-01-01", _turns())
    _write_session(tmp_path / "gemini", "gemini", "s2", "b", "2024-01-02", _turns())

    index = SessionIndex()
    index.rebuild(tmp_path, vendors=["chatgpt"])

    assert [s.session_id for s in index.list_sessions()] == ["s1"]


def test_rebuild_with_explicit_vendor_list_skips_nonexistent_vendor_dir(tmp_path):
    _write_session(tmp_path / "chatgpt", "chatgpt", "s1", "a", "2024-01-01", _turns())

    index = SessionIndex()
    # "gemini" 디렉터리가 실제로 없어도(아직 sync 안 함 등) 죽지 않고 조용히 건너뜀.
    index.rebuild(tmp_path, vendors=["chatgpt", "gemini"])

    assert [s.session_id for s in index.list_sessions()] == ["s1"]


def test_list_sessions_vendor_filter_is_case_insensitive(tmp_path):
    _write_session(tmp_path / "gemini", "gemini", "s1", "a", "2024-01-01", _turns())

    index = SessionIndex()
    index.rebuild(tmp_path)

    assert [s.session_id for s in index.list_sessions(vendor="Gemini")] == ["s1"]


def test_search_sessions_vendor_filter_is_case_insensitive(tmp_path):
    _write_session(tmp_path / "gemini", "gemini", "s1", "찾는말", "2024-01-01", _turns())

    index = SessionIndex()
    index.rebuild(tmp_path)

    results = index.search_sessions("찾는말", vendor="GEMINI")
    assert [s.session_id for s, _snippet in results] == ["s1"]


def test_get_session_vendor_is_case_insensitive(tmp_path):
    _write_session(tmp_path / "chatgpt", "chatgpt", "s1", "제목", "2024-01-01", _turns())

    index = SessionIndex()
    index.rebuild(tmp_path)

    record = index.get_session("ChatGPT", "s1")
    assert record is not None
    assert record.session_id == "s1"


def test_search_sessions_vendor_filter_excludes_other_vendors(tmp_path):
    _write_session(tmp_path / "chatgpt", "chatgpt", "s1", "찾는말", "2024-01-01", _turns())
    _write_session(tmp_path / "gemini", "gemini", "s2", "찾는말", "2024-01-02", _turns())

    index = SessionIndex()
    index.rebuild(tmp_path)

    results = index.search_sessions("찾는말", vendor="chatgpt")
    assert [s.session_id for s, _snippet in results] == ["s1"]


def test_search_sessions_date_to_excludes_sessions_after_range(tmp_path):
    _write_session(tmp_path / "chatgpt", "chatgpt", "old", "찾는말", "2024-01-01", _turns())
    _write_session(tmp_path / "chatgpt", "chatgpt", "new", "찾는말", "2024-06-01", _turns())

    index = SessionIndex()
    index.rebuild(tmp_path)

    results = index.search_sessions("찾는말", date_to="2024-03-01")
    assert [s.session_id for s, _snippet in results] == ["old"]


def test_search_sessions_stops_early_once_limit_reached(tmp_path):
    # 제목이 아니라 turn 텍스트로 매치시켜야 한다 — 제목 매치는 continue로 곧장
    # 다음 세션으로 넘어가서 limit 체크(및 break)를 아예 안 거치기 때문.
    for i in range(5):
        _write_session(
            tmp_path / "chatgpt", "chatgpt", f"s{i}", "제목", f"2024-01-0{i + 1}",
            _turns(user_text="찾는말이 turn 텍스트에 있음"),
        )

    index = SessionIndex()
    index.rebuild(tmp_path)

    results = index.search_sessions("찾는말", limit=2)
    assert len(results) == 2


def test_rebuild_skips_files_that_fail_to_parse(tmp_path):
    vendor_dir = tmp_path / "chatgpt"
    vendor_dir.mkdir(parents=True)
    (vendor_dir / "broken.md").write_text("이건 세션 마크다운이 아님", encoding="utf-8")
    _write_session(vendor_dir, "chatgpt", "ok", "정상", "2024-01-01", _turns())

    index = SessionIndex()
    index.rebuild(tmp_path)

    assert [s.session_id for s in index.list_sessions()] == ["ok"]
