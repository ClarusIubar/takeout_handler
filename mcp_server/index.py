"""result_dir(또는 vault) 아래 렌더링된 세션 마크다운을 순회해 인메모리 조회 인덱스를 만든다.

vendors/, common/session_markdown.py는 건드리지 않는다 — 이미 만들어진 .md 파일을
common.session_reader.parse_session_markdown()으로 역파싱해서 재사용할 뿐이다.
"""

from pathlib import Path

from common.session_reader import parse_session_markdown


class SessionIndex:
    def __init__(self):
        self._sessions = []

    def rebuild(self, root, vendors=None):
        """root/<vendor>/*.md 를 전부 읽어 인덱스를 처음부터 다시 만든다.

        vendors: 스캔할 벤더 디렉터리 이름 목록. None이면 root 바로 아래 모든
        서브디렉터리를 벤더로 취급한다."""
        root = Path(root)
        self._sessions = []
        if not root.exists():
            return

        if vendors is not None:
            vendor_dirs = [root / name for name in vendors]
        else:
            vendor_dirs = [p for p in sorted(root.iterdir()) if p.is_dir()]

        for vendor_dir in vendor_dirs:
            if not vendor_dir.is_dir():
                continue
            vendor_tag = vendor_dir.name
            for md_path in sorted(vendor_dir.glob("*.md")):
                text = md_path.read_text(encoding="utf-8")
                try:
                    record = parse_session_markdown(text, vendor_tag=vendor_tag)
                except (ValueError, KeyError):
                    # 세션 마크다운 형식이 아닌 파일(사용자가 직접 만든 노트 등)은 조용히 건너뜀.
                    continue
                self._sessions.append(record)

    def list_sessions(self, vendor=None, limit=50, offset=0):
        items = [s for s in self._sessions if vendor is None or s.vendor_tag == vendor]
        items.sort(key=lambda s: s.date, reverse=True)
        return items[offset:offset + limit]

    def search_sessions(self, query, vendor=None, date_from=None, date_to=None, limit=20):
        """제목 또는 turn 텍스트에 query가 (대소문자 무시) 부분 문자열로 들어있는 세션을
        찾는다. 반환값: [(SessionRecord, matched_snippet)]. 임베딩/시맨틱 검색은 하지 않는다."""
        needle = query.lower()
        results = []
        for s in self._sorted_for_search():
            if vendor is not None and s.vendor_tag != vendor:
                continue
            if date_from is not None and s.date < date_from:
                continue
            if date_to is not None and s.date > date_to:
                continue

            if needle in s.title.lower():
                results.append((s, s.title))
                continue
            for t in s.turns:
                if needle in t.text.lower():
                    results.append((s, t.text))
                    break

            if len(results) >= limit:
                break
        return results[:limit]

    def get_session(self, vendor, session_id):
        for s in self._sessions:
            if s.vendor_tag == vendor and s.session_id == session_id:
                return s
        return None

    def _sorted_for_search(self):
        return sorted(self._sessions, key=lambda s: s.date, reverse=True)
