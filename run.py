"""ChatGPT + Gemini Takeout -> Markdown 통합 파이프라인 CLI.

data/<vendor>/ 에 raw takeout을 넣고 실행하면, data/ 아래 존재가 감지되는 벤더만
자동으로 골라 result/<vendor>/ 에 마크다운을 생성한다.

    python run.py                   # 감지되는 벤더 전부
    python run.py --vendor chatgpt  # ChatGPT만
    python run.py --vendor gemini   # Gemini만
    python run.py --dry-run         # 실제 파일 생성 없이 미리보기 로그만
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vendors import chatgpt, gemini  # noqa: E402

VENDORS = {
    "chatgpt": chatgpt,
    "gemini": gemini,
}

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RESULT_DIR = ROOT / "result"

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


def run_vendor(name, module, dry_run):
    data_dir = DATA_DIR / name
    result_dir = RESULT_DIR / name

    print("=" * 60)
    print(f"[{module.VENDOR_LABEL}] data_dir={data_dir}")
    print("=" * 60)

    if not data_dir.exists() or not module.detect(data_dir):
        print(f"[건너뜀] {data_dir} 에서 {module.VENDOR_LABEL} takeout 데이터를 찾지 못했습니다.")
        return None

    stats = module.convert(data_dir, result_dir, dry_run)

    print()
    print(f"[{module.VENDOR_LABEL}] 결과: 세션 {stats.sessions_found}개 중 "
          f"파일 {stats.files_written}개 생성, 빈 대화 {stats.empty_skipped}개 스킵")
    print(f"[{module.VENDOR_LABEL}] 첨부파일: 해석 성공 {stats.attachments_ok}개 / "
          f"원본 없음 {stats.attachments_missing}개")
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
    args = parser.parse_args()

    targets = args.vendor or list(VENDORS)

    results = {}
    for name in targets:
        module = VENDORS[name]
        results[name] = run_vendor(name, module, args.dry_run)

    ran = {name: s for name, s in results.items() if s is not None}
    if not ran:
        print("실행된 벤더가 없습니다. data/<vendor>/ 에 raw takeout을 넣었는지 확인하세요.")
        sys.exit(1)


if __name__ == "__main__":
    main()
