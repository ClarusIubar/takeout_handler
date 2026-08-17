"""eval 하네스용 합성 세션 데이터. common.session_markdown.build_session_markdown()을
그대로 재사용해서(mcp_server가 실제로 읽는 것과 동일한 렌더링 경로) result_dir을 만든다.

이 도구의 실제 목적은 "이런 얘기 나눈 적 있어? 있으면 어디 있어?"에 답하는 것이지,
저장된 대화 내용을 그대로 되읊는 게 아니다. 그래서 grounding 증거로 session_id(=위치
식별자) 자체를 쓴다 — "교토"/"김치찌개" 같은 흔한 단어는 LLM이 사전학습만으로도
그럴듯하게 답할 수 있지만, "kyoto-trip-1" 같은 이 픽스처 전용 session_id는 tool 결과를
실제로 읽지 않으면 알 수 없다.

search_sessions는 단순 substring 매치이므로, 각 세션을 구별하는 검색 키워드도 turn
텍스트에 실제로 등장하도록 신경 써서 작성한다. "제주도"처럼 아예 존재하지 않는 주제도
하나 필요하다 — false positive(없는데 있다고 답함) 방지를 검증하려면 "찾아도 없는" 케이스가
있어야 한다(harness.py가 검색 대상으로만 쓰고 세션을 만들지는 않는다).
"""

import json
from pathlib import Path

from common.session_markdown import build_session_markdown


def _write_session(result_dir, vendor, session_id, title, date_str, turns):
    vendor_dir = Path(result_dir) / vendor
    vendor_dir.mkdir(parents=True, exist_ok=True)
    md, _hash = build_session_markdown(
        vendor_tag=vendor, vendor_label=vendor, title=title, session_id=session_id,
        url=f"https://example.com/{vendor}/{session_id}", date_str=date_str, turns=turns,
    )
    (vendor_dir / f"{session_id}.md").write_text(md, encoding="utf-8")


def _qa(question, answer):
    return [
        {"role": "user", "text": question, "time_str": "00:00:00"},
        {"role": "assistant", "text": answer, "time_str": "00:00:01"},
    ]


