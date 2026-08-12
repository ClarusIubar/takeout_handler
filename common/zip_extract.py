"""벤더가 주는 원본 zip을 그대로 data/<vendor>/에 넣어도 동작하도록, 파싱 전에
그 자리에서 압축을 풀어주는 유틸리티.

벤더별 detect()/convert()는 이미 풀려있는 파일 구조만 알면 되고, "사용자가 압축을
미리 풀어서 정리해줬다"는 가정은 여기서 없앤다 — 호출자(run.py)가 detect()로 먼저
확인해서 이미 데이터가 있으면 건드리지 않고, 없을 때만 호출한다.
"""

import zipfile
from pathlib import Path


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
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(data_dir)
    return len(zips)
