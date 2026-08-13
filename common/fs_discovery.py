"""파일 탐색 시 압축 도구/OS가 남기는 쓰레기 경로를 걸러내는 공통 판별.

macOS에서 압축되거나 AirDrop/클라우드를 거친 zip에는 흔히 `__MACOSX/` 리소스 포크
사본이 원본과 나란히 들어있다. `__MACOSX`가 알파벳순으로 정상 폴더명보다 앞에 오는
경우가 많아서, "재귀 탐색 후 정렬해서 첫 번째를 고른다" 같은 로직은 이 쓰레기 사본을
조용히 선택할 위험이 있다. 벤더별 순회 방식(rglob, os.walk 등)은 다르게 유지하되,
"이 경로가 쓰레기인가"라는 판단 하나만 여기서 공유한다.
"""

from pathlib import Path

JUNK_DIR_NAMES = {"__MACOSX"}


def is_junk_segment(part: str) -> bool:
    """경로 세그먼트 하나(폴더명 또는 파일명)가 __MACOSX이거나 .으로 시작하면
    (리소스 포크/숨김 파일류) True. zip 엔트리 이름 문자열에도, 실제 파일시스템
    Path에도 똑같이 쓸 수 있도록 문자열 단위로 판단한다."""
    return part in JUNK_DIR_NAMES or part.startswith('.')


def is_junk_path(path: Path, root: Path) -> bool:
    """root 기준 path의 상대 경로 세그먼트(파일명 포함) 어디든 쓰레기면 True."""
    rel_parts = path.relative_to(root).parts
    return any(is_junk_segment(part) for part in rel_parts)


def pick_primary(candidates, label: str):
    """탐색 후보 리스트(쓰레기 경로는 이미 제외됐고, 얕은 순으로 정렬돼 있다고 가정)
    중 가장 얕은 것을 고른다. 후보가 2개 이상이면(재실행 잔여물, 압축 중복 등으로 진짜
    모호한 경우) 전부 나열하는 경고를 찍는다.

    반환값: (선택된 경로, 모호했는지 여부). 모호 여부는 호출자가 ConvertStats.parse_errors를
    올릴지 판단하는 데 쓴다 — 완전 실패는 아니지만 사용자 확인이 필요한 상태라 조용히
    넘어가면 안 된다."""
    chosen = candidates[0]
    ambiguous = len(candidates) > 1
    if ambiguous:
        print(f"[경고] {label}이(가) 서로 다른 위치 {len(candidates)}곳에서 발견됨 "
              "(재실행 잔여물이나 압축 중복 가능성):")
        for c in candidates:
            print(f"    - {c}")
        print(f"  -> 가장 상위 경로를 사용: {chosen}")
    return chosen, ambiguous
