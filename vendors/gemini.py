"""Gemini Takeout(내 활동.html) -> 마크다운.

gemini_takeout/convert.py 포팅 (BASE_DIR/OUTPUT_DIR이 옛 폴더명 google_take_out으로
하드코딩돼 있던 버그를 data_dir/result_dir 파라미터화로 수정).

Google "내 활동" HTML은 outer-cell div 블록의 나열이라, 문자열 위치 기준으로 블록을
잘라낸 뒤 블록마다 새 HTMLParser 인스턴스로 파싱한다. 세션 ID는 각 블록의 caption
링크(gemini.google.com/app/<id>)에서 추출해 세션 단위로 그룹핑한다.
"""

import os
import re
import shutil
import urllib.parse
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

from common.attachment_cache import BaseAttachmentResolver
from common.markdown_safety import ensure_fences_closed, make_fence, normalize_fences
from common.session_markdown import build_session_markdown
from common.text import first_sentence, sanitize_filename
from vendors.base import ConvertStats

VENDOR_TAG = "gemini"
VENDOR_LABEL = "Gemini"

ACTIVITY_HTML_BASENAME_HINTS = ('내활동', '내 활동', 'activity', 'Activity')
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}
AUDIO_EXTS = {'.wav'}
PDF_EXTS = {'.pdf'}
EMBED_EXTS = IMAGE_EXTS | AUDIO_EXTS | PDF_EXTS  # 이미지+음성+PDF 전부 Obsidian 네이티브 임베드

MARKER = "항목을 검색함"
KST_RE = re.compile(
    r'(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(오전|오후)\s*(\d{1,2}):(\d{2}):(\d{2})\s*KST'
)
VOID_TAGS = {'br', 'hr', 'img'}


def _find_activity_html(data_dir: Path):
    for root, _dirs, files in os.walk(data_dir):
        for file in files:
            if file.endswith('.html') and any(hint in file for hint in ACTIVITY_HTML_BASENAME_HINTS):
                return Path(root) / file
    return None


def detect(data_dir: Path) -> bool:
    return _find_activity_html(data_dir) is not None


def _is_remote_url(s):
    return bool(re.match(r'^https?://', (s or '').strip(), re.IGNORECASE))


class _AttachmentResolver(BaseAttachmentResolver):
    """href/src(원본 그대로, percent-encoded일 수 있음) -> (rel_path, display_name, is_embeddable).
    basename 기준으로 캐시되어 같은 파일이 여러 턴/세션에서 참조돼도 한 번만 복사된다."""

    def __init__(self, data_dir, attachments_dir, activity_html_basename, dry_run):
        super().__init__(attachments_dir, dry_run)
        self.data_dir = data_dir
        self.activity_html_basename = activity_html_basename

    def resolve(self, raw_ref, hint_display_name=None):
        if not raw_ref or _is_remote_url(raw_ref):
            return None

        orig_basename = os.path.basename(urllib.parse.unquote(raw_ref))
        if not orig_basename or orig_basename == self.activity_html_basename:
            return None

        if orig_basename in self._cache:
            return self._cache[orig_basename]

        basename = orig_basename
        src_path = self.data_dir / basename
        if not src_path.exists():
            # Gemini href의 확장자가 실제 저장된 파일과 다를 때가 있다:
            # (1) href는 .png인데 실제로는 .jpg로 저장됨
            # (2) href는 Canvas 문서라 .md라고 붙어있는데 실제 파일은 확장자가 아예 없음
            # 같은 stem으로 다른 이미지 확장자 -> 무확장자 순서로 찾아본다.
            stem = os.path.splitext(basename)[0]
            candidates = [stem + alt_ext for alt_ext in IMAGE_EXTS] + [stem]
            for candidate in candidates:
                alt_path = self.data_dir / candidate
                if alt_path.exists():
                    basename = candidate
                    src_path = alt_path
                    break
            else:
                self._cache[orig_basename] = None
                return None

        ext = os.path.splitext(basename)[1]
        dest_name = basename if ext else (basename + ".md")  # 확장자 없는 Canvas 문서 -> .md
        dest_path = self.attachments_dir / dest_name

        self._guarded_copy(dest_path, lambda: shutil.copy2(src_path, dest_path))

        display_name = hint_display_name or basename
        is_embeddable = ext.lower() in EMBED_EXTS  # 확장자 없는 .md-fallback은 임베드하지 않음
        result = (f"Attachments/{dest_name}", display_name, is_embeddable)
        self._cache[orig_basename] = result
        self._cache[basename] = result
        return result


