# LM Studio가 non-streaming 요청에서 내부적으로 ~300초 타임아웃을 걸고 "Channel Error"
# ("Engine protocol predict request failed: fetch failed")로 끊는 걸 실제로 관찰했다 —
# 클라이언트 쪽 timeout(DEFAULT_TIMEOUT=600s)과 무관하게 서버 내부 채널이 먼저 죽는다.
# 알려진 해법은 스트리밍(stream: true)이라, SSE 청크를 비-스트리밍 응답과 같은 모양의
# message dict로 합치는 순수 로직만 여기서 검증한다(실제 HTTP는 라이브 LM Studio 필요).
import pytest

from eval.lm_studio_client import LMStudioStreamError, _accumulate_stream_chunks, _iter_sse_lines


def _chunk(delta, finish_reason=None):
    return {"choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}]}


def test_accumulate_plain_text_content():
    chunks = [
        _chunk({"role": "assistant", "content": ""}),
        _chunk({"content": "안녕"}),
        _chunk({"content": "하세요"}),
        _chunk({}, finish_reason="stop"),
    ]
    result = _accumulate_stream_chunks(chunks)
    message = result["choices"][0]["message"]
    assert message["content"] == "안녕하세요"
    assert result["choices"][0]["finish_reason"] == "stop"


def test_accumulate_reconstructs_single_tool_call_arguments():
    chunks = [
        _chunk({"role": "assistant", "content": ""}),
        _chunk({"tool_calls": [{"index": 0, "id": "call_1", "type": "function",
                                 "function": {"name": "list_sessions", "arguments": ""}}]}),
        _chunk({"tool_calls": [{"index": 0, "function": {"arguments": '{"vendor"'}}]}),
        _chunk({"tool_calls": [{"index": 0, "function": {"arguments": ':null}'}}]}),
        _chunk({}, finish_reason="tool_calls"),
    ]
    result = _accumulate_stream_chunks(chunks)
    message = result["choices"][0]["message"]
    assert message["tool_calls"] == [{
        "id": "call_1", "type": "function",
        "function": {"name": "list_sessions", "arguments": '{"vendor":null}'},
    }]
    assert result["choices"][0]["finish_reason"] == "tool_calls"


def test_accumulate_reconstructs_multiple_parallel_tool_calls_by_index():
    chunks = [
        _chunk({"role": "assistant", "content": ""}),
        _chunk({"tool_calls": [{"index": 0, "id": "call_1", "type": "function",
                                 "function": {"name": "search_sessions", "arguments": ""}}]}),
        _chunk({"tool_calls": [{"index": 1, "id": "call_2", "type": "function",
                                 "function": {"name": "get_session", "arguments": ""}}]}),
        _chunk({"tool_calls": [{"index": 0, "function": {"arguments": '{"query":"a"}'}}]}),
        _chunk({"tool_calls": [{"index": 1, "function": {"arguments": '{"session_id":"b"}'}}]}),
        _chunk({}, finish_reason="tool_calls"),
    ]
    result = _accumulate_stream_chunks(chunks)
    tool_calls = result["choices"][0]["message"]["tool_calls"]
    assert [c["function"]["name"] for c in tool_calls] == ["search_sessions", "get_session"]
    assert tool_calls[0]["function"]["arguments"] == '{"query":"a"}'
    assert tool_calls[1]["function"]["arguments"] == '{"session_id":"b"}'


def test_accumulate_collects_reasoning_field_under_original_key():
    chunks = [
        _chunk({"role": "assistant", "reasoning": "생각 중"}),
        _chunk({"reasoning": "...더 생각"}),
        _chunk({"content": "답변"}, finish_reason="stop"),
    ]
    result = _accumulate_stream_chunks(chunks)
    message = result["choices"][0]["message"]
    assert message["reasoning"] == "생각 중...더 생각"
    assert message["content"] == "답변"


def test_accumulate_no_tool_calls_key_when_none_streamed():
    chunks = [_chunk({"role": "assistant", "content": "그냥 답"}, finish_reason="stop")]
    result = _accumulate_stream_chunks(chunks)
    assert "tool_calls" not in result["choices"][0]["message"]


def test_accumulate_raises_on_error_chunk_instead_of_returning_empty():
    # 실측: meta/muse-glimmer가 tool-calling 문법(peg-native format)에 안 맞는 출력을
    # 내면 LM Studio가 스트림 중간에 "error" 키를 담은 청크를 보내고 끊는다. 예전엔
    # "choices" 키가 없다는 이유로 이걸 그냥 무시해서 예외 없이 빈 문자열을 반환했다 —
    # 실패를 조용히 성공처럼 보이게 만드는 버그였다. 이젠 명시적으로 예외를 던져야 한다.
    chunks = [
        _chunk({"role": "assistant", "reasoning_content": "생각 중"}),
        {"error": {"message": 'Engine protocol predict stream returned an error: '
                               '{"code":500,"message":"The model produced output that '
                               'does not match the expected peg-native format",'
                               '"type":"server_error"}'}},
    ]
    with pytest.raises(LMStudioStreamError, match="peg-native format"):
        _accumulate_stream_chunks(chunks)


def test_accumulate_ignores_usage_only_chunk_without_error_key():
    # error 키가 없는 "choices 없음" 청크(usage-only 등)는 여전히 조용히 넘어가야 한다 —
    # 이건 정상적인 스트림 종료 프레임이다.
    chunks = [
        _chunk({"role": "assistant", "content": "정상 답변"}),
        {"id": "x", "usage": {"total_tokens": 10}},
        _chunk({}, finish_reason="stop"),
    ]
    result = _accumulate_stream_chunks(chunks)
    assert result["choices"][0]["message"]["content"] == "정상 답변"


def test_iter_sse_lines_parses_data_lines_and_stops_at_done():
    raw = [
        b'data: {"choices": [{"delta": {"content": "a"}}]}\n',
        b'\n',
        b'data: {"choices": [{"delta": {"content": "b"}}]}\n',
        b'data: [DONE]\n',
        b'data: {"choices": [{"delta": {"content": "should not appear"}}]}\n',
    ]
    chunks = list(_iter_sse_lines(raw))
    assert [c["choices"][0]["delta"]["content"] for c in chunks] == ["a", "b"]


def test_accumulate_skips_chunks_without_choices():
    # LM Studio(그리고 다른 OpenAI 호환 서버들)가 스트림 끝에 usage-only 프레임처럼
    # "choices"가 없거나 빈 리스트인 청크를 보낼 수 있다 — 무시하고 죽지 않아야 한다.
    chunks = [
        _chunk({"role": "assistant", "content": "안녕"}),
        {"id": "x", "usage": {"total_tokens": 10}},  # choices 키 자체가 없음
        {"choices": []},  # choices가 빈 리스트
        _chunk({}, finish_reason="stop"),
    ]
    result = _accumulate_stream_chunks(chunks)
    assert result["choices"][0]["message"]["content"] == "안녕"
    assert result["choices"][0]["finish_reason"] == "stop"


def test_iter_sse_lines_ignores_non_data_lines():
    raw = [b': keep-alive comment\n', b'data: {"choices": [{"delta": {"content": "x"}}]}\n']
    chunks = list(_iter_sse_lines(raw))
    assert len(chunks) == 1
