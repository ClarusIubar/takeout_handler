"""MCP resource/tool 등록. mcp_server.index/mcp_server.pipeline을 얇게 감싸기만 하고
새 조회/변환 로직은 만들지 않는다.

vault는 절대 건드리지 않는다 — sync_takeout이 재생성하는 대상은 항상 result_dir뿐이다.
"""

import json
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from mcp_server.index import SessionIndex
from mcp_server.pipeline import discover_vendors, sync_vendor


def _session_summary(s):
    return {
        "vendor": s.vendor_tag,
        "session_id": s.session_id,
        "title": s.title,
        "date": s.date,
        "turns_count": s.turns_count,
        "url": s.url,
    }


def _session_full(s):
    return {
        **_session_summary(s),
        "turns": [
            {
                "turn_index": t.turn_index,
                "role": t.role,
                "parent_turn_index": t.parent_turn_index,
                "has_attachment": t.has_attachment,
                "time_str": t.time_str,
                "text": t.text,
            }
            for t in s.turns
        ],
    }


def create_server(result_dir, data_dirs=None, name="takeout-handler"):
    """MCPServer 인스턴스를 만들어 반환한다.

    result_dir: 렌더링된 세션 마크다운이 있는 루트(result/ 또는 vault). 조회 tool/resource는
        전부 여기서 읽는다.
    data_dirs: {vendor_tag: Path} — sync_takeout이 참조할 벤더별 raw export 위치. None이면
        sync_takeout이 호출될 때 "data_dir 미설정" 오류로 응답한다.
    """
    result_dir = Path(result_dir)
    data_dirs = data_dirs or {}

    server = MCPServer(name)
    index = SessionIndex()
    index.rebuild(result_dir)

    @server.tool()
    def list_sessions(vendor: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
        """저장된 Takeout 세션 목록을 최신순으로 반환한다 (turn 본문은 제외 — 응답 크기 유지)."""
        return [_session_summary(s) for s in index.list_sessions(vendor=vendor, limit=limit, offset=offset)]

    @server.tool()
    def search_sessions(
        query: str,
        vendor: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """제목 또는 turn 텍스트에 대한 단순 부분 문자열 검색이다 (대소문자 무시, 임베딩
        검색 아님). 검색어가 우연히 텍스트에 포함되기만 해도 결과에 걸리므로, 실제로는
        사용자가 찾는 것과 무관한 항목이 섞여 나올 수 있다 — 각 결과의 matched_snippet과
        title을 반드시 확인해서 실제로 관련 있는 항목만 사용자에게 보고하고, 단어만
        겹치고 맥락이 다른 항목은 걸러내라. 사용자가 특정 벤더(예: ChatGPT, Gemini)를
        언급하면 그걸 vendor 파라미터에 반영해서 검색 범위를 좁혀라. matched_snippet은
        문맥 확인용 짧은 미리보기일 뿐 전체 내용이 아니다 — 사용자가 정확한/전체
        내용(예: 체크리스트 항목, 구체적인 수치)을 원하면 snippet만으로 답하지 말고
        session_id로 get_session을 마저 호출해 전체 turn을 읽어라. 마찬가지로, 결과가
        여러 건이라 어느 것이 실제로 사용자의 질문과 관련 있는지 판단해야 할 때도
        snippet만 보고 단정하지 말고 get_session으로 전체 내용을 확인한 뒤에 판단해라 —
        snippet은 매치된 부분 주변만 잘라낸 것이라, 그것만으로는 그 대화가 정말 그
        주제를 다룬 것인지 스쳐 지나간 언급인지 구분되지 않는 경우가 많다."""
        results = index.search_sessions(query, vendor=vendor, date_from=date_from, date_to=date_to, limit=limit)
        return [{**_session_summary(s), "matched_snippet": snippet} for s, snippet in results]

    @server.tool()
    def get_session(vendor: str, session_id: str, format: str = "json") -> dict | str:
        """세션 하나를 turn 전체와 함께 조회한다.

        format="markdown"이면 result_dir에 저장된 원본 렌더링 텍스트를 그대로 반환하고,
        기본값("json")이면 구조화된 SessionRecord를 반환한다."""
        s = index.get_session(vendor, session_id)
        if s is None:
            raise ValueError(f"세션을 찾을 수 없음: {vendor}/{session_id}")
        if format == "markdown":
            # 실제 디렉터리명은 항상 s.vendor_tag(index가 이미 대소문자 무시하고 찾아준
            # 정식 값) 기준이다 — 호출자가 넘긴 vendor 원문(예: "Gemini")을 그대로 쓰면
            # 대소문자가 다를 때 파일을 못 찾을 수 있다.
            md_path = result_dir / s.vendor_tag / f"{session_id}.md"
            if not md_path.exists():
                raise ValueError(f"세션 마크다운 파일을 찾을 수 없음: {md_path}")
            return md_path.read_text(encoding="utf-8")
        return _session_full(s)

    @server.tool()
    def sync_takeout(vendor: str | None = None, dry_run: bool = False) -> dict[str, dict]:
        """raw export -> result_dir 를 재생성한다 (vault는 절대 건드리지 않음). 완료 후
        조회 인덱스를 새로고침한다(dry_run이면 새로고침하지 않음). 이 서버에서 유일하게
        부작용이 있는 tool이다."""
        vendors = discover_vendors()
        targets = [vendor.lower()] if vendor else list(vendors)
        unknown = [v for v in targets if v not in vendors]
        if unknown:
            raise ValueError(f"알 수 없는 벤더: {', '.join(unknown)} (사용 가능: {', '.join(sorted(vendors))})")

        summary = {}
        for name_ in targets:
            data_dir = data_dirs.get(name_)
            if data_dir is None:
                summary[name_] = {"skipped": True, "reason": "data_dir이 설정되지 않음"}
                continue
            stats, log_text = sync_vendor(name_, vendors[name_], dry_run, data_dir, result_dir / name_)
            if stats is None:
                summary[name_] = {"skipped": True, "log": log_text}
                continue
            summary[name_] = {
                "sessions_found": stats.sessions_found,
                "files_created": stats.files_created,
                "files_updated": stats.files_updated,
                "files_unchanged": stats.files_unchanged,
                "empty_skipped": stats.empty_skipped,
                "parse_errors": stats.parse_errors,
                "log": log_text,
            }

        if not dry_run:
            index.rebuild(result_dir)
        return summary

    @server.resource("takeout://sessions")
    def sessions_resource() -> str:
        return json.dumps([_session_summary(s) for s in index.list_sessions(limit=100_000)], ensure_ascii=False)

    @server.resource("takeout://sessions/{vendor}/{session_id}.json")
    def session_json_resource(vendor: str, session_id: str) -> str:
        s = index.get_session(vendor, session_id)
        if s is None:
            raise ValueError(f"세션을 찾을 수 없음: {vendor}/{session_id}")
        return json.dumps(_session_full(s), ensure_ascii=False)

    @server.resource("takeout://sessions/{vendor}/{session_id}.md")
    def session_markdown_resource(vendor: str, session_id: str) -> str:
        md_path = result_dir / vendor / f"{session_id}.md"
        if not md_path.exists():
            raise ValueError(f"세션 마크다운 파일을 찾을 수 없음: {md_path}")
        return md_path.read_text(encoding="utf-8")

    return server
