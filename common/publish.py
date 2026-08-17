"""result/<vendor>/의 변환된 마크다운을 실제 옵시디언 vault로 미러링(upsert)한다.

result/는 이 프로젝트가 관리하는 내부 스테이징 영역이고, vault는 사용자의 실제 PKM
저장소다. 이 둘을 분리해서 --publish라는 명시적 단계로만 vault에 쓰는 이유는, 실제
vault에 파일을 쓰는 건 되돌리기 까다로운 작업이라 사용자가 result/의 변환 결과를
먼저 검토한 뒤 명시적으로 반영하도록 하기 위함이다.

vault 안에서 파일 위치가 바뀌어도(사용자가 손수 다른 폴더로 옮겼거나 이름을 바꿨어도)
추적하지 않는다 — vault_dir/<filename> 위치만 기준으로 단순 미러링한다. 세션 내용이
바뀌면 사용자가 옮긴 자리가 아니라 원래 위치(vault_dir/<filename>)에 새로 하나가 다시
생길 수 있다 — vault 전체를 뒤져서 옮겨진 파일을 찾아내는 건 이번 범위 밖이다.

result_dir은 하위 폴더를 가질 수 있다 (예: Claude 벤더의 result/claude/<project명>/*.md
— 프로젝트별로 분리된 대화). rglob으로 재귀 탐색하고 result_dir 기준 상대 경로를 그대로
vault_dir에 재현한다. 같은 이유로 프로젝트 이름이 나중에 바뀌면(폴더명이 프로젝트명
기반이므로) 새 폴더에 파일이 다시 생기고, 예전 폴더에는 고아 파일이 남을 수 있다 —
이것도 위와 같은 성격의 한계라 별도로 추적하지 않는다.
"""

from pathlib import Path

from common.session_markdown import extract_content_hash
from common.upsert import write_upsert


def publish_vendor(result_dir: Path, vault_dir: Path, dry_run: bool):
    """result_dir의 모든 .md(+ Attachments/)를 vault_dir로 upsert 미러링한다.

    반환값: dict(created=, updated=, unchanged=, attachments_copied=)
    """
    stats = {"created": 0, "updated": 0, "unchanged": 0, "attachments_copied": 0}

    if not result_dir.exists():
        return stats

    for md_path in sorted(result_dir.rglob("*.md")):
        # newline='' : 유니버설 개행 변환을 끈다. result/의 파일도 이미 newline=''로
        # 쓰였으므로(common/upsert.py) 있는 그대로 읽어야 vault에도 정확히 같은
        # 바이트가 그대로 옮겨간다 — 안 그러면 읽고 다시 쓰는 것만으로 내용이 바뀐다.
        text = md_path.read_text(encoding="utf-8", newline="")
        content_hash = extract_content_hash(text)
        dest = vault_dir / md_path.relative_to(result_dir)
        action = write_upsert(dest, text, content_hash, dry_run)
        stats[action] += 1

    attachments_src = result_dir / "Attachments"
    if attachments_src.exists():
        attachments_dest = vault_dir / "Attachments"
        for src_file in sorted(attachments_src.iterdir()):
            if not src_file.is_file():
                continue
            dest_file = attachments_dest / src_file.name
            if dest_file.exists():
                continue
            if not dry_run:
                attachments_dest.mkdir(parents=True, exist_ok=True)
                dest_file.write_bytes(src_file.read_bytes())
            stats["attachments_copied"] += 1

    return stats
