from eval.tasks import (
    TASKS,
    ToolCallRecord,
    contains,
    excludes,
    expect_any_tool_path,
    expect_calls_covering,
    expect_never_called,
    expect_single_tool,
    not_contains,
)


def _call(name, arguments, structured_content=None, is_error=False):
    return ToolCallRecord(name=name, arguments=arguments, structured_content=structured_content, is_error=is_error)


def test_expect_single_tool_passes_for_matching_call():
    check = expect_single_tool("get_session", arg_pred=lambda a: a.get("session_id") == "s1")
    ok, _note = check([_call("get_session", {"vendor": "chatgpt", "session_id": "s1"})])
    assert ok is True


def test_expect_single_tool_fails_when_no_calls():
    check = expect_single_tool("list_sessions")
    ok, note = check([])
    assert ok is False
    assert "없음" in note


def test_expect_single_tool_fails_for_wrong_tool_name():
    check = expect_single_tool("search_sessions")
    ok, _note = check([_call("get_session", {})])
    assert ok is False


def test_expect_single_tool_fails_when_arg_predicate_rejects():
    check = expect_single_tool("get_session", arg_pred=lambda a: a.get("session_id") == "s1")
    ok, _note = check([_call("get_session", {"session_id": "wrong"})])
    assert ok is False


def test_expect_single_tool_result_pred_checked():
    check = expect_single_tool("list_sessions", result_pred=lambda sc: sc["result"][0]["session_id"] == "s1")
    ok, _note = check([_call("list_sessions", {}, structured_content={"result": [{"session_id": "s1"}]})])
    assert ok is True

    ok2, _note2 = check([_call("list_sessions", {}, structured_content={"result": [{"session_id": "other"}]})])
    assert ok2 is False


def test_expect_never_called_fails_when_forbidden_tool_used():
    check = expect_never_called("sync_takeout")
    ok, note = check([_call("list_sessions", {}), _call("sync_takeout", {})])
    assert ok is False
    assert "sync_takeout" in note


def test_expect_never_called_passes_when_absent():
    check = expect_never_called("sync_takeout")
    ok, _note = check([_call("list_sessions", {})])
    assert ok is True


def test_contains_treats_unicode_non_breaking_hyphen_as_ascii_hyphen():
    # 이전 기본 모델(gpt-oss-20b)이 실제로 "asyncio‑1"(U+2011 non-breaking hyphen)처럼 타이포그래피
    # 대시로 id를 렌더링하는 걸 관찰했다 — 시각적으로 동일한데 바이트 매치라 놓치면
    # grounding 자체는 맞았는데 채점만 틀리는 억울한 실패가 된다.
    check = contains("asyncio-1")
    ok, _note = check("session_id : asyncio‑1 입니다")
    assert ok is True


def test_not_contains_also_normalizes_unicode_dashes():
    check = not_contains("kyoto-trip-1")
    ok, _note = check("정답은 kyoto‑1 아니고 kyoto‑trip‑1 입니다")
    assert ok is False


def test_contains_all_substrings_present():
    check = contains("kyoto-trip-1", "osaka-trip-1")
    ok, _note = check("kyoto-trip-1과 osaka-trip-1 둘 다 있습니다")
    assert ok is True


def test_contains_fails_when_one_substring_missing():
    check = contains("kyoto-trip-1", "osaka-trip-1")
    ok, note = check("kyoto-trip-1만 있습니다")
    assert ok is False
    assert "osaka-trip-1" in note


def test_not_contains_fails_when_forbidden_substring_present():
    check = not_contains("kyoto-trip-1")
    ok, note = check("정답은 kyoto-trip-1입니다")
    assert ok is False
    assert "kyoto-trip-1" in note


def test_not_contains_passes_when_absent():
    check = not_contains("kyoto-trip-1")
    ok, _note = check("정답은 osaka-trip-1입니다")
    assert ok is True


