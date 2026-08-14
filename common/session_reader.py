"""session_markdown.py::build_session_markdown()의 역함수.

렌더링된 .md 파일(frontmatter + <!-- turn: {...} --> 주석이 심긴 callout 본문)을
다시 구조화 데이터(SessionRecord/TurnRecord)로 되돌린다. 이 프로젝트가 직접 만드는
포맷이라 YAML 파서 의존성을 새로 들이지 않고 extract_content_hash()와 같은 방식으로
stdlib re/json만 사용한다.
"""

import json
import re
from dataclasses import dataclass, field

_FRONTMATTER_RE = re.compile(r'\A---\n(.*?)\n---\n\n(.*)\Z', re.DOTALL)
_FIELD_LINE_RE = re.compile(r'^(\w+):\s*(.*)$')
_TAG_LINE_RE = re.compile(r'^  - (.*)$')
_TURN_COMMENT_RE = re.compile(r'<!-- turn: (\{.*?\}) -->\n')
_CALLOUT_HEADER_RE = re.compile(r'\A> \[!(?:question|tip)\]-\s+.*?\s+\((?P<time>.*?)\)\n')


@dataclass
class TurnRecord:
    turn_index: int
    role: str
    parent_turn_index: int | None
    has_attachment: bool
    time_str: str
    text: str


@dataclass
class SessionRecord:
    vendor_tag: str
    session_id: str
    title: str
    url: str
    date: str
    turns_count: int
    content_hash: str
    tags: list = field(default_factory=list)
    turns: list = field(default_factory=list)


def _unescape_yaml_quoted(raw):
    """text.yaml_quote()의 역변환: 따옴표를 벗기고 이스케이프를 되돌린다."""
    if raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1]
    return raw.replace('\\"', '"').replace('\\\\', '\\')


def _parse_frontmatter(fm_text):
    fields = {}
    tags = []
    lines = fm_text.split('\n')
    i = 0
    while i < len(lines):
        m = _FIELD_LINE_RE.match(lines[i])
        if not m:
            i += 1
            continue
        key, val = m.group(1), m.group(2)
        if key == 'tags':
            i += 1
            while i < len(lines):
                tm = _TAG_LINE_RE.match(lines[i])
                if not tm:
                    break
                tags.append(tm.group(1).strip())
                i += 1
            continue
        fields[key] = val
        i += 1
    return fields, tags


def _parse_turns(body):
    turns = []
    for cm in _TURN_COMMENT_RE.finditer(body):
        meta = json.loads(cm.group(1))
        rest = body[cm.end():]
        hm = _CALLOUT_HEADER_RE.match(rest)
        if not hm:
            raise ValueError(f"turn {meta.get('turn_index')}: callout header를 찾지 못함")

        text_lines = []
        for line in rest[hm.end():].split('\n'):
            if not line.startswith('> '):
                break
            text_lines.append(line[2:])

        turns.append(TurnRecord(
            turn_index=meta['turn_index'],
            role=meta['role'],
            parent_turn_index=meta['parent_turn_index'],
            has_attachment=meta['has_attachment'],
            time_str=hm.group('time'),
            text='\n'.join(text_lines),
        ))
    return turns


def parse_session_markdown(text, vendor_tag):
    """build_session_markdown()이 만든 마크다운 텍스트를 SessionRecord로 역파싱한다."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("session markdown에 frontmatter가 없거나 형식이 다릅니다")
    fm_text, body = m.group(1), m.group(2)
    fields, tags = _parse_frontmatter(fm_text)

    return SessionRecord(
        vendor_tag=vendor_tag,
        session_id=_unescape_yaml_quoted(fields['session_id']),
        title=_unescape_yaml_quoted(fields['title']),
        url=fields['url'],
        date=fields['date'],
        turns_count=int(fields['turns_count']),
        content_hash=fields['content_hash'],
        tags=tags,
        turns=_parse_turns(body),
    )