def build_fixture_result_dir(root):
    """root 아래 7개 세션(chatgpt 4개, gemini 3개)을 써넣고, (result_dir, FACTS)를 반환한다.
    '제주도'처럼 여기 없는 주제는 의도적으로 만들지 않는다 — 존재하지 않음을 올바르게
    보고하는지 검증하는 negative 태스크용."""
    result_dir = Path(root)

    _write_session(
        result_dir, "chatgpt", "mcp-arch-1", "MCP 서버 아키텍처 설계 논의", "2026-08-01",
        _qa("MCP 서버를 어떻게 설계하면 좋을까?",
            "resource와 tool을 나눠서, 조회는 tool로 부작용 있는 sync는 별도 tool로 노출하면 됩니다."),
    )
    _write_session(
        result_dir, "chatgpt", "asyncio-1", "Python asyncio 비동기 프로그래밍 질문", "2026-07-15",
        _qa("asyncio에서 여러 코루틴을 동시에 실행하려면 어떻게 하나요?",
            "asyncio.gather()나 TaskGroup을 쓰면 여러 코루틴을 동시에 실행할 수 있습니다."),
    )
    _write_session(
        result_dir, "chatgpt", "resume-fb-1", "이력서 첨삭 피드백", "2026-05-01",
        _qa("제 이력서 좀 봐주실 수 있나요?",
            "경력 기술 부분을 성과 중심으로 다시 쓰면 이력서가 훨씬 좋아질 것 같습니다."),
    )
    _write_session(
        result_dir, "chatgpt", "move-checklist-1", "이사 준비 체크리스트", "2026-06-10",
        _qa("이사 갈 때 뭘 챙겨야 할지 체크리스트 좀 만들어줘.",
            "전입신고, 인터넷 이전 설치, 우편물 주소 변경 등을 챙기면 됩니다."),
    )
    _write_session(
        result_dir, "gemini", "kyoto-trip-1", "교토 3박4일 여행 일정", "2026-07-20",
        _qa("교토 3박4일 여행 일정 짜줘.",
            "1일차 교토역 도착, 2일차 기요미즈데라, 3일차 아라시야마, 4일차 귀국 일정을 추천합니다."),
    )
    _write_session(
        result_dir, "gemini", "osaka-trip-1", "오사카 당일치기 여행 일정", "2026-07-22",
        _qa("오사카 당일치기 여행 일정 짜줘.",
            "오전 오사카성, 점심 도톤보리, 오후 신사이바시 쇼핑 코스를 추천합니다."),
    )
    _write_session(
        result_dir, "gemini", "kimchi-recipe-1", "김치찌개 레시피 정리", "2026-04-11",
        _qa("맛있는 김치찌개 요리 방법 알려줘.",
            "신김치와 돼지고기를 볶다가 물을 붓고 끓이면 김치찌개 요리가 완성됩니다."),
    )

    # --- decoy 세션: 키워드는 substring으로 걸리지만 내용상 무관하다. search_sessions는
    # 단순 substring 매치라 이것도 검색 결과에 포함되므로, 모델이 tool 결과의 title/본문을
    # 실제로 읽고 관련성을 판단하는지(단순 id 되읊기가 아닌지)를 이걸로 검증한다. ---
    _write_session(
        result_dir, "chatgpt", "career-chat-1", "개발자 커리어 고민 상담", "2026-03-01",
        _qa("백엔드랑 프론트엔드 중에 뭐가 저한테 더 잘 맞을지 고민이에요.",
            "저는 백엔드보다는 프론트엔드가 잘 맞는 것 같아요. asyncio 같은 비동기 개념은 "
            "늘 어려워서 피하고 싶었거든요."),
    )
    _write_session(
        result_dir, "gemini", "weekend-plan-1", "주말 계획 정리", "2026-02-01",
        _qa("이번 주말에 뭐 하면 좋을까?",
            "이번 주말엔 집에서 좀 쉬려고요. 요리는 나중에 배우기로 했어요."),
    )
    _write_session(
        result_dir, "gemini", "travel-savings-1", "여행 자금 저축 계획", "2026-07-10",
        _qa("여행 갈 돈을 모으려면 저축을 어떻게 해야 할까?",
            "매달 일정 금액을 자동이체로 떼서 여행 전용 통장에 모으는 걸 추천드렸습니다."),
    )

    facts = {
        "newest_session_id": "mcp-arch-1",
        "mcp_arch_session": ("chatgpt", "mcp-arch-1"),
        "asyncio_session": ("chatgpt", "asyncio-1"),
        "resume_session": ("chatgpt", "resume-fb-1"),
        "move_session": ("chatgpt", "move-checklist-1"),
        "kyoto_session": ("gemini", "kyoto-trip-1"),
        "osaka_session": ("gemini", "osaka-trip-1"),
        "kimchi_session": ("gemini", "kimchi-recipe-1"),
        "nonexistent_topic": "제주도",
        "asyncio_decoy_session": ("chatgpt", "career-chat-1"),
        "kimchi_decoy_session": ("gemini", "weekend-plan-1"),
        "travel_decoy_session": ("gemini", "travel-savings-1"),
    }
    return result_dir, facts


def build_fixture_raw_chatgpt_data_dir(root, conversation_id="eval-sync-new-1"):
    """sync_takeout이 실제로 처리할 원본(raw) ChatGPT export를 만든다 —
    tests/conftest.py::_build_chatgpt_export와 동일한 최소 conversations.json 패턴을
    eval/ 안에 독립적으로 포팅했다(tests/에는 __init__.py가 없어 패키지로 import할 수
    없으므로). conversation_id는 build_fixture_result_dir()이 미리 심어두는 10개
    session_id와 절대 겹치지 않아야 한다 — sync_takeout 실행 전후로 "새로 생긴
    세션"임을 명확히 구분하기 위함이다."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "id": conversation_id,
            "title": "Eval sync 검증용 새 대화",
            "create_time": 1700000000,
            "current_node": "msg-a",
            "mapping": {
                "root": {"id": "root", "message": None, "parent": None, "children": ["msg-u"]},
                "msg-u": {
                    "id": "msg-u",
                    "parent": "root",
                    "children": ["msg-a"],
                    "message": {
                        "author": {"role": "user"},
                        "create_time": 1700000000,
                        "content": {"content_type": "text", "parts": ["동기화 테스트 질문"]},
                    },
                },
                "msg-a": {
                    "id": "msg-a",
                    "parent": "msg-u",
                    "children": [],
                    "message": {
                        "author": {"role": "assistant"},
                        "create_time": 1700000001,
                        "content": {"content_type": "text", "parts": ["동기화 테스트 답변"]},
                    },
                },
            },
        }
    ]
    (root / "conversations.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return root