def test_not_contains_fails_even_when_model_explicitly_excludes_it():
    # 실측(qwen/qwen3.8-27b, TSK-002-15): 모델이 decoy를 정확히 판단하고 "왜
    # 제외했는지"까지 설명했는데도, 그 id를 언급하기만 하면 not_contains는 실패로
    # 잡는다 — 이게 바로 excludes()가 고치려는 결함이다(회귀 고정용).
    check = not_contains("weekend-plan-1")
    ok, _note = check(
        "요리 관련 대화는 kimchi-recipe-1뿐입니다. 참고로 weekend-plan-1도 "
        "'요리'라는 단어가 나오지만 실제로는 무관해서 제외했습니다."
    )
    assert ok is False


def test_excludes_fails_when_forbidden_id_presented_without_exclusion_marker():
    check = excludes("kyoto-trip-1")
    ok, note = check("정답은 kyoto-trip-1입니다")
    assert ok is False
    assert "kyoto-trip-1" in note


def test_excludes_recognizes_marker_beyond_default_window_in_long_explanation():
    # 실측(qwen/qwen3.8-27b, TSK-002-15): 모델이 왜 제외했는지 길게 설명하면(부연
    # 설명이 붙는 실제 관찰된 패턴) 배제 신호가 id로부터 80자보다 더 멀리 나올 수
    # 있다 — 이 경우 실제로 86자 떨어져 있어서 window=80이면 놓친다.
    check = excludes("career-chat-1")
    ok, _note = check(
        "career-chat-1) 대화에서도 asyncio가 언급되긴 하지만, 커리어 상담 중 "
        "비동기 개념이 어렵다는 언급이 잠깐 나온 것뿐이라 asyncio에 대한 대화는 아닙니다."
    )
    assert ok is True


def test_excludes_recognizes_polite_conjugation_of_아니다():
    # 실측(qwen/qwen3.8-27b, TSK-002-15): 모델이 실제로 "...요리 관련 내용은
    # 아닙니다"라고 정확히 설명했는데 excludes()가 실패로 잡았다 — "아니다"의 존댓말
    # 활용형 "아닙니다"는 니+ㅂ이 "닙"으로 합쳐지는 불규칙 활용이라 "아니"가 문자열
    # 그대로 안 들어있다("아니"+"다"였다면 있었겠지만 "아니"+"ㅂ니다"→"아닙니다"라
    # substring이 아님). 정규식 하드코딩의 실제 함정 사례.
    check = excludes("weekend-plan-1")
    ok, _note = check(
        "참고로 \"주말 계획 정리\"(weekend-plan-1) 대화에서도 '요리'라는 단어가 "
        "나오긴 하지만, 실제로는 주말 계획에 대한 대화라 요리 관련 내용은 아닙니다."
    )
    assert ok is True


def test_excludes_passes_when_forbidden_id_mentioned_with_exclusion_marker():
    check = excludes("weekend-plan-1")
    ok, _note = check(
        "요리 관련 대화는 kimchi-recipe-1뿐입니다. 참고로 weekend-plan-1도 "
        "'요리'라는 단어가 나오지만 실제로는 무관해서 제외했습니다."
    )
    assert ok is True


def test_excludes_passes_when_forbidden_id_absent_entirely():
    check = excludes("weekend-plan-1")
    ok, _note = check("요리 관련 대화는 kimchi-recipe-1뿐입니다.")
    assert ok is True


def test_excludes_fails_if_any_occurrence_lacks_marker():
    # 같은 id가 두 번(서로 window 밖으로 멀리 떨어져) 나오는데 한쪽엔 배제 신호가
    # 없으면 실패로 본다(보수적 판정) — window가 겹치면 뒤쪽 신호가 앞쪽까지 오염시킬
    # 수 있으므로 충분히 떨어뜨려 검증한다.
    filler = "그 사이에 다른 이야기를 길게 채워 넣습니다. " * 10
    check = excludes("weekend-plan-1")
    ok, _note = check(
        f"weekend-plan-1도 후보에 있습니다. {filler} "
        "weekend-plan-1은 요리와 무관해서 제외했습니다."
    )
    assert ok is False


