import json
import sys
from pathlib import Path

import pytest

# pyproject.toml의 packages=["common", "vendors"]로 `pip install -e .`하면 필요 없지만,
# 설치 없이 바로 `pytest`를 돌릴 수 있도록 run.py와 동일한 방식으로 repo root를 sys.path에 넣는다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _build_chatgpt_export(dir_path, conversation_id="conv-1"):
    """detect()와 convert() 양쪽을 통과하는, 세션 1개(user->assistant)짜리 가장 작은
    conversations.json을 dir_path 아래에 만든다. integration/regression/smoke가 공유."""
    dir_path.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "id": conversation_id,
            "title": "Test conversation",
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
                        "content": {"content_type": "text", "parts": ["Hello"]},
                    },
                },
                "msg-a": {
                    "id": "msg-a",
                    "parent": "msg-u",
                    "children": [],
                    "message": {
                        "author": {"role": "assistant"},
                        "create_time": 1700000001,
                        "content": {"content_type": "text", "parts": ["Hi there"]},
                    },
                },
            },
        }
    ]
    (dir_path / "conversations.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    return dir_path


def _build_gemini_export(dir_path, session_id="session-abc123"):
    """detect()와 convert() 양쪽을 통과하는, 세션 1개(질문+응답)짜리 가장 작은 활동
    HTML을 dir_path 아래 (Takeout/Gemini 앱/내활동.html 형태, 실제 export와 동일한 중첩
    구조)에 만든다. integration/regression/smoke가 공유.

    _BlockParser의 상태 전이(prompt -> post_marker -> response)는 마커/타임스탬프/응답이
    서로 다른 텍스트 노드로 들어와야만 올바르게 동작하므로, <br>로 텍스트 노드 경계를
    명시적으로 끊는다 (한 덩어리로 이어붙이면 마커/타임스탬프 뒤 텍스트가 같은 노드 안에서
    통째로 버려져 response가 빈 문자열이 된다)."""
    nested = dir_path / "Takeout" / "Gemini 앱"
    nested.mkdir(parents=True, exist_ok=True)
    html = (
        '<div class="outer-cell mdl-cell mdl-cell--12-col mdl-shadow--2dp">'
        f'<a href="https://gemini.google.com/app/{session_id}">caption</a>'
        '<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">'
        "질문입니다항목을 검색함<br>"
        "2024. 3. 5. 오후 3:20:10 KST<br>"
        "답변입니다"
        "</div></div>"
    )
    (nested / "내활동.html").write_text(html, encoding="utf-8")
    return nested / "내활동.html"


@pytest.fixture
def minimal_chatgpt_export():
    """`minimal_chatgpt_export(dir_path, conversation_id="conv-1")`로 호출하는 팩토리
    fixture. conftest.py를 직접 import하지 않아도 모든 tests/ 하위 디렉토리에서 자동으로
    쓸 수 있게 fixture로 노출한다."""
    return _build_chatgpt_export


@pytest.fixture
def minimal_gemini_export():
    """`minimal_gemini_export(dir_path, session_id="session-abc123")`로 호출하는 팩토리
    fixture. 반환값은 실제로 만들어진 내활동.html의 Path."""
    return _build_gemini_export


def _build_claude_export(dir_path, standalone_uuid="conv-solo", project_uuid="chat-proj",
                          project_name="Jamissue"):
    """detect()와 convert() 양쪽을 통과하는 최소 Claude export를 dir_path 아래에 만든다.
    conversations.json(일반 대화 1개)과 design_chats/<uuid>.json(프로젝트 대화 1개)을
    둘 다 포함해서, 두 스키마가 실제로는 같은 convert() 배선을 함께 탄다는 걸 검증한다."""
    dir_path.mkdir(parents=True, exist_ok=True)

    standalone_payload = [
        {
            "uuid": standalone_uuid,
            "name": "일반 대화",
            "created_at": "2026-06-01T12:00:00.000000+00:00",
            "chat_messages": [
                {
                    "uuid": "m-1", "sender": "human",
                    "created_at": "2026-06-01T12:00:00.000000+00:00",
                    "content": [{"type": "text", "text": "질문입니다"}],
                },
                {
                    "uuid": "m-2", "sender": "assistant",
                    "created_at": "2026-06-01T12:00:01.000000+00:00",
                    "content": [
                        {"type": "thinking", "thinking": "생각 중"},
                        {"type": "text", "text": "답변입니다"},
                    ],
                },
            ],
        }
    ]
    (dir_path / "conversations.json").write_text(
        json.dumps(standalone_payload, ensure_ascii=False), encoding="utf-8"
    )

    design_chats_dir = dir_path / "design_chats"
    design_chats_dir.mkdir(parents=True, exist_ok=True)
    project_payload = {
        "uuid": project_uuid,
        "title": "프로젝트 대화",
        "project": {"uuid": f"proj-{project_name}", "name": project_name},
        "created_at": "2026-06-19T11:00:00.000000Z",
        "messages": [
            {
                "uuid": "u-1", "role": "user",
                "content": {"content": "저장소를 확인해줘", "timestamp": "2026-06-19T11:00:00.000000Z"},
            },
            {
                "uuid": "a-1", "role": "assistant",
                "content": {
                    "contentBlocks": [
                        {"type": "text", "text": "확인했습니다"},
                        {"type": "tool_call", "toolCall": {"name": "github_list_repos", "input": {}, "output": "1개"}},
                    ],
                    "timestamp": "2026-06-19T11:05:00.000000Z",
                },
            },
        ],
    }
    (design_chats_dir / f"{project_uuid}.json").write_text(
        json.dumps(project_payload, ensure_ascii=False), encoding="utf-8"
    )
    return dir_path


@pytest.fixture
def minimal_claude_export():
    """`minimal_claude_export(dir_path, standalone_uuid=..., project_uuid=..., project_name=...)`
    로 호출하는 팩토리 fixture. conversations.json(일반 대화)과 design_chats/*.json
    (프로젝트 대화)을 하나씩 만든다."""
    return _build_claude_export


@pytest.fixture
def patched_config_path(monkeypatch, tmp_path):
    """run.main()이 무조건 호출하는 load_config()가 실제 프로젝트의 config.json을
    읽거나(없으면 자동 생성) 건드리지 않도록 CONFIG_PATH를 tmp_path 아래로 돌린다.
    run.main()을 호출하는 모든 integration/smoke 테스트는 이 fixture를 반드시 요청해야
    한다 — common.config.load_config()가 자기 모듈의 전역 CONFIG_PATH를 참조하므로,
    여기를 패치하면 run.py가 `from common.config import load_config`로 가져다 쓰는
    호출에도 그대로 반영된다."""
    fake_path = tmp_path / "config.json"
    monkeypatch.setattr("common.config.CONFIG_PATH", fake_path)
    return fake_path


@pytest.fixture(autouse=True)
def _isolate_real_project_paths(monkeypatch, tmp_path):
    """모든 테스트에 기본으로 걸리는 안전망. patched_config_path나 --input을 깜빡한 새
    테스트가 나중에 생겨도, 실제 프로젝트의 config.json/data/를 절대 건드리지 않는다.
    존재하지 않는 tmp 경로로 돌리므로, DATA_DIR 폴백이 실제로 발동해도 그냥 "데이터
    없음"으로 조용히 스킵될 뿐 진짜 개인 데이터를 읽는 일은 없다.

    unit/regression 테스트는 run.CONFIG/run.DATA_DIR을 아예 참조하지 않으므로 완전히
    무해한 no-op이고, test_run_input.py처럼 이미 자체적으로 run.DATA_DIR을 monkeypatch
    하는 테스트는 그 안에서 다시 덮어쓰므로 순서 문제도 없다. 이 fixture는 안전망일 뿐,
    새 테스트가 --input 없이 실제 data/를 읽도록 짜는 습관을 정당화하지는 않는다 —
    여전히 CLI 레벨 테스트는 --input/--output-dir/--vault-dir을 tmp_path로 명시해야 한다."""
    monkeypatch.setattr("common.config.CONFIG_PATH", tmp_path / "config.json")
    import run
    monkeypatch.setattr(run, "DATA_DIR", tmp_path / "unused_data_dir")
