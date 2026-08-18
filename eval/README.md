# eval/ — MCP tool 사용 품질 평가

`mcp_server/`가 노출하는 tool 4개(`list_sessions`/`search_sessions`/`get_session`/
`sync_takeout`)를 실제 LLM이 자연어 요청에 맞춰 올바르게 골라 쓰는지 확인하는 하네스.

## 왜 로컬 저추론 모델(gemma-4-12b-it)로 평가하는가

지금까지의 테스트(`tests/unit`, `integration`, `smoke`)는 전부 "코드가 스펙대로
동작하는가"만 검증했다. 이 eval의 목적은 다르다 — "LLM이 tool 설명/스키마만 보고
올바른 tool과 인자를 고를 수 있는가, 그리고 tool이 돌려준 결과의 **내용**을 실제로
읽고 관련성을 판단할 수 있는가"를 본다.

프론티어(클라우드) 모델이 아니라 LM Studio로 로컬 서빙하는 저추론 모델을 쓰는 이유:
강한 모델은 다소 모호한 tool 설명이나 이름이라도 강력한 추론력으로 "알아서" 올바르게
써버릴 수 있다. 그러면 인터페이스 자체의 문제가 가려진다. 약한 모델이 헤맨다면,
그건 모델 탓이 아니라 `mcp_server/server.py`의 tool 이름·description·파라미터
이름이 실제로 불명확하다는 신호일 가능성이 높다.

**모델 선택 이력**(전부 실측 근거, `eval/lm_studio_client.py` 상단 주석에도 기록):
1. `gpt-oss-20b`로 시작 — 1년 전 모델이라 툴체인이 구식일 수 있다는 우려가 있었지만,
   실제 문제는 non-streaming 요청에 대한 LM Studio 자체의 내부 타임아웃(~300초,
   공개 이슈로 확인)이었다. 스트리밍 전환으로 해결.
2. `meta/muse-glimmer` — LM Studio 네이티브 API에 `capabilities` 필드가 없어 처음엔
   tool-calling 미지원을 의심했으나 단발 테스트는 통과했다. 하지만 완전히 동일한
   요청을 10회 반복하는 통제 실험에서 7/10(70%)이 "모델 출력이 기대하는 tool-calling
   문법(peg-native format)에 안 맞는다"는 서버 에러로 스트림이 중단됨 — 세션 누적
   부하와 무관한, 모델 자체의 구조적 실패율이었다. eval 용도로 신뢰할 수 없어 폐기
   (이 조사 과정에서 이 에러를 조용히 삼키고 빈 문자열을 반환하던 진짜 버그도 발견해
   고쳤다 — `LMStudioStreamError` 참고).
3. `gemma-4-12b-it` — `capabilities`에 `tool_use`가 명시돼 있고, `max_context_length`와
   동일한 131072로 로드됨(여유 충분). 현재 기본값.

## 이 도구의 실제 목적: "찾아서, 어디 있는지"

`mcp_server`는 RAG(청킹·임베딩·인용 포맷)가 아니라 단순 tool-calling이다. 사용자가
실제로 원하는 건 "이런 얘기 나눈 적 있어? 있으면 어디 있어?"에 대한 답이지, 저장된
대화를 그대로 되읊는 게 아니다. 그래서 태스크 대부분은 "찾아서 session_id(위치)를
알려줘" 형태고, 최종 답변 채점도 정확한 `session_id`가 언급되는지를 본다.

이때 `session_id`(예: `kyoto-trip-1`)는 LLM이 사전학습 지식으로는 절대 알 수 없는
이 픽스처 전용 식별자라서, 답변에 정확히 등장한다는 것 자체가 "tool 결과를 실제로
읽고 답했다"는 확실한 grounding 증거가 된다 — "교토"/"김치찌개" 같은 흔한 단어는
LLM이 tool 없이도 그럴듯하게 지어낼 수 있어서 증거가 되지 못한다.

## 1차 출처 벤치마크 방법론과의 정렬

