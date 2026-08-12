from common.markdown_safety import ensure_fences_closed, make_fence, normalize_fences, open_fence_length


def test_make_fence_defaults_to_three_backticks():
    assert make_fence("plain code, no backticks") == "```"


def test_make_fence_grows_past_content_backticks():
    # 본문에 4연속 backtick이 있으면 펜스는 그보다 길어야 CommonMark상 안전하다.
    assert make_fence("some ```` inside") == "`````"


def test_open_fence_length_detects_unclosed_fence():
    text = "```python\nprint(1)\n"
    assert open_fence_length(text) == 3


def test_open_fence_length_none_when_closed():
    text = "```python\nprint(1)\n```\n"
    assert open_fence_length(text) is None


def test_ensure_fences_closed_appends_closing_fence():
    text = "```python\nprint(1)\n"
    result = ensure_fences_closed(text)
    assert open_fence_length(result) is None
    assert result.rstrip("\n").endswith("```")


def test_normalize_fences_forces_newline_after_bare_triple_backtick():
    # 모델이 예시로 언급한 ``` 뒤에 바로 문장이 이어지면 언어 태그로 오인돼
    # 그 뒤 전체가 코드블록으로 삼켜진다 -> 줄바꿈을 강제해야 한다.
    text = "```이건 코드블록이 아니라 그냥 백틱 얘기입니다"
    result = normalize_fences(text)
    assert result.startswith("```\n이건 코드블록이 아니라")


def test_normalize_fences_preserves_real_language_tag():
    text = "```python\nprint(1)\n```"
    assert normalize_fences(text) == text
