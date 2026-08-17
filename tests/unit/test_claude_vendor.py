import json
from datetime import datetime

from vendors.claude import (
    VENDOR_LABEL,
    VENDOR_TAG,
    _find_claude_candidates,
    _local_date,
    _local_dt_str,
    convert,
    detect,
)


def _write(dir_path, name, payload):
    (dir_path / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


# ==========================================
# detect() / 후보 탐색
# ==========================================

def test_detect_true_with_conversations_json_only(tmp_path):
    _write(tmp_path, "conversations.json", [])
    assert detect(tmp_path) is True


def test_detect_true_with_design_chats_dir_only(tmp_path):
    # design_chats/*.json 변환은 TSK-003-02에서 추가되지만, detect()는 export 전체를
    # 기준으로 감지해야 한다 — 프로젝트 대화만 있는(conversations.json 없는) export를
    # "데이터 없음"으로 잘못 판정하면 안 되기 때문이다.
    (tmp_path / "design_chats").mkdir()
    assert detect(tmp_path) is True


def test_detect_false_when_nothing_present(tmp_path):
    assert detect(tmp_path) is False


def test_find_claude_candidates_handles_one_level_of_nesting(tmp_path):
    nested = tmp_path / "claude-export"
    nested.mkdir()
    _write(nested, "conversations.json", [])
    candidates = _find_claude_candidates(tmp_path)
    assert candidates == [nested]


def test_find_claude_candidates_ignores_macosx_junk(tmp_path):
    real = tmp_path / "real-export"
    real.mkdir()
    _write(real, "conversations.json", [])
    junk = tmp_path / "__MACOSX" / "real-export"
    junk.mkdir(parents=True)
    _write(junk, "conversations.json", [])

    candidates = _find_claude_candidates(tmp_path)

    assert candidates == [real]


# ==========================================
# 타임존 — Claude의 ISO8601(UTC) 타임스탬프를 ChatGPT(datetime.fromtimestamp,
# 로컬 타임존)와 동일하게 "실행 중인 시스템의 로컬 시각"으로 보여줘야 한다.
# UTC 그대로 노출하면 벤더마다 같은 실제 시각이 다르게 표시된다.
# ==========================================

def test_local_dt_str_converts_utc_to_system_local_time():
    expected = datetime.fromisoformat("2026-06-19T11:00:00+00:00").astimezone()
    assert _local_dt_str("2026-06-19T11:00:00.000000Z") == expected.strftime("%Y-%m-%d %H:%M:%S")


def test_local_date_converts_utc_to_system_local_date():
    expected = datetime.fromisoformat("2026-06-19T23:30:00+00:00").astimezone()
    assert _local_date("2026-06-19T23:30:00.000000Z") == expected.date().isoformat()


# ==========================================
# conversations.json (일반 대화) 로더
# ==========================================

def _standalone_conversation(uuid="conv-1", name="Test chat"):
    return {
        "uuid": uuid,
        "name": name,
        "created_at": "2026-06-01T12:00:00.000000+00:00",
        "chat_messages": [
            {
                "uuid": "m-1",
                "sender": "human",
                "created_at": "2026-06-01T12:00:00.000000+00:00",
                "content": [{"type": "text", "text": "Hello"}],
                "attachments": [],
                "files": [],
            },
            {
                "uuid": "m-2",
                "sender": "assistant",
                "created_at": "2026-06-01T12:00:01.000000+00:00",
                "content": [
                    {"type": "thinking", "thinking": "Let me think about this."},
                    {"type": "text", "text": "Hi there"},
                    {"type": "token_budget", "budget": 1234},
                ],
                "attachments": [],
                "files": [],
            },
        ],
    }


def test_convert_standalone_conversation_creates_one_file(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write(data_dir, "conversations.json", [_standalone_conversation()])
    result_dir = tmp_path / "result"

    stats = convert(data_dir, result_dir, dry_run=False)

    assert stats.vendor_tag == VENDOR_TAG
    assert stats.sessions_found == 1
    assert stats.files_created == 1
    md_files = list(result_dir.glob("*.md"))
    assert len(md_files) == 1
    assert md_files[0].name == "conv-1.md"
    text = md_files[0].read_text(encoding="utf-8")
    assert 'title: "Test chat"' in text
    assert 'session_id: "conv-1"' in text
    assert "Hello" in text
    assert "Hi there" in text
    # thinking/token_budget 같은 비-text 블록이 본문을 깨지 않고 스킵/렌더링됐는지만 확인
    assert f"- {VENDOR_TAG}" in text
    assert VENDOR_LABEL in text


def test_convert_standalone_empty_title_falls_back_to_first_sentence(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    conv = _standalone_conversation(uuid="conv-2", name="")
    _write(data_dir, "conversations.json", [conv])
    result_dir = tmp_path / "result"

    convert(data_dir, result_dir, dry_run=False)

    text = (result_dir / "conv-2.md").read_text(encoding="utf-8")
    assert 'title: "Hello"' in text


def test_convert_standalone_unknown_block_type_is_skipped_not_crashed(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    conv = _standalone_conversation(uuid="conv-3")
    conv["chat_messages"][1]["content"].append({"type": "some_future_block_type", "x": 1})
    _write(data_dir, "conversations.json", [conv])
    result_dir = tmp_path / "result"

    stats = convert(data_dir, result_dir, dry_run=False)

    assert stats.parse_errors == 0
    assert (result_dir / "conv-3.md").exists()


def test_convert_standalone_empty_messages_is_skipped(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    conv = {"uuid": "conv-empty", "name": "Empty", "created_at": "2026-01-01T00:00:00Z",
            "chat_messages": []}
    _write(data_dir, "conversations.json", [conv])
    result_dir = tmp_path / "result"

    stats = convert(data_dir, result_dir, dry_run=False)

    assert stats.empty_skipped == 1
    assert not list(result_dir.glob("*.md"))


def test_convert_standalone_dry_run_creates_no_files(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write(data_dir, "conversations.json", [_standalone_conversation()])
    result_dir = tmp_path / "result"

    stats = convert(data_dir, result_dir, dry_run=True)

    assert stats.files_created == 1
    assert not result_dir.exists() or not list(result_dir.glob("*.md"))


def test_convert_standalone_missing_attachment_is_reported(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    conv = _standalone_conversation(uuid="conv-attach")
    conv["chat_messages"][0]["attachments"] = [
        {"file_uuid": "f-1", "file_name": "photo.png"}
    ]
    _write(data_dir, "conversations.json", [conv])
    result_dir = tmp_path / "result"

    stats = convert(data_dir, result_dir, dry_run=False)

    assert stats.attachments_missing == 1
    text = (result_dir / "conv-attach.md").read_text(encoding="utf-8")
    assert "photo.png" in text
    assert "누락" in text


def test_convert_standalone_tool_result_local_resource_is_not_silently_dropped(tmp_path):
    # 실제 데이터에서 발견: 코드 실행 등으로 Claude가 만든 파일은 tool_result.content
    # 안에 {"type": "local_resource", "file_path": ..., "name": ...} 형태로 들어온다
    # (텍스트가 아니라서 이전 렌더러는 이런 항목을 통째로 무시하고 있었다). 이 export엔
    # 실제 파일 바이트가 없으니 내용을 못 넣더라도, 파일이 생성됐다는 사실 자체는
    # 표시해야 한다.
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    conv = _standalone_conversation(uuid="conv-resource")
    conv["chat_messages"][1]["content"].append({
        "type": "tool_result",
        "content": [
            {
                "type": "local_resource",
                "file_path": "/mnt/user-data/outputs/chart.jsx",
                "name": "price vs performance",
                "mime_type": None,
                "uuid": "res-1",
            }
        ],
    })
    _write(data_dir, "conversations.json", [conv])
    result_dir = tmp_path / "result"

    convert(data_dir, result_dir, dry_run=False)

    text = (result_dir / "conv-resource.md").read_text(encoding="utf-8")
    assert "price vs performance" in text
    assert "chart.jsx" in text


# ==========================================
# design_chats/*.json (프로젝트/에이전틱 대화) 로더
# ==========================================

def _write_design_chat(dir_path, uuid, project_name, messages, title="Chat"):
    (dir_path / "design_chats").mkdir(parents=True, exist_ok=True)
    payload = {
        "uuid": uuid,
        "title": title,
        "project": {"uuid": f"proj-{project_name}", "name": project_name},
        "created_at": "2026-06-19T11:00:00.000000Z",
        "updated_at": "2026-06-19T11:10:00.000000Z",
        "messages": messages,
    }
    (dir_path / "design_chats" / f"{uuid}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _plain_user_message(text="다시 재개"):
    return {
        "uuid": "u-1",
        "role": "user",
        "content": {
            "authorAccountUuid": "acc-1",
            "authorName": "Tester",
            "content": text,
            "id": "u-1",
            "role": "user",
            "timestamp": "2026-06-19T11:00:00.000000Z",
        },
    }


def _agentic_assistant_message():
    return {
        "uuid": "a-1",
        "role": "assistant",
        "content": {
            "id": "a-1",
            "role": "assistant",
            "content": "ignored raw text, contentBlocks is the source of truth",
            "contentBlocks": [
                {"type": "text", "text": "I'll check the repo."},
                {
                    "type": "tool_call",
                    "toolCall": {
                        "id": "toolu_1",
                        "type": "edit",
                        "name": "github_list_repos",
                        "input": {},
                        "output": "1 repository found",
                    },
                },
                {"type": "thinking", "text": "The user wants a repo summary."},
                {"type": "some_future_block_type", "x": 1},
            ],
            "id": "a-1",
            "role": "assistant",
            "timestamp": "2026-06-19T11:05:00.000000Z",
        },
    }


def test_convert_project_chat_creates_file_in_project_subfolder(tmp_path):
    data_dir = tmp_path / "data"
    _write_design_chat(
        data_dir, "chat-1", "Jamissue",
        [_plain_user_message(), _agentic_assistant_message()],
    )
    result_dir = tmp_path / "result"

    stats = convert(data_dir, result_dir, dry_run=False)

    assert stats.sessions_found == 1
    md_path = result_dir / "Jamissue" / "chat-1.md"
    assert md_path.exists()
    text = md_path.read_text(encoding="utf-8")
    assert "다시 재개" in text
    assert "I'll check the repo." in text
    assert "github_list_repos" in text
    assert "The user wants a repo summary." in text


def test_convert_project_chat_with_attachment_object_content_and_empty_title(tmp_path):
    data_dir = tmp_path / "data"
    user_msg = {
        "uuid": "u-2",
        "role": "user",
        "content": {
            "authorAccountUuid": "acc-1",
            "authorName": "Tester",
            "content": "Please review this file",
            "attachments": [{"id": "att-1", "name": "notes.txt", "content": "some notes"}],
            "id": "u-2",
            "role": "user",
            "timestamp": "2026-06-19T11:00:00.000000Z",
        },
    }
    _write_design_chat(data_dir, "chat-2", "GDWEB", [user_msg], title="")
    result_dir = tmp_path / "result"

    convert(data_dir, result_dir, dry_run=False)

    text = (result_dir / "GDWEB" / "chat-2.md").read_text(encoding="utf-8")
    assert "Please review this file" in text
    assert 'title: "Please review this file"' in text


def test_convert_project_chat_empty_messages_is_skipped(tmp_path):
    data_dir = tmp_path / "data"
    _write_design_chat(data_dir, "chat-empty", "Untitled", [])
    result_dir = tmp_path / "result"

    stats = convert(data_dir, result_dir, dry_run=False)

    assert stats.empty_skipped == 1
    assert not (result_dir / "Untitled").exists()


def test_convert_project_chat_renders_user_interjection_content(tmp_path):
    # 실제 사용자 zip으로 검증하다 발견한 버그: user_interjection 블록의 실제 텍스트는
    # block['text']/block['content']가 아니라 block['message']['content']에 있다
    # (실제 스키마: {"type": "user_interjection", "message": {"role": "user",
    # "content": "...", "attachments": [...]}}). 잘못된 키를 읽으면 조용히 빈 문자열을
    # 반환해서 중간에 사용자가 끼어든 실제 발화가 통째로 사라진다.
    data_dir = tmp_path / "data"
    assistant_msg = {
        "uuid": "a-2",
        "role": "assistant",
        "content": {
            "contentBlocks": [
                {"type": "text", "text": "여름 팔레트를 분홍으로 바꿨습니다."},
                {
                    "type": "user_interjection",
                    "message": {
                        "id": "u-int-1",
                        "role": "user",
                        "content": "아 여름 색깔 분홍계열로 금방 또 바뀌었네...",
                        "attachments": [],
                        "timestamp": "2026-06-19T12:10:00.731Z",
                    },
                },
            ],
            "timestamp": "2026-06-19T11:05:00.000000Z",
        },
    }
    _write_design_chat(data_dir, "chat-interject", "Jamissue", [_plain_user_message(), assistant_msg])
    result_dir = tmp_path / "result"

    convert(data_dir, result_dir, dry_run=False)

    text = (result_dir / "Jamissue" / "chat-interject.md").read_text(encoding="utf-8")
    assert "아 여름 색깔 분홍계열로 금방 또 바뀌었네" in text


def test_convert_mixes_standalone_and_project_chats(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write(data_dir, "conversations.json", [_standalone_conversation(uuid="conv-solo")])
    _write_design_chat(data_dir, "chat-proj", "Jamissue", [_plain_user_message(), _agentic_assistant_message()])
    result_dir = tmp_path / "result"

    stats = convert(data_dir, result_dir, dry_run=False)

    assert stats.sessions_found == 2
    assert (result_dir / "conv-solo.md").exists()
    assert (result_dir / "Jamissue" / "chat-proj.md").exists()