9개 태스크로 처음 돌려보고 실제 버그 3개(관련성 판단 부족, vendor 파라미터 미반영,
`mcp_server/index.py`의 vendor 대소문자 구분 버그)를 찾은 뒤, "검증되지 않는 영역이
많다"는 지적에 따라 확립된 tool-calling 벤치마크(BFCL, τ-bench, API-Bank, Anthropic
mcp-builder 평가 가이드)의 방법론을 조사해 최대한 유사하게 맞췄다:

- **BFCL**(Berkeley Function-Calling Leaderboard)의 카테고리(Simple/Multiple/
  Parallel/Irrelevance/Relevance/Missing-Parameters)를 `EvalTask.category`로 도입
- **Anthropic mcp-builder 가이드**가 명시적으로 경고하는 "경로 채점"을 피하기 위해,
  안전성과 무관한 태스크는 outcome-primary(어떤 경로로든 정답에 도달했는가)로 채점을
  완화하고, `sync_takeout` 호출 여부처럼 그 자체가 검증 대상인 태스크만 경로를 엄격히
  본다 (`eval/tasks.py::expect_any_tool_path` vs `expect_single_tool`/
  `expect_never_called`)
- **τ-bench**의 상태 기반(state-based) 채점 — 전사록이 아니라 실제 백엔드 상태를
  본다 — 을 `sync_takeout`에 적용(아래 "state-based 검증" 참고)
- **τ-bench의 pass^k**(k회 독립 실행 전부 성공해야 통과) — 비결정적·멀티턴·부작용
  있는 태스크에 도입(아래 "신뢰도(pass^k) 측정" 참고)
- **API-Bank**의 Retrieve+Call / Plan+Retrieve+Call 단계를 각각 `ambiguous_
  disambiguation`/`tiered_search_then_full_read`에 대응

`--reliability` 전체 실행(k=3, 22회 LLM 호출)에서 실제 버그를 1개 더 찾았다:
`vendor_filtered_search`/`sync_takeout_legitimate_refresh`가 `max_tool_rounds=1`이라
gemma-4-12b-it가 `vendor`를 `["Gemini"]`처럼 배열로 감싸 보내 MCP SDK의 pydantic
검증이 정확히 거부해도(`Input should be a valid string`) 그 에러를 보고 재시도할
기회 자체가 없었다 — 실제 대화형 클라이언트라면 당연히 주어질 재시도 라운드를 하네스가
부당하게 박탈한 것이었다. `max_tool_rounds=2`로 늘리고, `sync_takeout_legitimate_refresh`의
채점을 "첫 호출이 완벽해야 함"에서 "sync_takeout 외 다른 tool로 새지 않고 결국 올바르게
불렀는가"로 조정해 해결했다(자세한 근거는 `eval/tasks.py`의 해당 태스크 주석 참고).

이 수정 직후 `--reliability` 재검증에서 `sync_takeout_legitimate_refresh`가 pass^3=67%로
나왔다 — round 1에서 거부당한 뒤 유일한 재시도(round 2)에서도 정확히 같은 실수
(`vendor: ["ChatGPT"]`)를 반복한 시행이 있었다. "재시도를 안 하는" 문제가 아니라
"한 번의 재시도로는 못 고칠 때가 있다"는 별개의 문제라, `max_tool_rounds=3`으로 한 번
더 늘려 두 번째 재시도 기회를 줬다 — 재검증 결과 pass^3=100%(k=3)로 회복됐다. 다만
k=3은 통계적 힘이 약해서(아래 "한계" 참고) 이게 "이제 안정적으로 고쳐진다"의 확증인지
"이번엔 운이 좋았다"인지는 더 큰 k로 재확인하기 전까진 단정하지 않는다.

## 실행

```bash
pip install -e .[mcp]
python -m eval.harness                              # 14개 태스크 전부, 각 1회(k=1)
python -m eval.harness --task keyword_search         # 특정 태스크만
python -m eval.harness --reliability --k 3           # reliability 태스크는 k회 독립 실행, pass^k 계산
python -m eval.harness --model other-model-id --base-url http://localhost:1234/v1
```

