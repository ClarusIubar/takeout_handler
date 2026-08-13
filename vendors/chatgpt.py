"""ChatGPT Takeout(conversations*.json) -> 마크다운.

gpt_takeout/convert.py 포팅. 대화는 mapping(트리) 구조이므로 current_node에서
parent를 역추적해 실제 화면에 보였던 브랜치 하나만 채택한다 (재생성된 분기는 버림).
첨부파일은 conversation_asset_file_names.json으로 원본 파일명을 찾고, 실제 바이트는
file_<id>.dat 블롭에서 가져와 result_dir/Attachments로 복사한다.
"""

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

from common.attachment_cache import BaseAttachmentResolver
from common.fs_discovery import is_junk_path
from common.markdown_safety import ensure_fences_closed, normalize_fences
from common.session_markdown import build_session_markdown
from common.text import first_sentence, sanitize_filename
from common.upsert import write_upsert
from vendors.base import ConvertStats

VENDOR_TAG = "chatgpt"
VENDOR_LABEL = "ChatGPT"

IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}
AUDIO_EXTS = {'.wav'}
PDF_EXTS = {'.pdf'}
# Gemini 쪽(vendors/gemini.py)과 동일한 임베드 기준: 이미지+음성+PDF. mp4는 인식은 하되
# (destination 확장자를 올바르게 붙이되) 임베드 대상에는 안 넣는다 — Gemini의 실측 데이터에도
# mp4 첨부가 있었지만 그쪽도 EMBED_EXTS에서 제외하고 링크로만 표시하는 것으로 이미 검증됨.
EMBED_EXTS = IMAGE_EXTS | AUDIO_EXTS | PDF_EXTS


def _find_conversation_candidates(data_dir: Path):
    """data_dir 재귀 탐색으로 conversations*.json이 들어있는 서로 다른 부모 디렉터리를
    전부 찾는다 (macOS 압축이 남기는 __MACOSX/ 같은 쓰레기 경로는 제외 — 안 걸러내면
    알파벳순 정렬에서 __MACOSX가 정상 폴더보다 앞에 와 엉뚱한 사본이 선택될 수 있다).
    정상적인 export라면 보통 정확히 1개만 나온다. 상위(얕은) 폴더가 먼저 오도록 정렬."""
    matches = data_dir.rglob('conversations*.json')
    parents = {m.parent for m in matches if not is_junk_path(m, data_dir)}
    return sorted(parents, key=lambda p: len(p.relative_to(data_dir).parts))


def _find_conversations_dir(data_dir: Path):
    """detect()용 간단 버전 — 후보 중 하나라도 있으면 그중 가장 얕은 폴더를 반환.
    여러 후보가 있을 때의 경고 로그는 convert()에서 한 번만 찍는다(내부에서 detect()가
    여러 번 호출될 수 있어 여기서 찍으면 중복 출력됨)."""
    candidates = _find_conversation_candidates(data_dir)
    return candidates[0] if candidates else None


def detect(data_dir: Path) -> bool:
    return _find_conversations_dir(data_dir) is not None


# ==========================================
# 첨부파일 해석 (.dat 블롭 -> 실제 파일)
# ==========================================

def _load_asset_name_map(data_dir):
    """conversation_asset_file_names.json: {".dat 파일명": "원본 파일명"} -> {file_id: 원본 파일명}"""
    path = data_dir / "conversation_asset_file_names.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        print(f"[경고] conversation_asset_file_names.json 파싱 실패: {exc}")
        return {}
    out = {}
    if isinstance(data, dict):
        for dat_name, orig_name in data.items():
            file_id = dat_name[:-4] if dat_name.lower().endswith('.dat') else dat_name
            out[file_id] = orig_name
    return out


def _sniff_ext(path):
    try:
        head = path.open('rb').read(16)
    except Exception:
        return None
    if head.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png'
    if head.startswith(b'\xff\xd8\xff'):
        return '.jpg'
    if head.startswith(b'GIF87a') or head.startswith(b'GIF89a'):
        return '.gif'
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return '.webp'
    if head[:4] == b'RIFF' and head[8:12] == b'WAVE':
        return '.wav'
    if head[4:8] == b'ftyp':
        return '.mp4'
    if head.startswith(b'%PDF'):
        return '.pdf'
    return None


