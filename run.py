"""ChatGPT + Gemini Takeout -> Markdown 통합 파이프라인 CLI.

data/<vendor>/ 에 벤더가 준 원본 export를 그대로 넣고 실행하면(zip 그대로든, 미리
압축을 풀어놨든 상관없음), data/ 아래 존재가 감지되는 벤더만 자동으로 골라
result/<vendor>/ 에 마크다운을 생성한다.

원본 파일이 data/<vendor>/에 있지 않아도(예: 다운로드 폴더에 그대로 있는 zip)
--input으로 위치를 직접 지정할 수 있다 — 경로를 코드에 박아넣을 필요 없음.

    python run.py                   # 감지되는 벤더 전부 (data/<vendor>/ 기준)
    python run.py --vendor chatgpt  # ChatGPT만
    python run.py --vendor gemini   # Gemini만
    python run.py --dry-run         # 실제 파일 생성 없이 미리보기 로그만
    python run.py --input gemini="C:\\Users\\me\\Downloads\\takeout.zip"
                                     # data/gemini/ 대신 이 zip을 원본으로 사용
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.zip_extract import extract_all_zips, extract_zip  # noqa: E402
from vendors import base  # noqa: E402

# vendors/ 디렉터리를 스캔해서 벤더 모듈을 자동으로 찾는다 (각 모듈은 discover() 안에서
# base.validate()로 인터페이스 검증까지 끝낸 상태). 새 벤더를 추가할 때 여기를 고칠
# 필요 없이 vendors/<name>.py 파일만 놓으면 된다.
VENDORS = base.discover()

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RESULT_DIR = ROOT / "result"

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


def resolve_input(name: str, raw_path: str) -> Path:
    """--input <name>=<raw_path>로 받은 경로를 실제 data_dir로 바꾼다.

    - 폴더면 그 폴더를 그대로 data_dir로 쓴다 (원본 위치를 전혀 건드리지 않음).
    - .zip 파일이면 원본은 그대로 두고, 내용만 DATA_DIR/<name>/에 압축 해제해서
      거기를 data_dir로 쓴다 (사용자의 원본 다운로드 폴더에 수백 개 파일을
      흩뿌리지 않기 위함 — 압축 해제 결과물은 항상 이 프로젝트가 관리하는
      gitignore된 data/ 아래에만 생긴다).
    """
    src = Path(raw_path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"--input {name}={raw_path}: 경로가 존재하지 않습니다")
    if src.is_dir():
        return src
    if src.suffix.lower() == ".zip":
        dest = DATA_DIR / name
        extract_zip(src, dest)
        return dest
    raise ValueError(f"--input {name}={raw_path}: 폴더 또는 .zip 파일이어야 합니다")


def run_vendor(name: str, module: base.VendorModule, dry_run: bool, data_dir: Path):
    result_dir = RESULT_DIR / name

    print("=" * 60)
    print(f"[{module.VENDOR_LABEL}] data_dir={data_dir}")
    print("=" * 60)

    if not data_dir.exists():
        print(f"[건너뜀] {data_dir} 에서 {module.VENDOR_LABEL} takeout 데이터를 찾지 못했습니다.")
        return None

    if not module.detect(data_dir):
        # 이미 풀려있는 데이터가 없으면, zip을 그대로 넣었다고 가정하고 풀어본 뒤 다시 감지.
        # 이미 압축이 풀려있었다면(예전 방식) 여기서 zip이 안 잡히므로 그냥 넘어간다.
        extracted = extract_all_zips(data_dir)
        if extracted:
            print(f"[{module.VENDOR_LABEL}] zip {extracted}개 압축 해제함")

    if not module.detect(data_dir):
        print(f"[건너뜀] {data_dir} 에서 {module.VENDOR_LABEL} takeout 데이터를 찾지 못했습니다.")
        return None

    stats = module.convert(data_dir, result_dir, dry_run)

    print()
    print(f"[{module.VENDOR_LABEL}] 결과: 세션 {stats.sessions_found}개 중 "
          f"파일 {stats.files_written}개 생성, 빈 대화 {stats.empty_skipped}개 스킵")
    print(f"[{module.VENDOR_LABEL}] 첨부파일: 해석 성공 {stats.attachments_ok}개 / "
          f"원본 없음 {stats.attachments_missing}개")
    if stats.parse_errors:
        print(f"[{module.VENDOR_LABEL}] ⚠️ 파싱 실패 {stats.parse_errors}건 — 위 로그의 [경고] 확인 필요")
    if dry_run:
        print(f"[{module.VENDOR_LABEL}] --dry-run: 실제 파일은 생성되지 않았습니다.")
    print()
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--vendor", choices=sorted(VENDORS), action="append",
                         help="특정 벤더만 실행 (여러 번 지정 가능). 생략하면 감지되는 벤더 전부 실행.")
    parser.add_argument("--dry-run", action="store_true",
                         help="실제 파일을 생성하지 않고 파싱 결과만 미리 확인.")
    parser.add_argument("--input", action="append", default=[], metavar="VENDOR=PATH",
                         help="특정 벤더의 원본 데이터 위치를 data/<vendor>/ 대신 직접 지정 "
                              "(폴더 또는 .zip 파일, 여러 번 지정 가능). "
                              '예: --input gemini="C:\\Users\\me\\Downloads\\takeout.zip"')
    args = parser.parse_args()

    targets = args.vendor or list(VENDORS)

    inputs = {}
    for item in args.input:
        if "=" not in item:
            parser.error(f"--input은 VENDOR=PATH 형식이어야 합니다: {item}")
        name, raw_path = item.split("=", 1)
        if name not in VENDORS:
            parser.error(f"--input: 알 수 없는 벤더 '{name}' (사용 가능: {', '.join(sorted(VENDORS))})")
        inputs[name] = raw_path

    results = {}
    for name in targets:
        module = VENDORS[name]
        if name in inputs:
            try:
                data_dir = resolve_input(name, inputs[name])
            except (FileNotFoundError, ValueError) as exc:
                print(f"[오류] {exc}")
                results[name] = None
                continue
        else:
            data_dir = DATA_DIR / name
        results[name] = run_vendor(name, module, args.dry_run, data_dir)

    ran = {name: s for name, s in results.items() if s is not None}
    if not ran:
        print("실행된 벤더가 없습니다. data/<vendor>/ 에 raw takeout을 넣었는지 확인하세요.")
        sys.exit(1)

    failed = {name: s for name, s in ran.items() if s.parse_errors > 0}
    if failed:
        print("일부 파일이 파싱에 실패했습니다 (부분 성공):")
        for name, s in failed.items():
            print(f"  - {name}: {s.parse_errors}건")
        sys.exit(2)


if __name__ == "__main__":
    main()