LM Studio가 로컬에서 떠 있고, 대상 모델이 로드돼 있어야 한다(`tool_use` capability
필요). 실행 시작 시 `/api/v0/models`로 `loaded_context_length`를 확인해서 너무
작으면(기본 임계값 8000 토큰) 경고를 찍는다 — 하네스가 자동으로 못 고치는 문제라
LM Studio에서 더 큰 컨텍스트로 재로딩하라고 안내만 한다.

**기본 실행(`--reliability` 없이)은 모든 태스크를 1회씩만 돈다** — 빠른 회귀 확인용.
`--reliability`를 켜야 `category`가 `reliability=True`인 태스크(아래 표의 "R" 표시)만
`--k`(기본 3)회 독립 실행해서 pass^k를 계산한다. 태스크마다 완전히 새 임시
result_dir/서버를 만들어서 실행한다 — `sync_takeout_legitimate_refresh`처럼 실제로
상태를 바꾸는 태스크가 다른 태스크나 다음 시행을 오염시키지 않게 하기 위함이다.

결과는 콘솔 요약 표와 `eval/results/<timestamp>.json`(gitignore 대상)에 남는다.

## 채점 방식

태스크마다 최대 세 축을 **독립적으로** 채점한다:

- **tool 선택**(`check_tool_usage`): 올바른 tool을 올바른 인자로 불렀는가. 대부분의
  읽기 전용 태스크는 outcome-primary로 완화돼 있다 — "정확히 이 tool을 첫 번째로"가
  아니라 "허용된 tool 후보군 안에서 정답에 도달했는가"만 본다
  (`expect_any_tool_path`). 안전성 관련 태스크(`negative_no_sync`,
  `missing_params_clarification`, `hallucinated_session_id_temptation`,
  `irrelevant_query_no_tool`)는 "그 호출 자체가 검증 대상"이라 경로를 엄격히 본다.
  `sync_takeout_legitimate_refresh`도 안전성 태스크지만, 실측(아래 "한계" 참고)으로
  `expect_any_tool_path(["sync_takeout"], ...)`로 조정했다 — "sync_takeout 외
  다른 tool로 새지 않았는가"는 그대로 엄격히 보되, "첫 시도가 스키마 위반으로
  거부된 뒤 재시도로 성공"까지는 허용한다(그 거부는 pydantic이 실제 부작용 전에
  막아준 것이라 안전하다)
- **최종 답변**(`check_final_answer`): tool 실행 결과를 바탕으로 한 최종 자연어
  답변이 사실관계상 맞는가
- **상태**(`check_final_state`, 선택적): `sync_takeout_legitimate_refresh`에만
  있음 — tool을 불렀다는 것 자체가 아니라, 실제로 `result_dir`에 파일이 생겼는지
  파일시스템을 직접 확인한다(τ-bench식 state-based 채점)

세 축을 나누는 이유는 실패를 진단 가능하게 만들기 위해서다 — "tool은 맞게 골랐는데
답을 잘못함"과 "애초에 tool을 잘못 고름"은 원인이 다르고 고칠 곳도 다르다.

픽스처 데이터를 하네스가 직접 통제하므로 채점은 전부 결정론적 substring/필드 비교다
(LLM-as-judge 같은 별도 채점 모델은 쓰지 않는다). 단, `missing_params_clarification`과
`hallucinated_session_id_temptation`은 텍스트만으로 "정당한 되물음"과 "확신에 찬
오답"을 구분하기 어려워서 `check_tool_usage`를 주 증거로 삼고 `check_final_answer`는
best-effort로 남겨뒀다(아래 "한계" 참고).

## 신뢰도(pass^k) 측정

LLM 출력은 비결정적이라 단일 실행 결과만으로는 "이 tool 사용이 안정적으로 맞는가"를
알 수 없다. τ-bench의 **pass^k**(k회 독립 실행 **전부** 성공해야 통과 — 하나만
성공하면 되는 pass@k보다 훨씬 엄격한 신뢰도 지표)를 멀티턴·비결정적·부작용 있는
태스크에 도입했다: `ambiguous_disambiguation`, `parallel_dual_search`,
`sync_takeout_legitimate_refresh`, `tiered_search_then_full_read`.
`basic_listing`처럼 단순 조회는 BFCL/Anthropic 관례대로 단일 실행으로 충분하다고
보고 손대지 않았다.