def _ext_from_name(name):
    if not name:
        return None
    ext = os.path.splitext(name)[1]
    return ext if ext else None


class _AttachmentResolver(BaseAttachmentResolver):
    def __init__(self, data_dir, attachments_dir, asset_name_map, dry_run):
        super().__init__(attachments_dir, dry_run)
        self.data_dir = data_dir
        self.asset_name_map = asset_name_map

    def resolve(self, file_id, hint_name=None):
        """.dat 블롭을 확장자 붙여서 attachments_dir로 복사하고
        (상대링크, 표시용 원본 파일명, 이미지 여부)를 반환. 원본이 없으면 None."""
        if file_id in self._cache:
            return self._cache[file_id]

        dat_path = self.data_dir / f"{file_id}.dat"
        if not dat_path.exists():
            self._cache[file_id] = None
            return None

        orig_name = hint_name or self.asset_name_map.get(file_id)
        ext = _ext_from_name(orig_name) or _sniff_ext(dat_path) or '.bin'
        dest_name = f"{file_id}{ext}"
        dest_path = self.attachments_dir / dest_name

        self._guarded_copy(dest_path, lambda: dest_path.write_bytes(dat_path.read_bytes()))

        display_name = orig_name or dest_name
        is_embeddable = ext.lower() in EMBED_EXTS
        result = (f"Attachments/{dest_name}", display_name, is_embeddable)
        self._cache[file_id] = result
        return result

    def describe(self, file_id, hint_name=None):
        resolved = self.resolve(file_id, hint_name=hint_name)
        if resolved is None:
            label = hint_name or file_id
            return f"\n> ⚠️ 첨부파일 누락 (원본 export에 파일 없음): {label}\n"
        rel_path, display_name, is_embeddable = resolved
        if is_embeddable:
            return f"\n![[{rel_path}]]\n"
        return f"\n📎 [{display_name}]({rel_path})\n"


# ==========================================
# ChatGPT export JSON 파싱
# ==========================================

def _conversation_id(conv):
    return str(conv.get('id') or conv.get('conversation_id') or '').strip()


def _load_conversations(data_dir):
    """(대화 리스트, 파싱 실패한 파일 수)를 반환한다. 파일 하나가 깨져 있어도
    (예: 다운로드 중단된 export) 나머지는 계속 처리하되, 실패 건수는 상위로
    올려서 run.py가 '조용한 부분 실패'를 종료 코드로 알 수 있게 한다."""
    files = sorted(data_dir.glob('conversations*.json'))
    if not files:
        print(f"[오류] {data_dir} 에서 conversations*.json 을 찾지 못했습니다.")
        return [], 0

    raw = []
    errors = 0
    for path in files:
        try:
            data = json.loads(path.read_text(encoding='utf-8-sig'))
        except Exception as exc:
            print(f"[경고] {path.name} 파싱 실패: {exc}")
            errors += 1
            continue
        if isinstance(data, list):
            print(f"  {path.name}: {len(data)}개 대화")
            raw.extend(x for x in data if isinstance(x, dict))
        else:
            # 최상위가 list가 아니면 "0개 대화"로 조용히 넘기지 않는다 — 예상과 다른
            # export 형식(스키마 변경 등)일 수 있으므로 진짜 빈 export와 구분해서 알린다.
            print(f"[경고] {path.name}의 최상위 타입이 list가 아니라 {type(data).__name__}입니다 "
                  "— 예상과 다른 export 형식일 수 있습니다.")
            errors += 1

    dedup = {}
    dup_count = 0
    for conv in raw:
        key = _conversation_id(conv) or hashlib.sha256(
            json.dumps(conv, sort_keys=True, ensure_ascii=False, default=str).encode('utf-8')
        ).hexdigest()
        if key in dedup:
            dup_count += 1
        dedup[key] = conv
    if dup_count:
        print(f"[경고] 중복 conversation_id {dup_count}건 (마지막으로 처리된 파일 것으로 덮어씀)")
    return list(dedup.values()), errors


def _message_timestamp(node):
    msg = node.get('message') or {}
    for key in ('create_time', 'update_time'):
        try:
            value = msg.get(key)
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            pass
    return 0.0


