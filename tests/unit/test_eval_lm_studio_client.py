# eval/lm_studio_client.py의 순수 파싱/변환 함수만 테스트한다. 실제 LM Studio HTTP
# 호출은 여기서 검증하지 않는다(비결정적 LLM 출력이라 자동 유닛테스트 대상이 아님 —
# eval/README.md에 수동 실행 방법을 문서화).
from dataclasses import dataclass

from eval.lm_studio_client import assistant_message, extract_tool_calls, mcp_tool_to_openai


def test_extract_tool_calls_parses_json_arguments():
    response = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "",
                "reasoning": "이건 무시돼야 함",
                "tool_calls": [{
                    "type": "function",
                    "id": "call_1",
                    "function": {"name": "get_weather", "arguments": '{"location": "Boston"}'},
                }],
            },
        }],
    }

    calls = extract_tool_calls(response)

    assert calls == [{"id": "call_1", "name": "get_weather", "arguments": {"location": "Boston"}}]


def test_extract_tool_calls_returns_empty_list_when_no_tool_calls():
    response = {"choices": [{"message": {"role": "assistant", "content": "그냥 답변"}}]}
    assert extract_tool_calls(response) == []


def test_extract_tool_calls_handles_empty_arguments_string():
    response = {
        "choices": [{"message": {"tool_calls": [
            {"id": "c1", "function": {"name": "list_sessions", "arguments": ""}},
        ]}}],
    }
    calls = extract_tool_calls(response)
    assert calls == [{"id": "c1", "name": "list_sessions", "arguments": {}}]


def test_assistant_message_returns_raw_message_dict():
    response = {"choices": [{"message": {"role": "assistant", "content": "hi", "reasoning": "..."}}]}
    msg = assistant_message(response)
    assert msg == {"role": "assistant", "content": "hi", "reasoning": "..."}


@dataclass
class _FakeMcpTool:
    name: str
    description: str
    input_schema: dict


def test_mcp_tool_to_openai_converts_shape():
    tool = _FakeMcpTool(
        name="list_sessions",
        description="세션 목록을 반환한다.",
        input_schema={"type": "object", "properties": {"vendor": {"type": "string"}}},
    )

    openai_tool = mcp_tool_to_openai(tool)

    assert openai_tool == {
        "type": "function",
        "function": {
            "name": "list_sessions",
            "description": "세션 목록을 반환한다.",
            "parameters": {"type": "object", "properties": {"vendor": {"type": "string"}}},
        },
    }