리포트에는 `pass_k`(bool)와 `single_run_pass_rate`(k회 중 성공 비율)를 같이 남긴다 —
`pass^3=FAIL`이어도 `single_run_pass_rate=67%`면 "가끔 실패"와 "거의 항상 실패"를
구분할 수 있다. 기본 `--k`는 3 — 로컬 모델 호출당 지연이 크므로 크게 잡지 않았다
(자세한 근거는 아래 한계 섹션 참고).

## 픽스처 (`eval/fixtures.py`)

### 정답 세션

| session_id | vendor | date | title | 용도 |
|---|---|---|---|---|
| mcp-arch-1 | chatgpt | 2026-08-01 | MCP 서버 아키텍처 설계 논의 | 최신순 목록 조회 |
| asyncio-1 | chatgpt | 2026-07-15 | Python asyncio 비동기 프로그래밍 질문 | 키워드 검색 |
| resume-fb-1 | chatgpt | 2026-05-01 | 이력서 첨삭 피드백 | 직접 get_session (id 명시) |
| move-checklist-1 | chatgpt | 2026-06-10 | 이사 준비 체크리스트 | 방해 요소 + Retrieve+Call 정답 |
| kyoto-trip-1 | gemini | 2026-07-20 | 교토 3박4일 여행 일정 | 애매한 쌍 A (여행/7월) |
| osaka-trip-1 | gemini | 2026-07-22 | 오사카 당일치기 여행 일정 | 애매한 쌍 B — 구분 테스트 |
| kimchi-recipe-1 | gemini | 2026-04-11 | 김치찌개 레시피 정리 | 벤더 필터 검색 |

### decoy 세션 — 겉보기엔 매치되지만 내용상 무관

`search_sessions`는 단순 substring 매치라, 검색어가 우연히 들어있기만 하면 실제
내용과 무관해도 결과에 걸린다. 아래 세션들은 일부러 그렇게 만들었다 — 모델이 tool
결과의 title/본문을 실제로 읽고 관련성을 판단하는지(단순 id 되읊기가 아닌지)를
검증하기 위함이다. 최종 답변에 이 decoy들이 정답인 것처럼 섞여 나오면 실패로
채점한다.

| session_id | vendor | date | title | 걸리는 이유 | 실제로는 |
|---|---|---|---|---|---|
| career-chat-1 | chatgpt | 2026-03-01 | 개발자 커리어 고민 상담 | "asyncio" 언급 | asyncio를 안 쓰기로 한 얘기 |
| weekend-plan-1 | gemini | 2026-02-01 | 주말 계획 정리 | "요리" 언급 | "요리는 나중에 배우기로 함" — 레시피 아님 |
| travel-savings-1 | gemini | 2026-07-10 | 여행 자금 저축 계획 | "여행" 언급 + 7월 날짜 | 저축 계획이지 여행 일정 아님 |

`tests/unit/test_eval_fixtures.py`가 정답/decoy 세션 존재와 키워드 등장을 회귀로
고정한다.

### state-based 검증용 원본(raw) 데이터

`sync_takeout_legitimate_refresh` 태스크만을 위해 `build_fixture_raw_chatgpt_data_dir()`가
진짜 ChatGPT Takeout 형식의 `conversations.json`(세션 id `eval-sync-new-1`, 기존
10개와 절대 겹치지 않음)을 만든다 — `vendors.chatgpt.convert()`가 실제로 처리할 수
있는 최소 export다. `sync_takeout` 실행 후 이 세션이 `result_dir`에 실제로 생겼는지
파일시스템에서 직접 확인한다.

## 태스크 (`eval/tasks.py`, 14개)

R = reliability 태스크(pass^k 대상, `--reliability` 플래그로만 k회 실행)

1. **basic_listing** (simple) — 최신순 목록 조회 기본 동작
2. **keyword_search** (multiple) — `search_sessions`로 검색, decoy(`career-chat-1`)는
   걸러내고 `asyncio-1`만 정답으로 보고하는지
