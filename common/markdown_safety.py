"""ChatGPT/Gemini 두 벤더 convert.py에서 100% 동일하게 중복돼 있던 마크다운 안전장치."""

import re

LANG_TAG_RE = re.compile(r'^[a-zA-Z0-9_+-]{0,20}$')


def make_fence(text):
    """content 안에 포함된 가장 긴 backtick 연속 길이보다 긴 펜스를 골라서
    (CommonMark 규칙) 코드 안에 예시로 ``` 가 들어있어도 안 깨지게 한다."""
    longest = 0
    run = 0
    for ch in text:
        if ch == '`':
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    return '`' * max(3, longest + 1)


def normalize_fences(text):
    """```로 시작하는데 뒤에 오는 게 언어 태그(짧은 식별자)가 아니면 줄바꿈을 강제한다.
    (모델 응답 본문 텍스트 자체에 리터럴 ``` 가 들어있는 경우 펜스가 안 닫혀서
    그 뒤 전체가 코드블록으로 삼켜지는 것을 방지)"""

    def repl(m):
        rest = m.group(1)
        if LANG_TAG_RE.match(rest):
            return m.group(0)
        return '```\n' + rest

    return re.sub(r'```([^\n]*)', repl, text)


def open_fence_length(text):
    """CommonMark 실제 규칙대로 라인 단위 상태머신을 돌려 마지막에 열린 채로
    남은 펜스의 backtick 길이를 반환한다 (닫혀있으면 None)."""
    state_len = None
    for line in text.split('\n'):
        m = re.match(r'^(`{3,})(.*)$', line)
        if not m:
            continue
        ticks, rest = m.group(1), m.group(2)
        if state_len is None:
            state_len = len(ticks)
        elif rest.strip() == '' and len(ticks) >= state_len:
            state_len = None
    return state_len


def ensure_fences_closed(text):
    """끝까지 열려있는 채로 남은 코드펜스가 있으면 마지막에 닫는 펜스를 하나 더 붙인다."""
    open_len = open_fence_length(text)
    if open_len is not None:
        text = text.rstrip('\n') + "\n" + ("`" * open_len) + "\n"
    return text
