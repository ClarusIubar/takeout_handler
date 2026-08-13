"""세션 마크다운을 조건 없이 덮어쓰지 않고, 내용이 실제로 바뀐 경우에만 쓰는 upsert 유틸.

session_id 파일이 이미 존재하는지만 보면 안 되는 이유: 같은 session_id로 나중에 대화를 더
하고 다시 takeout을 받으면 turn이 늘어난 상태인데, 존재 여부만 보면 그 변경을 놓친다. 반대로
원본(JSON/HTML) 바이트와 우리가 만든 마크다운을 직접 비교하는 건 형식 자체가 달라 불가능하다.

그래서 "원본 vs 마크다운"이 아니라 "지난번에 만든 마크다운 vs 이번에 새로 만든 마크다운"을
비교한다 — 같은 렌더링 함수(common/session_markdown.py::build_session_markdown)의 출력이라
형식이 다르다는 문제가 없고, 소스가 안 바뀌었으면 해시가 그대로라 파일도 그대로 둔다(사용자가
옵시디언에서 노트를 직접 손봐도 소스가 안 바뀐 한 보존됨). 소스가 바뀌면(턴 추가, 제목 변경 등)
해시가 달라져서 다시 써야 한다는 게 정확히 잡힌다.
"""

from pathlib import Path

from common.session_markdown import extract_content_hash


def write_upsert(file_path: Path, md: str, content_hash: str, dry_run: bool) -> str:
    """"created" / "updated" / "unchanged" 중 하나를 반환한다.

    - 기존 파일이 없으면 "created".
    - 있는데 저장된 content_hash가 새 해시와 다르면(또는 못 읽으면) "updated".
    - 있고 해시가 같으면 "unchanged" — 파일에 손대지 않는다.

    dry_run이어도 판정 자체(어떤 파일을 읽는 것)는 그대로 하고, 실제 write만 건너뛴다 —
    그래야 --dry-run으로 upsert 결과를 미리 확인할 수 있다.
    """
    existing_hash = None
    if file_path.exists():
        try:
            existing_hash = extract_content_hash(file_path.read_text(encoding='utf-8'))
        except Exception:
            existing_hash = None  # 손상되거나 인코딩이 다른 파일이면 그냥 새로 씀

    if existing_hash is not None and existing_hash == content_hash:
        return "unchanged"

    action = "updated" if file_path.exists() else "created"
    if not dry_run:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(md, encoding='utf-8')
    return action
