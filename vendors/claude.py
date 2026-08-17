"""Claude(Anthropic) 데이터 export -> 마크다운.

실제 사용자 zip을 조사해보니 두 갈래 스키마가 섞여 있다:

- conversations.json: 프로젝트에 안 묶인 일반 대화. 배열 하나에 전부 들어있고, 메시지는
  sender(human/assistant) + content(블록 배열: text/thinking/tool_use/tool_result/
  token_budget)로 claude.ai 웹 채팅 스키마를 그대로 따른다.
- design_chats/<uuid>.json: 프로젝트에 묶인 에이전틱("코워크") 세션 — 완전히 다른 스키마.
  이번 TSK-003-01에서는 conversations.json 경로만 다룬다 (TSK-003-02에서 이어서 추가).

첨부파일은 이 export에 실 바이너리가 전혀 없어서(참조 uuid/파일명만 있음) 항상
"원본 없음"으로 처리하는 얇은 리졸버 하나로 충분하다 (TSK-003-03).
"""

import json
from datetime import datetime
from pathlib import Path

from common.attachment_cache import BaseAttachmentResolver
from common.fs_discovery import is_junk_path, pick_primary
from common.markdown_safety import ensure_fences_closed, normalize_fences
from common.session_markdown import build_session_markdown
from common.text import first_sentence, sanitize_filename
from common.upsert import record_action, write_upsert
from vendors.base import ConvertStats

VENDOR_TAG = "claude"
VENDOR_LABEL = "Claude"

_MARKER_NAMES = ("conversations.json", "design_chats", "projects")


# ==========================================
# detect() / 후보 탐색
# ==========================================

def _find_claude_candidates(data_dir: Path):
    """data_dir 재귀 탐색으로 conversations.json 또는 design_chats/ 또는 projects/ 중
    하나라도 들어있는 서로 다른 부모 디렉터리를 전부 찾는다 (정크 경로 제외, 얕은 폴더
    먼저). vendors/chatgpt.py의 _find_conversation_candidates와 동일한 패턴.

    design_chats/projects는 아직 변환하지 않지만(TSK-003-02), export 전체(둘 중 하나만
    있어도 유효한 export)를 기준으로 감지해야 사용자가 conversations.json이 없는(예:
    프로젝트 대화만 있는) export를 넣었을 때도 "데이터 없음"으로 잘못 판정하지 않는다."""
    parents = set()
    for name in _MARKER_NAMES:
        for m in data_dir.rglob(name):
            if is_junk_path(m, data_dir):
                continue
            parents.add(m.parent)
    return sorted(parents, key=lambda p: len(p.relative_to(data_dir).parts))


def detect(data_dir: Path) -> bool:
    return bool(_find_claude_candidates(data_dir))


# ==========================================
# 첨부파일 (실 바이너리 없음 — 항상 "원본 없음")
# ==========================================

class _AttachmentResolver(BaseAttachmentResolver):
    """이 export엔 첨부파일 실 바이트가 전혀 없다 (uuid/파일명 참조만 있음). ChatGPT의
    .dat 블롭처럼 복사해올 원본이 없으므로 항상 missing으로 기록한다 — 나중에 바이너리가
    포함된 export를 받으면 resolve()만 교체하면 된다."""

    def resolve(self, file_id, hint_name=None):
        if file_id not in self._cache:
            self._cache[file_id] = None
        return None

    def describe(self, file_id, hint_name=None):
        self.resolve(file_id, hint_name=hint_name)
        label = hint_name or file_id
        return f"\n> ⚠️ 첨부파일 누락 (원본 export에 파일 없음): {label}\n"


