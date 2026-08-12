"""벤더 공통 frontmatter + callout 마크다운 조립.

각 벤더 파서는 turn을 {'role': 'user'|'assistant', 'text': str, 'time_str': str,
'after_md': str (선택)} 딕셔너리 리스트로 정규화한 뒤 build_session_markdown()에 넘긴다.
'after_md'는 해당 callout 바로 뒤에 그대로 삽입된다 (예: Gemini의 첨부파일 블록처럼
callout 밖에 별도로 렌더링해야 하는 내용용).
"""

from .text import format_callout, yaml_quote


def build_session_markdown(vendor_tag, vendor_label, title, session_id, url, date_str, turns,
                            turns_count=None):
    """turns_count: frontmatter에 기록할 '턴' 개수. 벤더마다 턴의 정의가 다르므로
    (ChatGPT는 메시지 1개 = 1턴, Gemini는 질문+응답 쌍 = 1턴) 명시적으로 넘기지 않으면
    len(turns)(렌더링할 callout 블록 개수)로 대체한다."""
    if turns_count is None:
        turns_count = len(turns)
    title_yaml = yaml_quote(title)
    md = (
        "---\n"
        f'title: "{title_yaml}"\n'
        f'session_id: "{session_id}"\n'
        f"url: {url}\n"
        f"date: {date_str}\n"
        f"turns_count: {turns_count}\n"
        "tags:\n"
        f"  - {vendor_tag}\n"
        "  - chat-session\n"
        "---\n\n"
        f"# {title}\n\n"
    )

    for turn in turns:
        time_str = turn['time_str']
        if turn['role'] == 'user':
            md += f"> [!question]- User ({time_str})\n{format_callout(turn['text'])}\n\n"
        else:
            md += f"> [!tip]- {vendor_label} ({time_str})\n{format_callout(turn['text'])}\n\n"
        after_md = turn.get('after_md')
        if after_md:
            md += after_md

    return md