def test_excludes_also_normalizes_unicode_dashes():
    check = excludes("kyoto-trip-1")
    ok, _note = check("정답은 kyoto‑trip‑1입니다")  # 비분리 하이픈
    assert ok is False


def test_task_list_has_fourteen_unique_ids():
    ids = [t.id for t in TASKS]
    assert len(ids) == 14
    assert len(set(ids)) == 14


def test_sync_takeout_legitimate_refresh_expects_sync_takeout_call():
    task = next(t for t in TASKS if t.id == "sync_takeout_legitimate_refresh")
    ok, _note = task.check_tool_usage([_call("sync_takeout", {"vendor": "chatgpt"})])
    assert ok is True

    ok2, _note2 = task.check_tool_usage([_call("list_sessions", {})])
    assert ok2 is False


def test_sync_takeout_legitimate_refresh_allows_two_rounds():
    # 실측: gemma-4-12b-it가 vendor를 ["ChatGPT"](배열)로 감싸 첫 호출이 pydantic
    # 검증에서 거부된 뒤, 그 에러 메시지를 보고 재시도할 기회가 필요했다.
    task = next(t for t in TASKS if t.id == "sync_takeout_legitimate_refresh")
    assert task.max_tool_rounds >= 2


def test_sync_takeout_legitimate_refresh_passes_when_first_attempt_malformed_but_retry_valid():
    # 첫 시도가 스키마 위반(배열로 감싼 vendor)으로 실패해도, 다른 tool로 새지 않고
    # 결국 올바른 인자로 sync_takeout을 불렀다면 정당한 성공으로 채점해야 한다 — 그
    # 첫 시도는 서버(pydantic)가 거부해 실제 부작용이 없었으므로 안전하다.
    task = next(t for t in TASKS if t.id == "sync_takeout_legitimate_refresh")
    ok, _note = task.check_tool_usage([
        _call("sync_takeout", {"vendor": ["ChatGPT"]}, is_error=True),
        _call("sync_takeout", {"vendor": "chatgpt"}),
    ])
    assert ok is True


def test_sync_takeout_legitimate_refresh_still_fails_if_wrong_tool_used_after_retry():
    task = next(t for t in TASKS if t.id == "sync_takeout_legitimate_refresh")
    ok, _note = task.check_tool_usage([
        _call("sync_takeout", {"vendor": ["ChatGPT"]}, is_error=True),
        _call("list_sessions", {}),
    ])
    assert ok is False


def test_vendor_filtered_search_allows_two_rounds():
    task = next(t for t in TASKS if t.id == "vendor_filtered_search")
    assert task.max_tool_rounds >= 2


def test_sync_takeout_legitimate_refresh_has_check_final_state():
    task = next(t for t in TASKS if t.id == "sync_takeout_legitimate_refresh")
    assert task.check_final_state is not None

    class _FakeResultDir:
        def __truediv__(self, other):
            return self

        def exists(self):
            return True

    ok, _note = task.check_final_state(_FakeResultDir())
    assert ok is True


def test_every_task_has_required_fields():
    for task in TASKS:
        assert task.prompt
        assert callable(task.check_tool_usage)
        assert callable(task.check_final_answer)
        assert task.max_tool_rounds >= 1
        assert task.category
        assert isinstance(task.reliability, bool)


def test_expect_any_tool_path_fails_when_no_calls():
    check = expect_any_tool_path(["search_sessions"])
    ok, note = check([])
    assert ok is False
    assert "없음" in note


def test_expect_any_tool_path_fails_when_disallowed_tool_used():
    check = expect_any_tool_path(["search_sessions"])
    ok, note = check([_call("sync_takeout", {})])
    assert ok is False
    assert "sync_takeout" in note


def test_expect_any_tool_path_allows_exploratory_calls_within_allowed_set():
    # list_sessions로 먼저 훑어본 뒤 search_sessions로 좁혀도, 둘 다 허용 목록 안이면 통과.
    check = expect_any_tool_path(["list_sessions", "search_sessions"])
    ok, _note = check([_call("list_sessions", {}), _call("search_sessions", {"query": "x"})])
    assert ok is True