def _parse_kst(text):
    m = KST_RE.search(text)
    if not m:
        return None
    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    ampm = m.group(4)
    hour = int(m.group(5))
    minute = int(m.group(6))
    second = int(m.group(7))
    if ampm == "오후" and hour < 12:
        hour += 12
    elif ampm == "오전" and hour == 12:
        hour = 0
    try:
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None


def _render(node, resolver):
    """MiniNode(dict) 또는 str -> 마크다운 문자열"""
    if isinstance(node, str):
        return node

    tag = node['tag']
    children_md = "".join(_render(c, resolver) for c in node['children'])

    if tag in ('pre',):
        code_text = "".join(_raw_text(c) for c in node['children']).strip('\n')
        fence = make_fence(code_text)
        return f"\n{fence}\n{code_text}\n{fence}\n"
    if tag == 'code':
        raw = "".join(_raw_text(c) for c in node['children'])
        if '\n' in raw:
            code_text = raw.strip('\n')
            fence = make_fence(code_text)
            return f"\n{fence}\n{code_text}\n{fence}\n"
        return f"`{raw}`"
    if tag == 'p':
        return f"\n{children_md.strip()}\n\n"
    if tag == 'br':
        return "\n"
    if tag == 'hr':
        return "\n---\n"
    if tag == 'img':
        src = node['attrs'].get('src', '')
        if not src:
            return ""
        if _is_remote_url(src):
            return f"\n![]({src})\n"
        resolved = resolver.resolve(src, hint_display_name=node['attrs'].get('alt') or None)
        if resolved is None:
            return f"\n⚠️ 이미지 누락 (원본 export에 파일 없음): {src}\n"
        rel_path, display_name, is_embeddable = resolved
        if is_embeddable:
            return f"\n![[{rel_path}]]\n"
        return f"\n📎 [[{rel_path}|{display_name}]]\n"
    if tag in ('b', 'strong'):
        return f"**{children_md}**"
    if tag in ('i', 'em'):
        return f"*{children_md}*"
    if tag == 'li':
        return f"- {children_md.strip()}\n"
    if tag in ('ul', 'ol'):
        return f"\n{children_md}\n"
    if tag == 'a':
        href = node['attrs'].get('href', '#')
        text = children_md.strip() or href
        return f"[{text}]({href})"
    if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
        level = int(tag[1])
        return f"\n{'#' * min(level, 6)} {children_md.strip()}\n"
    if tag == 'table':
        return _render_table(node, resolver)
    return children_md


def _raw_text(node):
    if isinstance(node, str):
        return node
    if node['tag'] == 'br':
        return "\n"
    return "".join(_raw_text(c) for c in node['children'])


def _render_table(node, resolver):
    def find_rows(n):
        out = []
        for c in n['children']:
            if isinstance(c, str):
                continue
            if c['tag'] == 'tr':
                out.append(c)
            else:
                out.extend(find_rows(c))
        return out

    rows = find_rows(node)
    if not rows:
        return ""
    md = "\n"
    for i, row in enumerate(rows):
        cells = [c for c in row['children'] if not isinstance(c, str) and c['tag'] in ('td', 'th')]
        md += "| " + " | ".join(_render(c, resolver).strip().replace('\n', ' ') for c in cells) + " |\n"
        if i == 0:
            md += "| " + " | ".join(['---'] * len(cells)) + " |\n"
    return md + "\n"


def _is_target_content_cell(cls):
    return 'content-cell' in cls and 'body-1' in cls and 'text-right' not in cls