def _describe_attachment_refs(resolver, attachments, files):
    """conversations.json 메시지의 attachments/files 필드(둘 다 {file_uuid,file_name}류
    참조)를 합쳐서 누락 안내 텍스트 청크 리스트로 만든다."""
    chunks = []
    for ref in list(attachments or []) + list(files or []):
        if not isinstance(ref, dict):
            continue
        file_id = ref.get('file_uuid') or ref.get('id') or ''
        name = ref.get('file_name') or ref.get('name') or file_id
        if not (file_id or name):
            continue
        chunks.append(resolver.describe(file_id or name, hint_name=name))
    return chunks


# ==========================================
# conversations.json (일반 대화) 파싱
# ==========================================

def _quote_lines(text):
    """여러 줄 문자열의 매 줄 앞에 '> '를 붙인다. 첫 줄에만 붙이면 outer
    format_callout()이 한 겹 더 씌울 때 첫 줄만 중첩 인용(> >)되고 나머지 줄은
    한 겹(>)만 남아 같은 블록 안에서 인용 깊이가 들쭉날쭉해진다."""
    return "\n".join(f"> {line}" for line in text.split("\n"))


def _render_thinking_block(block):
    text = block.get('thinking')
    return f"\n> 🤔 **Thinking**\n{_quote_lines(text)}\n" if isinstance(text, str) and text.strip() else ""


def _render_tool_use_block(block):
    name = block.get('name') or 'tool'
    input_ = block.get('input')
    input_str = json.dumps(input_, ensure_ascii=False) if input_ is not None else ""
    return f"\n> 🔧 **Tool: {name}**\n> ```\n{_quote_lines(input_str)}\n> ```\n"


def _render_tool_result_item(item):
    """tool_result.content의 항목 하나를 렌더링한다. 대부분은 {"text": "..."}
    (일반 텍스트든 knowledge/웹검색 결과든 'text' 키에 본문이 들어있어 그대로 뽑으면
    됨)이지만, 코드 실행 등으로 Claude가 만든 파일은 {"type": "local_resource",
    "file_path", "name"}처럼 텍스트가 아예 없는 형태로 온다 — 이 export엔 실 바이트가
    없어 내용은 못 넣어도 "파일이 생성됐다"는 사실 자체는 남겨야 조용히 사라지지 않는다."""
    if not isinstance(item, dict):
        return ""
    text = item.get('text')
    if isinstance(text, str) and text.strip():
        return text
    if item.get('type') == 'local_resource':
        name = item.get('name') or item.get('file_path') or 'file'
        path = item.get('file_path')
        label = f"{name} ({path})" if path and path != name else name
        return f"📄 파일 생성됨: {label}"
    return ""


def _render_tool_result_block(block):
    content = block.get('content')
    if isinstance(content, list):
        parts = [_render_tool_result_item(c) for c in content]
        text = "\n".join(p for p in parts if p)
    elif isinstance(content, str):
        text = content
    else:
        text = ""
    return f"\n> 📋 **Tool result**\n{_quote_lines(text)}\n" if text.strip() else ""


def _render_text_block(block, resolver=None):
    text = block.get('text')
    return text if isinstance(text, str) else ""


STANDALONE_BLOCK_RENDERERS = {
    'text': _render_text_block,
    'thinking': _render_thinking_block,
    'tool_use': _render_tool_use_block,
    'tool_result': _render_tool_result_block,
    # token_budget 등 그 외 타입은 아래 기본 분기에서 조용히 스킵된다.
}


def _render_standalone_message(msg, resolver):
    chunks = []
    for block in (msg.get('content') or []):
        if not isinstance(block, dict):
            continue
        renderer = STANDALONE_BLOCK_RENDERERS.get(block.get('type'))
        if renderer:
            chunks.append(renderer(block))
    chunks.extend(_describe_attachment_refs(resolver, msg.get('attachments'), msg.get('files')))

    text = "\n\n".join(c.strip() for c in chunks if isinstance(c, str) and c.strip())
    return ensure_fences_closed(normalize_fences(text.strip()))