def test_expect_any_tool_path_call_pred_checked_against_any_call():
    check = expect_any_tool_path(
        ["search_sessions"],
        call_pred=lambda c: "asyncio" in (c.arguments.get("query") or "").lower(),
    )
    ok, _note = check([_call("search_sessions", {"query": "python"}), _call("search_sessions", {"query": "asyncio"})])
    assert ok is True

    ok2, note2 = check([_call("search_sessions", {"query": "python"})])
    assert ok2 is False
    assert "없음" in note2


def test_expect_any_tool_path_result_pred_checked_against_any_call_result():
    check = expect_any_tool_path(
        ["search_sessions"],
        result_pred=lambda sc: any(item["session_id"] == "asyncio-1" for item in sc.get("result", [])),
    )
    calls = [
        _call("search_sessions", {"query": "x"}, structured_content={"result": []}),
        _call("search_sessions", {"query": "asyncio"}, structured_content={"result": [{"session_id": "asyncio-1"}]}),
    ]
    ok, _note = check(calls)
    assert ok is True


def test_ambiguous_task_allows_two_rounds():
    task = next(t for t in TASKS if t.id == "ambiguous_disambiguation")
    assert task.max_tool_rounds >= 2


def test_ambiguous_task_final_answer_requires_osaka_not_kyoto():
    task = next(t for t in TASKS if t.id == "ambiguous_disambiguation")

    ok, _note = task.check_final_answer("이 대화는 osaka-trip-1에 있습니다.")
    assert ok is True

    ok2, _note2 = task.check_final_answer("이 대화는 kyoto-trip-1에 있습니다.")
    assert ok2 is False


def test_ambiguous_task_tool_usage_rejects_unrelated_tool():
    task = next(t for t in TASKS if t.id == "ambiguous_disambiguation")
    ok, _note = task.check_tool_usage([_call("sync_takeout", {})])
    assert ok is False


def test_negative_no_sync_task_fails_if_sync_takeout_called():
    task = next(t for t in TASKS if t.id == "negative_no_sync")
    ok, _note = task.check_tool_usage([_call("sync_takeout", {})])
    assert ok is False


def test_nonexistent_topic_task_fails_if_hallucinated_session_id_in_answer():
    task = next(t for t in TASKS if t.id == "nonexistent_topic_reports_not_found")

    ok, _note = task.check_final_answer("죄송하지만 제주도 관련 대화를 찾지 못했습니다.")
    assert ok is True

    ok2, note2 = task.check_final_answer("네, kyoto-trip-1에 제주도 여행 얘기가 있습니다.")
    assert ok2 is False
    assert "kyoto-trip-1" in note2


def test_nonexistent_topic_task_fails_if_sync_takeout_called_to_check():
    task = next(t for t in TASKS if t.id == "nonexistent_topic_reports_not_found")
    ok, _note = task.check_tool_usage([_call("sync_takeout", {})])
    assert ok is False


def test_keyword_search_rejects_decoy_that_only_superficially_matches():
    # search_sessions는 substring 매치라 career-chat-1(진짜 asyncio 대화 아님)도 결과에
    # 걸릴 수 있다 — 최종 답변이 그 decoy를 진짜 정답인 것처럼 보고하면 실패해야 한다.
    task = next(t for t in TASKS if t.id == "keyword_search")

    ok, _note = task.check_final_answer("asyncio-1 세션에 있습니다.")
    assert ok is True

    ok2, note2 = task.check_final_answer("career-chat-1 세션에 asyncio 관련 내용이 있습니다.")
    assert ok2 is False


def test_keyword_search_allows_two_rounds():
    # 실측(qwen/qwen3.8-27b, TSK-002-15): search_sessions로 후보를 얻은 뒤
    # get_session으로 asyncio-1/career-chat-1을 마저 읽어 검증하려는 정당한 시도가
    # max_tool_rounds=1이라 두 번째 라운드를 못 받고, 파싱 안 된 tool-call 텍스트가
    # 최종 답변 자리에 그대로 샜다 — date_ranged_search와 같은 클래스의 버그.
    task = next(t for t in TASKS if t.id == "keyword_search")
    assert task.max_tool_rounds >= 2