def _choose_fallback_leaf(mapping):
    if not mapping:
        return None
    leaves = [
        nid for nid, node in mapping.items()
        if isinstance(node, dict) and not (node.get('children') or [])
    ]
    candidates = leaves or [nid for nid, node in mapping.items() if isinstance(node, dict)]
    if not candidates:
        return None
    return max(candidates, key=lambda nid: _message_timestamp(mapping[nid]))


def _active_branch_nodes(conv):
    """대화는 트리(mapping) 구조라 current_node에서 parent를 따라 역추적해서
    실제 화면에 보였던 브랜치 하나만 골라낸다 (분기된 재생성 답변은 최신 브랜치만 채택)."""
    mapping = conv.get('mapping') or {}
    if not isinstance(mapping, dict):
        return []

    current = conv.get('current_node')
    if not isinstance(current, str) or current not in mapping:
        current = _choose_fallback_leaf(mapping)
    if not current:
        return []

    chain = []
    seen = set()
    node_id = current
    while node_id and node_id in mapping and node_id not in seen:
        seen.add(node_id)
        node = mapping[node_id]
        if not isinstance(node, dict):
            break
        chain.append(node)
        parent = node.get('parent')
        node_id = parent if isinstance(parent, str) else None

    chain.reverse()
    return chain


def _visible_message(node):
    msg = node.get('message')
    if not isinstance(msg, dict):
        return None

    role = (msg.get('author') or {}).get('role')
    if role not in ('user', 'assistant'):
        return None

    # recipient가 'all'/None이 아니면 도구 호출용 내부 메시지(코드인터프리터 등)라 건너뛴다.
    recipient = msg.get('recipient')
    if recipient not in (None, 'all'):
        return None

    metadata = msg.get('metadata') or {}
    if isinstance(metadata, dict):
        if metadata.get('is_visually_hidden_from_conversation') is True:
            return None
        if metadata.get('is_hidden') is True:
            return None

    return msg


def _render_part(part, seen_asset_ids, resolver):
    if isinstance(part, str):
        return part
    if not isinstance(part, dict):
        return ""

    ctype = str(part.get('content_type') or part.get('type') or '').strip()

    if ctype in ('text', 'input_text', 'output_text'):
        text = part.get('text')
        return text if isinstance(text, str) else ""

    if ctype == 'image_asset_pointer':
        pointer = part.get('asset_pointer') or ""
        file_id = pointer.split('://', 1)[-1] if '://' in pointer else pointer
        if file_id:
            seen_asset_ids.add(file_id)
            return resolver.describe(file_id)
        return "\n> ⚠️ 첨부파일 누락 (알 수 없는 이미지)\n"

    if ctype in ('audio', 'input_audio'):
        return "[오디오]"

    if ctype == 'audio_transcription':
        # Advanced Voice Mode 대화: 실제 발화 내용이 여기 text 필드에 들어있다.
        text = part.get('text')
        return text if isinstance(text, str) else ""

    if ctype == 'real_time_user_audio_video_asset_pointer':
        # 음성/영상 스트림 마커 자체 (녹음 파일 asset). 트랜스크립트는 audio_transcription
        # 파츠 쪽에 별도로 들어있으므로 여기서는 렌더링할 텍스트가 없다.
        return ""

    if ctype:
        # thoughts/reasoning_recap 등 추론 과정 요약: 렌더링할 텍스트가 없으므로 건너뜀
        return ""

    for key in ('text', 'name', 'title'):
        value = part.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _render_message(msg, resolver):
    content = msg.get('content') or {}
    chunks = []
    seen_asset_ids = set()

    parts = content.get('parts') if isinstance(content, dict) else None
    if isinstance(parts, list):
        chunks.extend(_render_part(p, seen_asset_ids, resolver) for p in parts)
    else:
        text = content.get('text') if isinstance(content, dict) else None
        if isinstance(text, str):
            chunks.append(text)

    # metadata.attachments는 종종 content.parts의 image_asset_pointer와 같은 파일을
    # 중복 기재한다 (업로드 기록용). 이미 parts에서 렌더링된 asset은 다시 넣지 않는다.
    metadata = msg.get('metadata') or {}
    attachments = metadata.get('attachments') if isinstance(metadata, dict) else None
    if isinstance(attachments, list):
        for att in attachments:
            if not isinstance(att, dict):
                continue
            file_id = att.get('id')
            if isinstance(file_id, str) and file_id in seen_asset_ids:
                continue
            name = att.get('name') or att.get('file_name') or att.get('filename')
            if isinstance(file_id, str) and file_id:
                chunks.append(resolver.describe(file_id, hint_name=name))
            elif isinstance(name, str) and name.strip():
                chunks.append(f"\n> ⚠️ 첨부파일 누락 (원본 export에 파일 없음): {name.strip()}\n")

    text = "\n\n".join(c.strip() for c in chunks if isinstance(c, str) and c.strip())
    return ensure_fences_closed(normalize_fences(text.strip()))


