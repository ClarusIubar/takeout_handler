"""LM Studio(OpenAI 호환 REST API)용 최소 클라이언트. stdlib(urllib.request)만 쓴다 —
mcp_server/처럼 이 저장소의 opt-in 기능 하나가 새 런타임 의존성을 요구하지 않게 한다.

이 모듈은 mcp_server.server가 만드는 mcp.types.Tool을 OpenAI function-calling
tools 파라미터로 바꾸고, LM Studio 응답에서 tool_calls를 파싱하는 것까지만 담당한다.
실제 tool 실행/채점은 eval/harness.py의 몫이다.
"""

import json
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "http://localhost:1234/v1"
DEFAULT_MODEL = "gemma-4-12b-it"
# 모델 선택 이력 (전부 실측 근거):
# 1) gpt-oss-20b — 1년 전 모델이라 툴체인이 구식일 수 있다는 우려로 시작은 했지만,
#    실제 문제는 모델이 아니라 non-streaming 요청에 대한 LM Studio 자체의 내부
#    타임아웃(~300초, 공개 이슈로 확인)이었다 — 그 자체는 스트리밍 전환으로 해결됨.
# 2) meta/muse-glimmer — LM Studio 네이티브 API에 capabilities 필드가 없어 tool-calling
#    미지원을 의심했으나 단발 테스트는 통과했다. 하지만 10회 반복 통제 실험(완전히 동일한
#    요청)에서 7/10(70%)이 "The model produced output that does not match the expected
#    peg-native format" 에러로 스트림이 중단됨 — 세션 누적/부하와 무관한, 모델 자체의
#    tool-calling 문법 준수 실패였다. eval 용도로 신뢰할 수 없어 폐기.
#    (이 조사 과정에서 이 에러를 조용히 삼키고 빈 문자열을 반환하던 진짜 버그도 발견해 고침
#    — LMStudioStreamError 참고.)
# 3) gemma-4-12b-it — capabilities에 tool_use가 명시돼 있고, max_context_length와 동일한
#    131072로 로드됨(여유 충분). 하한 탐침으로 현재 기본값.
# 4) qwen/qwen3.8-27b (80128 컨텍스트) — 상한 참조로 추가. gemma를 대체하는 게 아니라
#    브래킷의 반대쪽이다.
#
# 왜 두 모델인가 — 모델 성능은 양방향으로 측정을 망친다:
#   상한: 강한 모델은 모호한 tool 설명도 추론력으로 덮어버려 결함을 가린다(거짓 음성).
#   하한: 너무 약한 모델은 멀쩡한 인터페이스도 못 따라와 정상을 결함으로 만든다(거짓 양성).
# 단일 모델로는 어느 쪽도 판정할 수 없고, 두 모델이 갈리는 지점 자체가 진단 신호다:
#   둘 다 실패 → 인터페이스 결함 가능성 높음 / gemma만 실패 → 모델 한계(인터페이스 건드리지 말 것)
# 운영 규칙: gemma 단독 실패는 크로스 체크 전까지 인터페이스 결함의 근거로 쓰지 않는다.
# 실측 근거(keyword_search, 동일 코드·동일 tool description·동일 중립 프롬프트):
#   gemma-4-12b-it 0/5(검증용 get_session 호출 0회) vs qwen/qwen3.8-27b 3/3(후보 2건을
#   매번 다 읽고 decoy 정확히 배제).
#
# 같은 계열 더 소형인 gemma-4-e4b-it은 쓰지 않는다 — gemma-4-12b-it이 이미 tool
# description 수준의 지침을 행동으로 옮기지 못해 하한선에 걸쳐 있거나 그 아래다. 더
# 작은 모델은 하한을 더 깊이 위반해 거짓 양성만 늘린다(인터페이스 품질이 아니라 모델의
# 무능을 측정하게 됨). 자세한 근거는 eval/README.md "상한/하한 브래킷" 절 참고.