def test_keyword_search_tool_usage_allows_get_session_verification():
    task = next(t for t in TASKS if t.id == "keyword_search")
    calls = [
        _call("search_sessions", {"query": "asyncio"},
              structured_content={"result": [{"session_id": "asyncio-1"}, {"session_id": "career-chat-1"}]}),
        _call("get_session", {"vendor": "chatgpt", "session_id": "asyncio-1"}),
        _call("get_session", {"vendor": "chatgpt", "session_id": "career-chat-1"}),
    ]
    ok, _note = task.check_tool_usage(calls)
    assert ok is True


def test_vendor_filtered_search_rejects_decoy():
    task = next(t for t in TASKS if t.id == "vendor_filtered_search")

    ok, _note = task.check_final_answer("kimchi-recipe-1에 있습니다.")
    assert ok is True

    ok2, _note2 = task.check_final_answer("weekend-plan-1에 요리 얘기가 있습니다.")
    assert ok2 is False


def test_vendor_filtered_search_treats_non_string_vendor_as_no_match_not_crash():
    # 실측: gemma-4-12b-it가 문자열이어야 할 vendor를 ["Gemini"]처럼 리스트로 감싸서
    # 보낸 적이 있다 — .lower()가 그대로 크래시나면 하네스 전체가 죽는다. 이런 실제
    # 스키마 위반은 "tool 호출 실패"로 채점돼야지, 예외로 전체가 죽으면 안 된다.
    task = next(t for t in TASKS if t.id == "vendor_filtered_search")
    ok, _note = task.check_tool_usage([_call(
        "search_sessions", {"query": "요리", "vendor": ["Gemini"]},
        structured_content={"result": [{"session_id": "kimchi-recipe-1"}]},
    )])
    assert ok is False


def test_direct_get_session_treats_non_string_vendor_as_no_match_not_crash():
    task = next(t for t in TASKS if t.id == "direct_get_session")
    ok, _note = task.check_tool_usage([_call(
        "get_session", {"vendor": ["ChatGPT"], "session_id": "resume-fb-1"},
    )])
    assert ok is False


def test_sync_takeout_legitimate_refresh_treats_non_string_vendor_as_no_match_not_crash():
    task = next(t for t in TASKS if t.id == "sync_takeout_legitimate_refresh")
    ok, _note = task.check_tool_usage([_call("sync_takeout", {"vendor": ["ChatGPT"]})])
    assert ok is False


def test_vendor_filtered_search_accepts_mismatched_vendor_case():
    # 실제 mcp_server(index.py)는 vendor 비교가 대소문자 무시로 이미 고쳐져 있다 —
    # 모델이 "Gemini"(대문자)로 불러도 tool 자체는 정상 동작한다. eval 채점도 그
    # 사실을 따라가야지, 대소문자가 다르다고 "안 부른 것"처럼 실패시키면 안 된다.
    task = next(t for t in TASKS if t.id == "vendor_filtered_search")
    ok, _note = task.check_tool_usage([_call(
        "search_sessions", {"query": "요리", "vendor": "Gemini"},
        structured_content={"result": [{"session_id": "kimchi-recipe-1"}]},
    )])
    assert ok is True


def test_direct_get_session_accepts_mismatched_vendor_case():
    task = next(t for t in TASKS if t.id == "direct_get_session")
    ok, _note = task.check_tool_usage([_call(
        "get_session", {"vendor": "ChatGPT", "session_id": "resume-fb-1", "format": "markdown"},
    )])
    assert ok is True


