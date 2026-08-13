"""벤더 공통 frontmatter + callout 마크다운 조립.

각 벤더 파서는 turn을 {'role': 'user'|'assistant', 'text': str, 'time_str': str,
'after_md': str (선택)} 딕셔너리 리스트로 정규화한 뒤 build_session_markdown()에 넘긴다.
'after_md'는 해당 callout 바로 뒤에 그대로 삽입된다 (예: Gemini의 첨부파일 블록처럼
callout 밖에 별도로 렌더링해야 하는 내용용).

frontmatter의 content_hash는 upsert 판단(common/upsert.py)에 쓰인다 — 원본(JSON/HTML)과
우리가 만드는 마크다운은 형식이 전혀 달라 직접 비교할 수 없으므로, 대신 "이 렌더러가 지금
만든 본문"과 "지난번에 이 렌더러가 만들어 저장해둔 본문"을 비교한다. 같은 turns/title이
들어가면 build_session_markdown()은 항상 같은 본문을 만드는 순수 함수이므로, 본문 해시
자체가 소스 상태의 지문 역할을 한다.

각 callout 바로 앞에는 turn_index/role/parent_turn_index/has_attachment를 담은 HTML
주석을 심는다. RAG 청킹 파이프라인이 "이게 질문인지 답변인지", "이 답변이 어느 질문에
대한 것인지"를 callout 문법([!question] vs [!tip])이나 "다음 질문 직전까지" 같은 순서
휴리스틱으로 추론하지 않고 바로 읽어갈 수 있게 하기 위함이다(ChatGPT는 연속 사용자
메시지나 응답 없는 마지막 질문이 가능해서 순서 휴리스틱만으로는 안전하지 않다). HTML
주석은 Obsidian 미리보기에는 안 보이므로 사용자가 보는 화면에는 영향이 없다.
"""

import hashlib
import json
import re

from .text import format_callout, yaml_quote

_CONTENT_HASH_LINE_RE = re.compile(r'^content_hash:\s*(\S+)\s*$', re.MULTILINE)


def _turn_comment(turn_index, role, parent_turn_index, has_attachment):
    payload = {
        "turn_index": turn_index,
        "role": role,
        "parent_turn_index": parent_turn_index,
        "has_attachment": has_attachment,
    }
    return f"<!-- turn: {json.dumps(payload, ensure_ascii=False)} -->\n"


def build_session_markdown(vendor_tag, vendor_label, title, session_id, url, date_str, turns,
                            turns_count=None):
    """turns_count: frontmatter에 기록할 '턴' 개수. 벤더마다 턴의 정의가 다르므로
    (ChatGPT는 메시지 1개 = 1턴, Gemini는 질문+응답 쌍 = 1턴) 명시적으로 넘기지 않으면
    len(turns)(렌더링할 callout 블록 개수)로 대체한다.

    반환값: (md, content_hash) 튜플."""
    if turns_count is None:
        turns_count = len(turns)

    body = f"# {title}\n\n"
    last_user_index = None
    for turn_index, turn in enumerate(turns):
        time_str = turn['time_str']
        role = turn['role']
        parent_turn_index = None if role == 'user' else last_user_index
        has_attachment = bool(turn.get('after_md'))
        body += _turn_comment(turn_index, role, parent_turn_index, has_attachment)
        if role == 'user':
            body += f"> [!question]- User ({time_str})\n{format_callout(turn['text'])}\n\n"
            last_user_index = turn_index
        else:
            body += f"> [!tip]- {vendor_label} ({time_str})\n{format_callout(turn['text'])}\n\n"
        after_md = turn.get('after_md')
        if after_md:
            body += after_md

    # frontmatter의 다른 필드(date, turns_count 등)는 전부 같은 turns/title에서 파생되므로
    # 본문이 안 바뀌면 그것들도 안 바뀐다 — frontmatter까지 만든 뒤 해시를 계산하는 순환을
    # 피하려고 본문만 해시한다.
    content_hash = hashlib.sha256(body.encode('utf-8')).hexdigest()[:16]

    title_yaml = yaml_quote(title)
    frontmatter = (
        "---\n"
        f'title: "{title_yaml}"\n'
        f'session_id: "{session_id}"\n'
        f"url: {url}\n"
        f"date: {date_str}\n"
        f"turns_count: {turns_count}\n"
        f"content_hash: {content_hash}\n"
        "tags:\n"
        f"  - {vendor_tag}\n"
        "  - chat-session\n"
        "---\n\n"
    )

    return frontmatter + body, content_hash


def extract_content_hash(text):
    """기존 .md 파일 텍스트에서 frontmatter의 content_hash 값을 읽어온다.
    없거나 형식이 다르면 None (PyYAML 없이 stdlib re만 사용 — 값 하나 읽자고
    이 프로젝트에 없던 YAML 파서 의존성을 새로 들일 필요는 없다)."""
    m = _CONTENT_HASH_LINE_RE.search(text)
    return m.group(1) if m else None