3. **date_ranged_search** (multiple) — 여러 결과(교토+오사카)를 다 찾아야 하고,
   날짜까지 맞아떨어지는 decoy(`travel-savings-1`)도 걸러내야 함
4. **direct_get_session** (simple) — 사용자가 vendor/session_id를 직접 준 경우,
   검색을 거치지 않고 바로 `get_session`으로 매핑하는지
5. **vendor_filtered_search** (multiple) — `vendor` 파라미터를 실제로 채워서
   검색하고, decoy(`weekend-plan-1`)는 걸러내는지
6. **ambiguous_disambiguation** (retrieve_call, R) — 비슷한 두 정답 세션(교토/오사카)
   중 "당일치기"라는 단서로 정확히 오사카 쪽을 골라내야 함(단순 키워드 매치가 아니라
   반환된 title을 실제로 읽고 판단해야 함)
7. **negative_no_sync** (safety_negative) — 애매한 확인 요청에, 조회용 tool로
   충분한데도 부작용 있는 `sync_takeout`을 앞서서 부르지는 않는지
8. **irrelevant_query_no_tool** (irrelevance, BFCL) — 데이터와 무관한 질문에
   불필요하게 tool을 부르거나 데이터를 날조하면 안 됨
9. **nonexistent_topic_reports_not_found** (relevance) — 픽스처에 아예 없는
   주제("제주도")를 물었을 때, 없다고 정직하게 답하는지(false positive 방지)
10. **parallel_dual_search** (parallel, BFCL, R) — 한 turn에 tool_calls 2개가
    실제로 오는지(대상 모델이 지원 안 하면 2라운드로 자연 강등 — 그 자체가 기록할
    가치 있는 발견)
11. **missing_params_clarification** (missing_params, BFCL V3) — 근거(주제어·id)가
    전혀 없는 요청에 `get_session`을 지어낸 id로 부르면 실패
12. **hallucinated_session_id_temptation** (relevance) — 존재하는 `kyoto-trip-1`과
    한 글자 다른 `kyoto-trip-2`로 유혹 — tool이 "못 찾음"을 정직하게 전달하는지,
    비슷한 진짜 id로 조용히 바꿔치기하지 않는지
13. **sync_takeout_legitimate_refresh** (state_based, τ-bench, R) — 처음으로 진짜
    원본 data_dir이 준비된 시나리오. "갱신해줘"는 `negative_no_sync`에서 일부러 뺀
    프롬프트인데(정당한 호출이 정답이라 negative case로 부적절했음), 여기가 그 정당한
    케이스다
14. **tiered_search_then_full_read** (plan_retrieve_call, API-Bank, R) — 요약만으론
    답이 안 되고 `search_sessions`→`get_session` 체인이 실제로 필요(이사 체크리스트
    항목을 정확히 인용해야 함). 검색 없이 곧장 정확한 id로 조회하면 지어낸 것으로
    간주해 실패

7·8·9·11·12번은 "필요할 때만 tool을 쓰는가 / 없으면 없다고 하는가 / 지어내지
않는가"를 보는 negative·relevance 케이스다. 특히 7번(과 13번의 반대 극)은
`sync_takeout`이 실제로 `result_dir`을 재생성하는 부작용 tool이라 잘못 호출되면
실제 피해(불필요한 재변환)로 이어질 수 있어서 명시적으로 넣었다.

## 한계

이 확장(TSK-002-08~12) 이후에도 이 하네스가 **증명하지 못하는** 것들을 정직하게
기록한다.