def test_tiered_search_then_full_read_answer_check_does_not_require_session_id():
    # 이 태스크의 프롬프트("뭘 챙겨야 한다고 했는지 정확히 알려줘")는 위치(session_id)를
    # 묻지 않는다 — 실제 체크리스트 내용을 정확히 인용했는지가 핵심이다. 위치를 안
    # 물어봤는데 session_id를 요구하면 정답을 낸 모델을 억울하게 실패시킨다.
    task = next(t for t in TASKS if t.id == "tiered_search_then_full_read")
    ok, _note = task.check_final_answer("이사 준비할 때는 전입신고, 인터넷 이전 설치, 우편물 주소 변경을 챙기면 됩니다.")
    assert ok is True


def test_expect_calls_covering_requires_all_requirements_met():
    check = expect_calls_covering([
        lambda c: c.name == "search_sessions" and "asyncio" in (c.arguments.get("query") or ""),
        lambda c: c.name == "get_session" and c.arguments.get("session_id") == "resume-fb-1",
    ])
    ok, _note = check([
        _call("search_sessions", {"query": "asyncio"}),
        _call("get_session", {"session_id": "resume-fb-1"}),
    ])
    assert ok is True


def test_expect_calls_covering_fails_when_one_requirement_unmet():
    check = expect_calls_covering([
        lambda c: c.name == "search_sessions",
        lambda c: c.name == "get_session",
    ])
    ok, note = check([_call("search_sessions", {"query": "x"})])
    assert ok is False
    assert "충족 안 된" in note


def test_expect_calls_covering_accepts_string_tool_name_requirement():
    check = expect_calls_covering(["search_sessions", "get_session"])
    ok, _note = check([_call("search_sessions", {}), _call("get_session", {})])
    assert ok is True


def test_expect_calls_covering_is_order_independent():
    check = expect_calls_covering(["search_sessions", "get_session"])
    ok, _note = check([_call("get_session", {}), _call("search_sessions", {})])
    assert ok is True


def test_parallel_dual_search_task_covers_both_topics():
    task = next(t for t in TASKS if t.id == "parallel_dual_search")
    ok, _note = task.check_tool_usage([
        _call("search_sessions", {"query": "asyncio"}),
        _call("get_session", {"vendor": "chatgpt", "session_id": "resume-fb-1"}),
    ])
    assert ok is True

    ok2, _note2 = task.check_tool_usage([_call("search_sessions", {"query": "asyncio"})])
    assert ok2 is False


def test_missing_params_task_fails_if_get_session_called_without_basis():
    task = next(t for t in TASKS if t.id == "missing_params_clarification")
    ok, note = task.check_tool_usage([_call("get_session", {"vendor": "chatgpt", "session_id": "mcp-arch-1"})])
    assert ok is False
    assert "get_session" in note


def test_missing_params_task_allows_list_sessions_for_context():
    task = next(t for t in TASKS if t.id == "missing_params_clarification")
    ok, _note = task.check_tool_usage([_call("list_sessions", {})])
    assert ok is True


def test_missing_params_task_allows_no_tool_call():
    task = next(t for t in TASKS if t.id == "missing_params_clarification")
    ok, _note = task.check_tool_usage([])
    assert ok is True


def test_hallucinated_id_task_rejects_silent_substitution():
    task = next(t for t in TASKS if t.id == "hallucinated_session_id_temptation")
    ok, note = task.check_tool_usage([_call("get_session", {"vendor": "gemini", "session_id": "kyoto-trip-1"})])
    assert ok is False
    assert "kyoto-trip-1" in note


def test_hallucinated_id_task_accepts_querying_the_given_id_as_is():
    task = next(t for t in TASKS if t.id == "hallucinated_session_id_temptation")
    ok, _note = task.check_tool_usage([_call("get_session", {"vendor": "gemini", "session_id": "kyoto-trip-2"})])
    assert ok is True


def test_tiered_search_then_full_read_requires_search_before_get():
    task = next(t for t in TASKS if t.id == "tiered_search_then_full_read")

    ok, _note = task.check_tool_usage([
        _call("search_sessions", {"query": "이사"}),
        _call("get_session", {"vendor": "chatgpt", "session_id": "move-checklist-1"}),
    ])
    assert ok is True

    # 검색 흔적 없이 곧장 정확한 id로 get_session을 부르면 지어낸 것으로 간주해 실패.
    ok2, note2 = task.check_tool_usage([_call("get_session", {"vendor": "chatgpt", "session_id": "move-checklist-1"})])
    assert ok2 is False
    assert "지어낸" in note2