def _parse_iso(ts):
    """Claude의 타임스탬프는 ISO8601 UTC 문자열이다. 여기서 시스템 로컬 타임존으로
    변환해둔다 — ChatGPT(datetime.fromtimestamp()가 epoch를 로컬로 변환)나 Gemini
    (Takeout HTML에 이미 KST로 찍혀 나옴)와 달리 UTC 그대로 두면, 같은 실제 시각인데
    벤더마다 frontmatter의 date/시간 표시가 몇 시간씩 어긋난다."""
    if not isinstance(ts, str) or not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
    except ValueError:
        return None
    return dt.astimezone()


def _local_date(ts):
    dt = _parse_iso(ts)
    return dt.date().isoformat() if dt else "unknown"


def _local_dt_str(ts):
    dt = _parse_iso(ts)
    return dt.strftime('%Y-%m-%d %H:%M:%S') if dt else "시간 미상"


def _load_standalone_conversations(data_dir):
    """conversations.json: 최상위가 대화 배열 하나. (대화 리스트, 파싱 실패 파일 수)."""
    path = data_dir / "conversations.json"
    if not path.exists():
        return [], 0
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except Exception as exc:
        print(f"[경고] {path.name} 파싱 실패: {exc}")
        return [], 1
    if not isinstance(data, list):
        print(f"[경고] {path.name}의 최상위 타입이 list가 아니라 {type(data).__name__}입니다 "
              "— 예상과 다른 export 형식일 수 있습니다.")
        return [], 1
    return [c for c in data if isinstance(c, dict)], 0


def _standalone_turns(conv, resolver):
    turns = []
    for msg in conv.get('chat_messages') or []:
        if not isinstance(msg, dict):
            continue
        role = 'user' if msg.get('sender') == 'human' else 'assistant'
        text = _render_standalone_message(msg, resolver)
        if not text:
            continue
        turns.append({'role': role, 'text': text, 'time_str': _local_dt_str(msg.get('created_at'))})
    return turns


def _convert_standalone(data_dir, result_dir, resolver, stats, dry_run):
    conversations, load_errors = _load_standalone_conversations(data_dir)
    stats.parse_errors += load_errors
    stats.sessions_found += len(conversations)

    for conv in conversations:
        uuid = str(conv.get('uuid') or '').strip()
        if not uuid:
            stats.empty_skipped += 1
            continue

        turns = _standalone_turns(conv, resolver)
        if not turns:
            stats.empty_skipped += 1
            continue

        title = str(conv.get('name') or '').strip() or first_sentence(turns[0]['text'])
        date_str = _local_date(conv.get('created_at'))
        url = f"https://claude.ai/chat/{uuid}"

        md, content_hash = build_session_markdown(
            vendor_tag=VENDOR_TAG,
            vendor_label=VENDOR_LABEL,
            title=title,
            session_id=uuid,
            url=url,
            date_str=date_str,
            turns=turns,
        )

        file_path = result_dir / (sanitize_filename(uuid, fallback="unknown_conversation") + ".md")
        record_action(stats, write_upsert(file_path, md, content_hash, dry_run))


# ==========================================
# 메인 처리
# ==========================================

def convert(data_dir: Path, result_dir: Path, dry_run: bool) -> ConvertStats:
    stats = ConvertStats(vendor_tag=VENDOR_TAG)

    candidates = _find_claude_candidates(data_dir)
    if not candidates:
        print(f"[오류] {data_dir} 에서 Claude export 데이터를 찾지 못했습니다.")
        return stats

    effective_dir, ambiguous = pick_primary(candidates, "Claude export")
    if ambiguous:
        stats.parse_errors += 1

    resolver = _AttachmentResolver(result_dir / "Attachments", dry_run)

    _convert_standalone(effective_dir, result_dir, resolver, stats, dry_run)
    # design_chats/*.json(프로젝트 소속 대화)은 TSK-003-02에서 이어서 추가된다.

    stats.attachments_ok, stats.attachments_missing = resolver.stats()
    return stats