def _find_outer_cell_blocks(content):
    """outer-cell div들은 서로 중첩되지 않는 형제(flat sibling) 구조이므로,
    문자열 위치 기준으로만 잘라내도 안전하다 (스트리밍 depth 카운터의 오류를 원천 차단)."""
    marker = '<div class="outer-cell'
    idxs = []
    start = 0
    while True:
        i = content.find(marker, start)
        if i == -1:
            break
        idxs.append(i)
        start = i + len(marker)
    idxs.append(len(content))
    return [content[idxs[i]:idxs[i + 1]] for i in range(len(idxs) - 1)]


class _BlockParser(HTMLParser):
    """outer-cell 블록 하나(HTML 조각)를 파싱. 블록마다 새 인스턴스를 사용하므로
    이전 블록의 상태가 다음 블록으로 새는 일이 없다."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.in_target = False
        self.depth = 0
        self.stack = None
        self.tree = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == 'a':
            href = attrs_dict.get('href') or ""
            if href:
                self.links.append(href)

        if not self.in_target:
            if tag == 'div' and _is_target_content_cell(attrs_dict.get('class') or ""):
                self.in_target = True
                self.depth = 1
                self.stack = [{'tag': 'root', 'attrs': {}, 'children': []}]
            return

        assert self.stack is not None
        if tag == 'div':
            self.depth += 1
        node = {'tag': tag, 'attrs': attrs_dict, 'children': []}
        self.stack[-1]['children'].append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_endtag(self, tag):
        if not self.in_target:
            return
        assert self.stack is not None
        if tag == 'div':
            self.depth -= 1
        if tag not in VOID_TAGS and len(self.stack) > 1 and self.stack[-1]['tag'] == tag:
            self.stack.pop()
        if tag == 'div' and self.depth == 0:
            self.in_target = False
            self.tree = self.stack[0]

    def handle_data(self, data):
        if self.in_target and self.stack and data:
            self.stack[-1]['children'].append(data)


def _extract_gemini_session_id(links):
    """caption 영역의 실제 세션 링크는 항상 블록 마지막 쪽에 나온다.
    응답 본문 중 예시로 언급된 gemini.google.com/app/... 링크(placeholder)에
    낚이지 않도록 첫 매치가 아니라 '마지막' 매치를 채택한다."""
    sid = None
    for href in links:
        m = re.search(r'gemini\.google\.com/app/([a-zA-Z0-9_-]+)', href)
        if m:
            sid = m.group(1).strip().rstrip(':;,.')
    return sid


def _parse_block(block, resolver):
    p = _BlockParser()
    p.feed(block)
    sid = _extract_gemini_session_id(p.links)

    root_children = p.tree['children'] if p.tree else []
    prompt_parts = []
    attachments = []
    dt = None
    response_nodes = []

    state = 'prompt'
    for child in root_children:
        if state == 'prompt':
            if isinstance(child, str) and MARKER in child:
                before = child.split(MARKER, 1)[0]
                if before:
                    prompt_parts.append(before)
                state = 'post_marker'
            else:
                prompt_parts.append(_render(child, resolver))
        elif state == 'post_marker':
            if isinstance(child, str):
                parsed = _parse_kst(child)
                if parsed is not None:
                    dt = parsed
                    state = 'response'
                # else: ignore stray text (e.g. "파일 N개 첨부됨.")
            elif child['tag'] == 'a':
                href = child['attrs'].get('href', '')
                # 순수 표시용 라벨이어야 한다 (render()는 "[text](href)" 마크다운
                # 링크 문자열을 반환하므로 쓰면 안 됨 - 나중에 다른 링크/임베드 문법
                # 안에 라벨로 다시 끼워넣을 때 중첩 마크다운이 되어 깨진다).
                text = _raw_text(child).strip() or href
                if href:
                    attachments.append((text, href))
            # br/etc: ignore
        else:  # response
            response_nodes.append(child)

    prompt_text = ensure_fences_closed(normalize_fences("".join(prompt_parts).strip()))
    response_md = ensure_fences_closed(normalize_fences("".join(_render(n, resolver) for n in response_nodes).strip()))

    return {
        'sid': sid,
        'prompt': prompt_text,
        'response': response_md,
        'attachments': attachments,
        'dt': dt,
    }


def _attachments_after_md(attachments, resolver):
    if not attachments:
        return ""
    out = ""
    for text, href in attachments:
        if _is_remote_url(href):
            out += f"> [{text}]({href})\n\n"
            continue
        resolved = resolver.resolve(href, hint_display_name=text)
        if resolved is None:
            out += f"> ⚠️ 첨부파일 누락 (원본 export에 파일 없음): {text} ({href})\n\n"
        else:
            rel_path, display_name, is_embeddable = resolved
            if is_embeddable:
                out += f"> ![[{rel_path}]]\n\n"
            else:
                out += f"> 📎 [[{rel_path}|{display_name}]]\n\n"
    return out


# ==========================================
# 메인 처리
# ==========================================

def convert(data_dir: Path, result_dir: Path, dry_run: bool) -> ConvertStats:
    stats = ConvertStats(vendor_tag=VENDOR_TAG)
    attachments_dir = result_dir / "Attachments"

    html_file = _find_activity_html(data_dir)
    if not html_file:
        print(f"[오류] {data_dir} 내에서 '내활동.html'(Activity) 파일을 찾지 못했습니다.")
        return stats

    file_size_mb = html_file.stat().st_size / (1024 * 1024)
    print(f"[파싱 시작] {html_file} ({file_size_mb:.1f} MB)")

    # Google Takeout은 보통 Takeout/<서비스명>/ 처럼 한 겹 이상 감싸져 있고, html이
    # 참조하는 첨부 미디어 파일들은 data_dir 최상위가 아니라 html과 같은 폴더에
    # 나란히 들어있다. 최상위 data_dir을 기준으로 찾으면(예전 방식) 실제 export
    # zip을 그대로 넣었을 때 첨부파일을 전부 놓친다.
    effective_dir = html_file.parent
    resolver = _AttachmentResolver(effective_dir, attachments_dir, html_file.name, dry_run)

    with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    blocks = _find_outer_cell_blocks(content)
    del content
    print(f"  outer-cell 블록 수: {len(blocks)}개")

    entries = []
    for i, block in enumerate(blocks):
        entries.append(_parse_block(block, resolver))
        if i % 200 == 0:
            print(f"\r  [파싱 중] {i}/{len(blocks)}", end='', flush=True)
    print()

    session_groups = {}
    orphan_count = 0
    for entry in entries:
        sid = entry['sid']
        if not sid:
            orphan_count += 1
            continue
        session_groups.setdefault(sid, []).append(entry)

    print(f"  세션ID 없는 항목(죽은 링크/삭제된 대화): {orphan_count}개 -> 무시")
    print(f"고유 세션 {len(session_groups)}개 -> {len(session_groups)}개의 .md 파일 생성 예정")
    stats.sessions_found = len(session_groups)

    for sid, turns_raw in session_groups.items():
        turns_raw.sort(key=lambda t: t['dt'] or datetime.min)

        first_turn = turns_raw[0]
        title = first_sentence(first_turn['prompt'])
        date_str = (first_turn['dt'] or datetime.min).strftime('%Y-%m-%d') if first_turn['dt'] else "unknown"
        url = f"https://gemini.google.com/app/{sid}"

        turns = []
        for t in turns_raw:
            time_str = t['dt'].strftime('%Y-%m-%d %H:%M:%S') if t['dt'] else "시간 미상"
            turns.append({
                'role': 'user',
                'text': t['prompt'],
                'time_str': time_str,
                'after_md': _attachments_after_md(t['attachments'], resolver),
            })
            turns.append({
                'role': 'assistant',
                'text': t['response'],
                'time_str': time_str,
            })

        md = build_session_markdown(
            vendor_tag=VENDOR_TAG,
            vendor_label=VENDOR_LABEL,
            title=title,
            session_id=sid,
            url=url,
            date_str=date_str,
            turns=turns,
            turns_count=len(turns_raw),
        )

        filename = sanitize_filename(sid, fallback="unknown_session") + ".md"
        file_path = result_dir / filename

        if not dry_run:
            result_dir.mkdir(parents=True, exist_ok=True)
            file_path.write_text(md, encoding='utf-8')
        stats.files_written += 1

    stats.attachments_ok, stats.attachments_missing = resolver.stats()
    return stats
