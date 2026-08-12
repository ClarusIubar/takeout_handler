"""ChatGPT/Gemini 두 벤더 convert.py에서 동일하게 중복돼 있던 텍스트 유틸리티."""

import re

URL_RE = re.compile(r'https?://\S+', re.IGNORECASE)


def clean_text(text):
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def first_sentence(text):
    """텍스트 첫 문장을 마침표/개행 기준으로 잘라낸다. URL 안의 마침표는 무시."""
    text = (text or "").strip()
    if not text:
        return "(빈 프롬프트)"

    url_spans = [(m.start(), m.end()) for m in URL_RE.finditer(text)]

    def inside_url(pos):
        return any(s <= pos < e for s, e in url_spans)

    cut = None
    for m in re.finditer(r'[.!?。！？\n]', text):
        if not inside_url(m.start()):
            cut = m.start()
            break

    s = text[:cut].strip() if cut is not None else text
    if not s:
        s = text.strip()
    return s[:150] if s else "(빈 프롬프트)"


def yaml_quote(text):
    return text.replace('\\', '\\\\').replace('"', '\\"')


def sanitize_filename(name, fallback="unknown"):
    clean = str(name).strip()
    clean = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', clean)
    return clean if clean else fallback


def format_callout(text):
    text = clean_text(text)
    if not text:
        return "> (내용 없음)"
    return '\n'.join(f"> {line}" for line in text.split('\n'))
