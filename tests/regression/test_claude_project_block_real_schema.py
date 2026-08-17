# 실제 사용자 zip 21개 결과물을 원본 데이터의 블록 타입별 개수와 대조하는 전수 검토를
# 하다가 발견한 두 가지 조용한 콘텐츠 유실 버그. 둘 다 처음 짠 코드가 design_chats/
# *.json의 실제 필드 이름을 잘못 추측했는데, 렌더러가 예외 없이 그냥 빈 문자열을
# 반환해서(vendors/base 전반의 "미지 타입은 조용히 스킵" 설계와 같은 방식으로) 실패가
# 전혀 눈에 띄지 않았다 — 유닛 테스트도 이 잘못된 가정을 그대로 픽스처에 박아놔서
# 통과하고 있었다. 두 버그 다 실제 원본 JSON을 직접 열어서 진짜 키 이름을 확인한
# 뒤에야 잡혔다.
import pytest

from vendors.claude import convert

pytestmark = pytest.mark.regression


def _write_design_chat(dir_path, uuid, messages):
    (dir_path / "design_chats").mkdir(parents=True, exist_ok=True)
    payload = {
        "uuid": uuid,
        "title": "Chat",
        "project": {"uuid": "proj-1", "name": "Real Schema Project"},
        "created_at": "2026-06-19T11:00:00.000000Z",
        "messages": messages,
    }
    import json
    (dir_path / "design_chats" / f"{uuid}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def test_thinking_block_reads_text_key_not_thinking_key(tmp_path):
    # 실제 스키마: {"type": "thinking", "text": "..."} — conversations.json 쪽의
    # {"type": "thinking", "thinking": "..."}와 키 이름이 다르다. 실사용 데이터에서는
    # 이 필드가 늘 빈 문자열이었지만("thinking" 키가 아예 없는 게 아니라 "text" 키가
    # 있고 값이 비어있는 형태), 나중에 값이 채워진 export가 오면 놓치면 안 된다.
    data_dir = tmp_path / "data"
    msg = {
        "uuid": "a-1", "role": "assistant",
        "content": {
            "contentBlocks": [
                {"type": "thinking", "text": "실제 키는 text다."},
            ],
            "timestamp": "2026-06-19T11:05:00.000000Z",
        },
    }
    _write_design_chat(data_dir, "chat-real-thinking", [msg])
    result_dir = tmp_path / "result"

    convert(data_dir, result_dir, dry_run=False)

    text = (result_dir / "Real Schema Project" / "chat-real-thinking.md").read_text(encoding="utf-8")
    assert "실제 키는 text다." in text


def test_thinking_block_with_empty_text_is_skipped_not_crashed(tmp_path):
    # 실사용 데이터의 실제 형태: {"type": "thinking", "text": ""} — 88개 전부 이
    # 모양이었다. 빈 값이면 렌더링할 게 없으니 스킵하는 게 맞고, 이 자체는 버그가
    # 아니다 — 다른 텍스트가 있는 메시지라면 대화 전체가 empty_skipped로 빠지면 안 된다.
    data_dir = tmp_path / "data"
    msg = {
        "uuid": "a-1", "role": "assistant",
        "content": {
            "contentBlocks": [
                {"type": "thinking", "text": ""},
                {"type": "text", "text": "실제 응답"},
            ],
            "timestamp": "2026-06-19T11:05:00.000000Z",
        },
    }
    _write_design_chat(data_dir, "chat-empty-thinking", [msg])
    result_dir = tmp_path / "result"

    stats = convert(data_dir, result_dir, dry_run=False)

    assert stats.empty_skipped == 0
    text = (result_dir / "Real Schema Project" / "chat-empty-thinking.md").read_text(encoding="utf-8")
    assert "실제 응답" in text
    assert "🤔" not in text


def test_user_interjection_block_reads_nested_message_content(tmp_path):
    # 실제 스키마: {"type": "user_interjection", "message": {"role": "user",
    # "content": "...", "attachments": [...]}} — 실사용 데이터에 6개 있었는데
    # block 최상위의 'text'/'content' 키를 찾던 예전 코드는 전부 빈 문자열을
    # 반환해서 에이전틱 세션 도중 사용자가 끼어든 실제 발화가 통째로 사라졌었다.
    data_dir = tmp_path / "data"
    msg = {
        "uuid": "a-1", "role": "assistant",
        "content": {
            "contentBlocks": [
                {
                    "type": "user_interjection",
                    "message": {
                        "role": "user",
                        "content": "잠깐, 그거 말고 다른 걸로",
                        "attachments": [],
                        "timestamp": "2026-06-19T12:10:00.000000Z",
                    },
                },
            ],
            "timestamp": "2026-06-19T11:05:00.000000Z",
        },
    }
    _write_design_chat(data_dir, "chat-real-interjection", [msg])
    result_dir = tmp_path / "result"

    convert(data_dir, result_dir, dry_run=False)

    text = (result_dir / "Real Schema Project" / "chat-real-interjection.md").read_text(encoding="utf-8")
    assert "잠깐, 그거 말고 다른 걸로" in text
