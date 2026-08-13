"""벤더가 주는 원본 zip을 그대로 data/<vendor>/에 넣어도 동작하도록, 파싱 전에
그 자리에서 압축을 풀어주는 유틸리티.

벤더별 detect()/convert()는 이미 풀려있는 파일 구조만 알면 되고, "사용자가 압축을
미리 풀어서 정리해줬다"는 가정은 여기서 없앤다 — 호출자(run.py)가 detect()로 먼저
확인해서 이미 데이터가 있으면 건드리지 않고, 없을 때만 호출한다.
"""

import zipfile
from pathlib import Path, PurePosixPath

from common.fs_discovery import is_junk_segment


def _member_parts(filename: str):
    """zip 엔트리 이름은 스펙상 '/' 구분자를 쓰지만, 일부 비표준 도구가 '\\'를 쓰기도
    해서 정규화 후 순수 posix 경로 세그먼트로 쪼갠다."""
    return PurePosixPath(filename.replace('\\', '/')).parts


def _is_safe_member(filename: str) -> bool:
    """zip slip(경로 탈출) 방어: 절대경로거나 '..' 세그먼트가 있으면 안전하지 않다고
    본다. extractall()의 암묵적 방어에만 기대지 않고 명시적으로 걸러서, run.py --input
    으로 사용자가 임의 zip 경로를 넘길 수 있는 경로에서도 목적지 밖으로 못 벗어나게 한다."""
    normalized = filename.replace('\\', '/')
    if PurePosixPath(normalized).is_absolute():
        return False
    parts = _member_parts(filename)
    return bool(parts) and '..' not in parts


def _is_junk_member(filename: str) -> bool:
    return any(is_junk_segment(part) for part in _member_parts(filename))


def extract_zip(zip_path: Path, dest_dir: Path) -> None:
    """zip_path 하나를 dest_dir에 압축 해제한다. 원본 zip은 건드리지 않는다.
    경로 탈출(zip slip) 시도가 있는 엔트리는 경고와 함께 건너뛰고, __MACOSX/ 등
    압축 도구가 남기는 쓰레기 엔트리는 조용히 건너뛴다 (애초에 안 써서, 나중에
    vendors 쪽 탐색 로직이 또 걸러낼 필요가 없게 깨끗한 상태로 만든다)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            if not _is_safe_member(member.filename):
                print(f"[경고] {zip_path.name}: 안전하지 않은 경로라 압축 해제에서 건너뜀 - {member.filename}")
                continue
            if _is_junk_member(member.filename):
                continue
            zf.extract(member, dest_dir)


def extract_all_zips(data_dir: Path) -> int:
    """data_dir 바로 아래 있는 모든 *.zip을 그 자리에 압축 해제한다.

    Google Takeout처럼 대용량 export가 여러 파트 zip으로 쪼개지는 경우, 파트마다
    그 자체로 유효한 zip이고 같은 상위 폴더 구조(예: Takeout/...)를 공유하므로
    순서 상관없이 전부 같은 위치에 풀면 자연스럽게 합쳐진다.

    zip 파일 자체는 지우지 않는다 (사용자의 원본 다운로드 보존). detect()가 찾는
    파일 확장자(.json/.html)와 겹치지 않으므로 이후 탐색에는 영향 없다.

    반환값: 실제로 처리한 zip 개수.
    """
    if not data_dir.exists():
        return 0
    zips = sorted(data_dir.glob("*.zip"))
    for zip_path in zips:
        extract_zip(zip_path, data_dir)
    return len(zips)