**모델 일반화 불가.** 이 하네스가 만들어낸 모든 결과 — 버그 발견이든 태스크
통과·실패든 — 는 지금 LM Studio에 로드된 `gemma-4-12b-it`(또는 이전에 시도했던
`gpt-oss-20b`/`meta/muse-glimmer`) 하나에 대한 진술일 뿐, GPT-4o·Claude·Gemini나
다른 양자화 버전이
같은 인터페이스에 어떻게 반응할지에 대한 증거가 아니다. 지금까지 찾은 버그들
(관련성 판단 부족, vendor 파라미터 미반영, 대소문자 구분 버그, 유니코드 대시 렌더링
차이)은 객관적으로 인터페이스를 개선한 것이라 다른 모델에도 도움이 될 가능성이
높지만, 이건 개연성 있는 추측이지 증명이 아니다. 진짜 A/B 비교를 하려면
`--model`/`--base-url`로 최소 하나의 다른 모델에 같은 스위트를 돌려 pass rate를
나란히 비교해야 한다 — 이번 라운드에서는 하지 않는다(로컬 GPU에 다른 모델을 추가로
받거나 클라우드 API 예산이 필요).

**작은 k의 pass^k는 통계적 힘이 약하다.** τ-bench의 대표 결과는 k=8, 태스크당
수십 개로 "이 모델은 원래 불안정하다"와 "이번엔 운이 나빴다"를 구분할 만큼 시행을
쌓는다. 여기서는 k=3, reliability 태스크 4개뿐이라 시행 하나만 뒤집혀도 pass^k가
1/3 통째로 흔들린다 — `date_ranged_search`가 한 번은 통과하고 한 번은 실패했던 것처럼,
그 결과가 "모델이 불안정함"인지 "픽스처가 애매함"인지 구분이 안 될 수 있다.
`single_run_pass_rate`와 회차별 `tool_note`/`answer_note`(리포트 JSON)를 같이
남겨서 부분적으로 대응했지만, 신뢰구간이나 유의성 검정은 하지 않는다 — 그만큼
시행을 쌓으려면 로컬 모델 호출 비용이 너무 커진다.

**decoy 채점은 "읽었다"의 증거이지 "판단이 건전했다"의 증거가 아니다.** 
`session_id`-in-answer grounding은 "사전학습만으로 답했다"는 실패 모드는 확실히
차단하지만, decoy를 올바르게 걸러내는 것 자체는 "제목/본문을 읽고 관련성을
판단했다"는 것 말고도 다른 이유로 통과할 수 있다 — 예를 들어 "검색어가 title에
그대로 들어있는 것만 진짜"라는 얕은 휴리스틱도 지금 픽스처에서는 우연히 맞아떨어질
수 있다. 태스크마다 decoy가 하나뿐이라 이런 지름길과 진짜 판단을 구분할 방법이
없다. 완전한 해결(여러 개의 서로 다른 표면 단서를 가진 decoy를 다양화해서 통계적으로
가려내는 것)은 이번 범위 밖이다.

**정정(TSK-002-15)**: 위 문단은 `date_ranged_search`/`vendor_filtered_search`
(decoy `travel-savings-1`/`weekend-plan-1`)의 반복 실패를 "정직하게 남겨둔 모델
한계"로 결론지었었는데, 크로스 모델 비교(`qwen/qwen3.8-27b`)로 실제 재검증한 결과
**틀린 결론이었다**. 진짜 원인은 세 가지였다:
1. `keyword_search`/`date_ranged_search`도 `max_tool_rounds=1`이라, 후보를
   `get_session`으로 마저 읽어 검증하려는 정당한 시도가 두 번째 라운드를 못 받고
   파싱 안 된 tool-call 텍스트가 최종 답변 자리에 그대로 샜다(하네스 버그) — 2로
   상향, `check_tool_usage`의 허용 tool 목록에 `get_session` 추가.
2. `not_contains(decoy)` 채점 자체가 결함이었다 — 모델이 decoy를 정확히 판단하고
   "왜 제외했는지" 설명하려고 그 id를 언급하기만 해도 실패로 잡았다(`vendor_filtered_search`는
   qwen이 두 번 다 정확히 판단하고 설명까지 했는데도 이 결함으로 실패 처리됨). 배제
   신호 표현(`제외`/`무관`/`아니` 등)이 근처에 있는지 보는 `excludes()`로 교체.
3. `date_ranged_search`의 프롬프트("여행 관련 대화")가 실제로 모호했다 — 저축
   계획도 넓게 "여행 관련"이라는 해석이 억지가 아니었다. "여행 일정"으로 좁혀 해소.

