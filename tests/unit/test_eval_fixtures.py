import json

from eval.fixtures import build_fixture_raw_chatgpt_data_dir, build_fixture_result_dir


def test_build_fixture_result_dir_writes_all_sessions(tmp_path):
    result_dir, facts = build_fixture_result_dir(tmp_path)

    chatgpt_ids = {p.stem for p in (result_dir / "chatgpt").glob("*.md")}
    gemini_ids = {p.stem for p in (result_dir / "gemini").glob("*.md")}

    assert chatgpt_ids == {"mcp-arch-1", "asyncio-1", "resume-fb-1", "move-checklist-1", "career-chat-1"}
    assert gemini_ids == {
        "kyoto-trip-1", "osaka-trip-1", "kimchi-recipe-1", "weekend-plan-1", "travel-savings-1",
    }


def test_facts_point_at_the_right_sessions(tmp_path):
    _result_dir, facts = build_fixture_result_dir(tmp_path)

    assert facts["newest_session_id"] == "mcp-arch-1"
    assert facts["asyncio_session"] == ("chatgpt", "asyncio-1")
    assert facts["resume_session"] == ("chatgpt", "resume-fb-1")
    assert facts["kyoto_session"] == ("gemini", "kyoto-trip-1")
    assert facts["osaka_session"] == ("gemini", "osaka-trip-1")
    assert facts["kimchi_session"] == ("gemini", "kimchi-recipe-1")


def test_build_fixture_result_dir_includes_decoy_sessions(tmp_path):
    result_dir, _facts = build_fixture_result_dir(tmp_path)

    chatgpt_ids = {p.stem for p in (result_dir / "chatgpt").glob("*.md")}
    gemini_ids = {p.stem for p in (result_dir / "gemini").glob("*.md")}

    assert "career-chat-1" in chatgpt_ids
    assert "weekend-plan-1" in gemini_ids
    assert "travel-savings-1" in gemini_ids


def test_decoy_sessions_contain_keyword_substring_but_are_off_topic(tmp_path):
    # search_sessions는 단순 substring 매치라 이 세션들도 결과에 걸려야 한다 — 모델이
    # 내용을 읽고 걸러내는지를 검증하려는 게 목적이라, 걸리는 것 자체는 의도된 동작.
    result_dir, _facts = build_fixture_result_dir(tmp_path)

    def _text(vendor, session_id):
        return (result_dir / vendor / f"{session_id}.md").read_text(encoding="utf-8")

    assert "asyncio" in _text("chatgpt", "career-chat-1")
    assert "요리" in _text("gemini", "weekend-plan-1")
    assert "여행" in _text("gemini", "travel-savings-1")


def test_travel_savings_decoy_dated_within_july_2026(tmp_path):
    # date_ranged_search 태스크의 "2026년 7월" 필터에도 걸리게 해서, 날짜만으론
    # 걸러지지 않고 내용을 읽어야만 제외할 수 있게 한다.
    result_dir, _facts = build_fixture_result_dir(tmp_path)
    text = (result_dir / "gemini" / "travel-savings-1.md").read_text(encoding="utf-8")
    assert "date: 2026-07" in text


def test_search_relevant_keywords_appear_literally_in_turn_text(tmp_path):
    # search_sessions는 단순 substring 매치라, 구별 키워드가 turn 텍스트에 실제로
    # 있어야 eval 태스크가 의미를 가진다.
    result_dir, _facts = build_fixture_result_dir(tmp_path)

    def _text(vendor, session_id):
        return (result_dir / vendor / f"{session_id}.md").read_text(encoding="utf-8")

    assert "asyncio" in _text("chatgpt", "asyncio-1")
    assert "김치찌개" in _text("gemini", "kimchi-recipe-1")
    assert "요리" in _text("gemini", "kimchi-recipe-1")
    assert "오사카" in _text("gemini", "osaka-trip-1")
    assert "교토" in _text("gemini", "kyoto-trip-1")
    # osaka 세션 본문에 kyoto의 구별 문구가 새어 들어가면 태스크 6(구분 테스트)이 무의미해짐
    assert "3박4일" not in _text("gemini", "osaka-trip-1")


def test_dates_match_planned_ranges(tmp_path):
    result_dir, _facts = build_fixture_result_dir(tmp_path)

    def _text(vendor, session_id):
        return (result_dir / vendor / f"{session_id}.md").read_text(encoding="utf-8")

    assert "date: 2026-08-01" in _text("chatgpt", "mcp-arch-1")
    assert "date: 2026-07-20" in _text("gemini", "kyoto-trip-1")
    assert "date: 2026-07-22" in _text("gemini", "osaka-trip-1")


def test_build_fixture_raw_chatgpt_data_dir_writes_valid_conversations_json(tmp_path):
    raw_dir = build_fixture_raw_chatgpt_data_dir(tmp_path)

    payload = json.loads((raw_dir / "conversations.json").read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    assert payload[0]["id"] == "eval-sync-new-1"


def test_build_fixture_raw_chatgpt_data_dir_id_does_not_collide_with_committed_fixtures(tmp_path):
    # facts의 값은 ("vendor", "session_id") 튜플이거나("mcp_arch_session" 등), 그냥
    # 문자열("newest_session_id", "nonexistent_topic")이다 — 튜플인 것만 걸러서
    # session_id(두 번째 요소)를 모은다.
    committed_result_dir = tmp_path / "committed"
    _result_dir, facts = build_fixture_result_dir(committed_result_dir)
    committed_ids = {value[1] for value in facts.values() if isinstance(value, tuple)}

    raw_dir = build_fixture_raw_chatgpt_data_dir(tmp_path / "raw")
    payload = json.loads((raw_dir / "conversations.json").read_text(encoding="utf-8"))

    assert payload[0]["id"] not in committed_ids


def test_raw_chatgpt_data_dir_is_convertible_by_vendors_chatgpt(tmp_path):
    from vendors import chatgpt as chatgpt_vendor

    raw_dir = build_fixture_raw_chatgpt_data_dir(tmp_path / "raw")
    result_dir = tmp_path / "result"

    assert chatgpt_vendor.detect(raw_dir) is True
    stats = chatgpt_vendor.convert(raw_dir, result_dir, dry_run=False)

    assert stats.sessions_found == 1
    assert (result_dir / "eval-sync-new-1.md").exists()