class LMStudioStreamError(RuntimeError):
    """LM Studio가 스트림 도중 SSE error 청크로 요청을 중단시켰을 때 던진다. 실측:
    meta/muse-glimmer가 tool-calling 문법(grammar)에 안 맞는 출력을 내면 LM Studio가
    "The model produced output that does not match the expected peg-native format"와
    함께 스트림을 끊는다 — 이걸 조용히 무시하면 실패가 빈 문자열 성공처럼 보여서
    eval 결과를 왜곡한다(실제로 그렇게 여러 태스크가 답이 없는 채로 "PASS"할 뻔했다)."""


def _post_json(url, payload, timeout):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_json_streaming(url, payload, timeout):
    req = urllib.request.Request(
        url,
        data=json.dumps({**payload, "stream": True}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return _accumulate_stream_chunks(_iter_sse_lines(resp))


def _iter_sse_lines(lines):
    """OpenAI 스타일 SSE 스트림(`data: {...}\\n` 줄들, `data: [DONE]`으로 종료)에서
    JSON 청크만 뽑아낸다. keep-alive 주석 줄(`: ...`)이나 빈 줄은 건너뛴다."""
    for raw_line in lines:
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        line = line.strip()
        if not line or not line.startswith("data:"):
            continue
        data = line[len("data:"):].strip()
        if data == "[DONE]":
            return
        yield json.loads(data)


def _accumulate_stream_chunks(chunks):
    """스트리밍 delta 청크들을 비-스트리밍 응답과 같은 모양(choices[0].message)으로
    합친다 — extract_tool_calls()/assistant_message()가 스트리밍 여부와 무관하게
    그대로 동작하게 하기 위함. tool_calls는 delta.index 기준으로 누적한다(OpenAI
    스펙: 이름은 첫 청크에서 한 번에, arguments는 여러 청크에 걸쳐 문자열로 이어붙여
    옴)."""
    content_parts = []
    reasoning_parts = []
    reasoning_key = "reasoning"
    tool_calls_by_index = {}
    finish_reason = None
    role = "assistant"

    for chunk in chunks:
        if "error" in chunk:
            raise LMStudioStreamError(chunk["error"].get("message") or str(chunk["error"]))
        choices = chunk.get("choices")
        if not choices:
            # usage-only 등 마지막 메타데이터 프레임 — 무시.
            continue
        choice = choices[0]
        if choice.get("finish_reason"):
            finish_reason = choice["finish_reason"]
        delta = choice.get("delta") or {}
        if delta.get("role"):
            role = delta["role"]
        if delta.get("content"):
            content_parts.append(delta["content"])
        for key in ("reasoning", "reasoning_content"):
            if delta.get(key):
                reasoning_key = key
                reasoning_parts.append(delta[key])
        for tc_delta in delta.get("tool_calls") or []:
            idx = tc_delta.get("index", 0)
            entry = tool_calls_by_index.setdefault(idx, {
                "id": None, "type": "function", "function": {"name": "", "arguments": ""},
            })
            if tc_delta.get("id"):
                entry["id"] = tc_delta["id"]
            if tc_delta.get("type"):
                entry["type"] = tc_delta["type"]
            fn_delta = tc_delta.get("function") or {}
            if fn_delta.get("name"):
                entry["function"]["name"] += fn_delta["name"]
            if fn_delta.get("arguments"):
                entry["function"]["arguments"] += fn_delta["arguments"]

    message = {"role": role, "content": "".join(content_parts)}
    if reasoning_parts:
        message[reasoning_key] = "".join(reasoning_parts)
    if tool_calls_by_index:
        message["tool_calls"] = [tool_calls_by_index[i] for i in sorted(tool_calls_by_index)]

    return {"choices": [{"index": 0, "message": message, "finish_reason": finish_reason, "logprobs": None}]}


def _get_json(url, timeout):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


DEFAULT_TIMEOUT = 600  # 로컬 모델 + 큰 컨텍스트 슬롯(수만 토큰)은 응답에 수 분씩 걸릴 수 있다.
# 실측: 90112 토큰 컨텍스트로 로드된 로컬 모델이 non-streaming 요청에서 "Channel Error"/
# "Engine protocol predict request failed: fetch failed"로 반복적으로 끊겼다 — 알고 보니
# 이건 이 클라이언트의 타임아웃과 무관하게 LM Studio 자신의 내부 엔진 채널이 non-streaming
# 요청에 대해 더 짧은 자체 타임아웃(공개 이슈들에서 ~300초로 보고됨)을 걸기 때문이었다.
# 그래서 chat_completion()은 기본적으로 스트리밍(stream=True)을 쓴다 — 청크가 주기적으로
# 오가야 그 내부 채널이 죽지 않는다.


def chat_completion(messages, tools=None, model=DEFAULT_MODEL, base_url=DEFAULT_BASE_URL,
                     tool_choice="auto", temperature=0.1, timeout=DEFAULT_TIMEOUT, stream=True):
    """POST /v1/chat/completions. tools가 없으면 tool_choice도 안 보낸다(순수 텍스트 응답용).
    stream=True(기본값)면 SSE로 받아 비-스트리밍과 동일한 모양으로 재조립한다 — 위
    DEFAULT_TIMEOUT 설명 참고. stream=False는 디버깅/비교용으로만 남겨둔다."""
    payload = {"model": model, "messages": messages, "temperature": temperature}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice
    if stream:
        return _post_json_streaming(f"{base_url}/chat/completions", payload, timeout)
    return _post_json(f"{base_url}/chat/completions", payload, timeout)


def extract_tool_calls(response):
    """response["choices"][0]["message"].tool_calls -> [{"id","name","arguments": dict}, ...].
    일부 모델(gpt-oss는 "reasoning", meta/muse-glimmer는 "reasoning_content")이
    사고 과정을 담은 필드를 덧붙이는데, 여기서 아예 안 읽으므로 필드 이름과 무관하게
    자동으로 무시된다."""
    message = response["choices"][0]["message"]
    calls = []
    for tc in message.get("tool_calls") or []:
        fn = tc["function"]
        raw_args = fn.get("arguments") or ""
        calls.append({
            "id": tc.get("id"),
            "name": fn["name"],
            "arguments": json.loads(raw_args) if raw_args else {},
        })
    return calls


def assistant_message(response):
    """다음 턴 messages 목록에 그대로 append할 원본 assistant 메시지 dict
    (tool_calls 필드가 남아있어야 OpenAI 스타일 멀티턴 히스토리로 유효하다)."""
    return response["choices"][0]["message"]


def mcp_tool_to_openai(tool):
    """mcp.types.Tool -> OpenAI chat completions 'tools' 파라미터의 항목 하나."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


def check_context_length(model=DEFAULT_MODEL, base_url=DEFAULT_BASE_URL, min_tokens=8000, timeout=10):
    """LM Studio 네이티브 API(/api/v0/models)로 현재 로드된 모델의 loaded_context_length를
    조회한다. 하네스를 죽이지는 않고 (모델을 재로딩해야 하는 문제라 하네스가 고칠 수 없음)
    부족해 보이면 경고 문자열을 반환한다 — 없으면 None.

    base_url은 보통 ".../v1"로 끝나므로, 네이티브 API 루트를 얻기 위해 그 접미사를 뗀다."""
    native_root = base_url[:-len("/v1")] if base_url.endswith("/v1") else base_url
    try:
        data = _get_json(f"{native_root}/api/v0/models", timeout)
    except (urllib.error.URLError, OSError, ValueError):
        return f"[경고] {native_root}/api/v0/models 조회 실패 — LM Studio가 떠 있는지 확인하세요."

    entry = next((m for m in data.get("data", []) if m.get("id") == model), None)
    if entry is None:
        return f"[경고] 모델 '{model}'이 LM Studio에 로드돼 있지 않습니다."

    loaded = entry.get("loaded_context_length")
    if loaded is not None and loaded < min_tokens:
        return (f"[경고] {model}의 loaded_context_length={loaded}가 최소 권장치({min_tokens}) "
                f"미만입니다. tool 스키마 + 멀티라운드 대화가 넘칠 수 있습니다 — "
                f"LM Studio에서 더 큰 컨텍스트로 재로딩을 고려하세요.")
    return None