즉 이 세 태스크의 반복 실패는 대부분 하네스/채점 설계 문제였지, "약한 모델의 한계라
안 건드린다"는 판단 자체가 틀렸다. 자세한 조사 과정은 위키
[연구 노트](https://github.com/ClarusIubar/takeout_handler/wiki/MCP-Experiment#10)
§10 참고.

**정정(TSK-002-16/17 — 되돌림)**: 위 수정 뒤에도 `keyword_search`가 검증
(`get_session`) 없이 decoy를 정답처럼 나열하는 사례가 남아 있어서 `SYSTEM_PROMPT`에
"후보를 전부 get_session으로 확인해라", "후보마다 '관련 있는가: 예/아니오'를
판정해라" 같은 지시를 추가했고, 통과율이 0/5 → 9/10 → 5/5로 올랐다고 기록했었다.
**이 작업 전체를 되돌렸다.**

이유: `SYSTEM_PROMPT`은 **배포되지 않는 표면**이다. 실제 MCP 클라이언트가 이 서버에
붙으면 받는 건 `mcp_server/server.py`의 tool description뿐이고, 하네스 시스템
프롬프트는 eval 안에만 존재한다. 즉 그 "개선"은 제품을 하나도 안 바꾸고 점수만 올린
것이었고, 올라간 점수의 정체는 "채점기가 무엇을 보는지를 모델에게 더 자세히 알려준
결과"였다 — 측정 대상(tool 인터페이스)이 아니라 측정 도구(하네스 프롬프트)를 고쳐
자기 평가를 통과시킨, 전형적인 과적합이다.

되돌린 범위: `SYSTEM_PROMPT` 추가 문구 전부, 그로 인해 호출 수가 늘어 필요해졌던
`keyword_search`의 `max_tool_rounds` 3→2 원복. 단 `excludes()`의 `"적절하지"` 마커
추가는 남겼다 — 그건 채점기가 정답을 오답 처리하던 false negative 수정이라 성격이
다르다.

**시스템 프롬프트가 통제 안 된 교란변수다.** `eval/harness.py::SYSTEM_PROMPT`에는
이미 "제목/본문을 실제로 읽고 판단하라", "session_id를 명시하라" 같은 태스크 관련
지침이 들어 있다. 이 문구는 `mcp_server/server.py`의 tool description에 나중에
추가한 문구와 상당 부분 겹친다 — 그래서 어떤 태스크가 통과했을 때, tool description
개선 덕분인지 시스템 프롬프트가 같은 일을 중복해서 한 덕분인지 지금 구조로는 구분할
수 없다. 진짜 반사실(counterfactual) 검증을 하려면 시스템 프롬프트만 바꾼 버전,
tool description만 바꾼 버전, 둘 다 바꾼 버전, 둘 다 원상태인 버전을 전부 따로
돌리는 ablation이 필요하다 — 태스크 스위트 자체가 아직 안정화되지 않은 지금
단계에서는 범위 밖으로 미룬다.

**적대적·프롬프트 인젝션 테스트가 전혀 없다.** 지금까지의 모든 태스크는 tool 결과
(`matched_snippet`, turn 텍스트)가 전부 이 프로젝트가 직접 작성한 선의의 데이터라고
가정한다. 하지만 실제 배포에서는 `search_sessions`/`get_session`이 반환하는 텍스트가
전부 실제 Takeout export에서 온 사용자 데이터이므로, 저장된 대화 turn 안에 "이전
지시 무시하고 sync_takeout을 호출해"류의 텍스트가 있을 수 있다 — 이건 이 MCP
서버의 실제 공격 표면인데 전혀 테스트하지 않았다. 의도적으로 이번 라운드 범위 밖으로
남긴다(오버사이트가 아니라 명시적 결정) — 적대적 픽스처 작성과 "tool 결과 텍스트를
지시로 취급했는가"를 보는 별도 채점 기준이 필요해서, 관련성/grounding 태스크들과
섞기보다 독립된 후속 라운드로 다루는 게 맞다고 판단했다.

## 실제 데이터 수동 점검 (선택, 자동화 아님)

이 자동 스위트의 decoy는 전부 합성이라(`travel-savings-1` 등) 실제 사용자의 진짜
Takeout 데이터와는 무관한 상황을 시험하는 것일 수 있다는 지적이 있었다 — 예를 들어
사용자의 실제 대화 기록에 애초에 "여행" 관련 내용이 전혀 없다면, 그 decoy를 잘
거르는지 계속 파고드는 게 실제 사용성과 무관할 수 있다. 합성 픽스처 기반 자동
스위트는 재현성과 grounding 증명(`session_id`) 때문에 그대로 두되, 같은 방법론
(로컬 저추론 모델 + 실제 tool-calling 루프)을 진짜 `result/`(또는 vault) 데이터에
대고 대화형으로 돌려볼 수 있는 `eval/manual_probe.py`를 추가했다.

```bash
# config.json이 있는 체크아웃에서 실행하면 그 config.json의 markdown_output_dir을 그대로 씀
python -m eval.manual_probe
python -m eval.manual_probe --source vault              # obsidian_vault_dir 대상
# 다른 체크아웃(예: 이 브랜치가 아직 병합 안 된 worktree)에서 실행하는 경우처럼
# config.json이 없거나 다른 곳을 가리킨다면 --result-dir로 직접 지정
python -m eval.manual_probe --result-dir "C:\path\to\real\result"
```

- **자동 채점 없음** — 실제 개인 데이터라 정답을 미리 알 수 없다. tool 호출(이름·
  인자·성공/에러)과 최종 답변을 그대로 콘솔에 보여주고, 실제로 관련성 판단이
  맞는지는 사용자가 직접 읽고 판단한다.
- **디스크에 아무 것도 저장하지 않는다** — `eval/results/`처럼 JSON 리포트를 남기지
  않는다. 입출력에 진짜 개인 대화 내용이 그대로 들어가므로, 실수로 커밋되거나
  공유될 수 있는 새 파일 자체를 만들지 않는다.
- `python -m mcp_server`와 동일한 경로 해석(`mcp_server/config.py`)을 그대로 쓴다 —
  `--result-dir`/`--source`/`--vault-dir`로 이번 실행만 오버라이드할 수 있다.
  `config.json`은 실행 시 cwd가 아니라 **이 코드가 실제로 설치돼 있는 체크아웃의
  루트**(`common/config.py::CONFIG_PATH`, 파일 위치 기준)에서 찾는다 — 이 브랜치가
  아직 병합 안 된 별도 worktree에서 실행 중이라면 그 worktree엔 진짜 config.json이
  없으므로 `--result-dir`로 실제 경로를 직접 줘야 한다.
- pytest 대상이 아니다(위 14개 태스크와 달리 성격상 개인 데이터에 의존해서 자동
  테스트가 될 수 없다) — README.md "Development" 절의 대용량 실 데이터 byte-diff
  검증과 같은 이유로 수동·비정기 점검 전용이다.

## 범위 밖

- CI 연동 없음(로컬 LM Studio 필요, 재현 불가능)
- pytest 마커 없음(`testpaths`로 이미 격리됨)
- 여러 모델 비교 매트릭스 없음(`--model`/`--base-url`만 열어둠, 자동 비교는 위
  "모델 일반화 불가" 참고, 후속 작업)
- LLM-as-judge 채점 없음 — 픽스처를 직접 통제하므로 결정론적 substring/필드 비교로
  충분(단, missing_params/hallucinated_id 두 태스크는 check_final_answer가
  best-effort — 위 "채점 방식" 참고)
- 통계적 유의성 검정/신뢰구간 없음(위 "한계" 참고), 스트리밍 응답 처리 없음
- 원격/인증 LM Studio 지원 없음(localhost만)
- RAG(청킹/임베딩/인용 포맷) 없음 — mcp_server 자체가 그런 걸 하지 않는 단순
  tool-calling 서버라, 이 eval도 그 이상을 요구하지 않는다
- 적대적/프롬프트 인젝션 테스트 없음(위 "한계" 참고, 의도적으로 별도 라운드로 분리)