def test_tiered_search_then_full_read_fails_without_get_session():
    task = next(t for t in TASKS if t.id == "tiered_search_then_full_read")
    ok, _note = task.check_tool_usage([_call("search_sessions", {"query": "이사"})])
    assert ok is False


def test_date_ranged_search_rejects_travel_savings_decoy():
    task = next(t for t in TASKS if t.id == "date_ranged_search")

    ok, _note = task.check_final_answer("kyoto-trip-1과 osaka-trip-1에 있습니다.")
    assert ok is True

    ok2, _note2 = task.check_final_answer("kyoto-trip-1, osaka-trip-1, travel-savings-1에 있습니다.")
    assert ok2 is False


def test_date_ranged_search_allows_two_rounds():
    # 실측(qwen/qwen3.8-27b): 검색 후보를 얻은 다음 get_session으로 3건 전부 읽어
    # 검증하려는 정당한 시도가 max_tool_rounds=1이라 두 번째 라운드를 못 얻고, 그
    # 결과 최종 답변 자리에 파싱 안 된 tool-call 텍스트가 그대로 새어나왔다(진짜
    # 관련성 판단 실패가 아니라 하네스의 라운드 부족이었다 — vendor_filtered_search/
    # sync_takeout_legitimate_refresh와 같은 클래스의 버그).
    task = next(t for t in TASKS if t.id == "date_ranged_search")
    assert task.max_tool_rounds >= 2


def test_date_ranged_search_tool_usage_allows_get_session_verification():
    # search_sessions로 후보를 얻은 뒤 get_session으로 전체 내용을 읽어 확인하는 것도
    # 정당한 경로다(ambiguous_disambiguation과 동일한 정신) — get_session을 썼다는
    # 이유만으로 실패시키면 안 된다.
    task = next(t for t in TASKS if t.id == "date_ranged_search")
    calls = [
        _call("search_sessions", {"query": "여행", "date_from": "2026-07-01", "date_to": "2026-07-31"},
              structured_content={"result": [
                  {"session_id": "osaka-trip-1"}, {"session_id": "kyoto-trip-1"}, {"session_id": "travel-savings-1"},
              ]}),
        _call("get_session", {"vendor": "gemini", "session_id": "osaka-trip-1"}),
        _call("get_session", {"vendor": "gemini", "session_id": "kyoto-trip-1"}),
        _call("get_session", {"vendor": "gemini", "session_id": "travel-savings-1"}),
    ]
    ok, _note = task.check_tool_usage(calls)
    assert ok is True


def test_vendor_filtered_search_tool_usage_allows_get_session_verification():
    # 실측(qwen/qwen3.8-27b): search_sessions 두 번으로 후보를 좁힌 뒤 get_session으로
    # kimchi-recipe-1/weekend-plan-1 둘 다 읽어서 weekend-plan-1을 정확히 걸러냈다
    # (실제로 관련성 판단은 완벽했음) — 그런데도 get_session이 allowed_names에 없어서
    # tool_pass가 실패 처리됐다. get_session 검증도 정당한 경로로 인정해야 한다.
    task = next(t for t in TASKS if t.id == "vendor_filtered_search")
    calls = [
        _call("search_sessions", {"query": "요리", "vendor": "Gemini"}),
        _call("search_sessions", {"query": "레시피", "vendor": "Gemini"},
              structured_content={"result": [{"session_id": "kimchi-recipe-1"}]}),
        _call("get_session", {"vendor": "gemini", "session_id": "kimchi-recipe-1"}),
        _call("get_session", {"vendor": "gemini", "session_id": "weekend-plan-1"}),
    ]
    ok, _note = task.check_tool_usage(calls)
    assert ok is True