def _local_date(ts):
    try:
        if ts is None:
            raise ValueError
        return datetime.fromtimestamp(float(ts)).date().isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return "unknown"


def _local_dt_str(ts):
    try:
        if ts is None:
            raise ValueError
        return datetime.fromtimestamp(float(ts)).strftime('%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError, OSError, OverflowError):
        return "시간 미상"


# ==========================================
# 메인 처리
# ==========================================

def convert(data_dir: Path, result_dir: Path, dry_run: bool) -> ConvertStats:
    stats = ConvertStats(vendor_tag=VENDOR_TAG)
    attachments_dir = result_dir / "Attachments"

    candidates = _find_conversation_candidates(data_dir)
    if not candidates:
        print(f"[오류] {data_dir} 에서 conversations*.json 을 찾지 못했습니다.")
        return stats

    effective_dir = candidates[0]
    if len(candidates) > 1:
        print(f"[경고] conversations*.json이 서로 다른 폴더 {len(candidates)}곳에서 발견됨 "
              "(재실행 잔여물이나 압축 중복 가능성):")
        for c in candidates:
            print(f"    - {c}")
        print(f"  -> 가장 상위 폴더를 사용: {effective_dir}")
        stats.parse_errors += 1

    asset_name_map = _load_asset_name_map(effective_dir)
    print(f"첨부파일 원본명 매핑: {len(asset_name_map)}개 로드")
    resolver = _AttachmentResolver(effective_dir, attachments_dir, asset_name_map, dry_run)

    conversations, load_errors = _load_conversations(effective_dir)
    stats.parse_errors += load_errors
    stats.sessions_found = len(conversations)
    print(f"총 대화 {len(conversations)}개 로드 (중복 제거 후)")

    for conv in sorted(
        conversations,
        key=lambda c: float(c.get('create_time') or c.get('update_time') or 0),
    ):
        cid = _conversation_id(conv)
        if not cid:
            stats.empty_skipped += 1
            continue

        turns = []
        for node in _active_branch_nodes(conv):
            msg = _visible_message(node)
            if not msg:
                continue
            role = (msg.get('author') or {}).get('role')
            text = _render_message(msg, resolver)
            if not text:
                continue
            ts = None
            for key in ('create_time', 'update_time'):
                value = msg.get(key)
                if value is not None:
                    ts = value
                    break
            turns.append({'role': role, 'text': text, 'time_str': _local_dt_str(ts), '_ts': ts})

        if not turns:
            stats.empty_skipped += 1
            continue

        title = str(conv.get('title') or '').strip()
        if not title:
            first_user_turn = next((t for t in turns if t['role'] == 'user'), turns[0])
            title = first_sentence(first_user_turn['text'])

        first_ts = conv.get('create_time') or turns[0]['_ts']
        date_str = _local_date(first_ts)
        url = f"https://chatgpt.com/c/{cid}"

        md, content_hash = build_session_markdown(
            vendor_tag=VENDOR_TAG,
            vendor_label=VENDOR_LABEL,
            title=title,
            session_id=cid,
            url=url,
            date_str=date_str,
            turns=turns,
        )

        filename = sanitize_filename(cid, fallback="unknown_conversation") + ".md"
        file_path = result_dir / filename

        action = write_upsert(file_path, md, content_hash, dry_run)
        if action == "created":
            stats.files_created += 1
        elif action == "updated":
            stats.files_updated += 1
        else:
            stats.files_unchanged += 1

    stats.attachments_ok, stats.attachments_missing = resolver.stats()
    return stats
