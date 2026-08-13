"""ChatGPT + Gemini Takeout -> Markdown 통합 파이프라인 CLI.

data/<vendor>/ 에 벤더가 준 원본 export를 그대로 넣고 실행하면(zip 그대로든, 미리
압축을 풀어놨든 상관없음), data/ 아래 존재가 감지되는 벤더만 자동으로 골라
result/<vendor>/ 에 마크다운을 생성한다.

세 가지 경로(takeout 원본, 마크다운 변환 결과, 실제 옵시디언 vault)는 모두
config.json으로 기본값을 설정할 수 있고, 필요할 때만 CLI로 이번 실행 한정
오버라이드할 수 있다 (우선순위: CLI 플래그 > config.json > 내장 기본값).
config.json이 없으면 처음 실행할 때 기본값으로 자동 생성된다.

    python run.py                   # 감지되는 벤더 전부 (config/기본값 경로 기준)
    python run.py --vendor chatgpt  # ChatGPT만
    python run.py --vendor gemini   # Gemini만
    python run.py --dry-run         # 실제 파일 생성 없이 미리보기 로그만
    python run.py --input gemini="C:\\Users\\me\\Downloads\\takeout.zip"
                                     # 이번 실행만 이 zip을 원본으로 사용
    python run.py --output-dir "D:\\md-out"
                                     # 이번 실행만 마크다운 출력 경로 변경
    python run.py --publish         # 변환 후 config.json의 obsidian_vault_dir로 발행
    python run.py --publish --vault-dir "D:\\MyVault"
                                     # 이번 실행만 다른 vault로 발행
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.config import load_config  # noqa: E402
from common.publish import publish_vendor  # noqa: E402
from common.zip_extract import extract_all_zips, extract_zip  # noqa: E402
from vendors import base  # noqa: E402

# vendors/ 디렉터리를 스캔해서 벤더 모듈을 자동으로 찾는다 (각 모듈은 discover() 안에서
# base.validate()로 인터페이스 검증까지 끝낸 상태). 새 벤더를 추가할 때 여기를 고칠
# 필요 없이 vendors/<name>.py 파일만 놓으면 된다.
VENDORS = base.discover()

# main() 안에서 채운다 (import run만 해도 config.json이 없으면 자동 생성되는 부작용이
# 생기지 않도록 — 예: 테스트가 run.py를 import하기만 해도 실제 프로젝트의 config.json이
# 조용히 만들어지는 걸 막는다). resolve_source()/resolve_output_dir()/resolve_vault_dir()는
# 이 전역을 참조하므로, 테스트에서는 monkeypatch로 직접 값을 주입해서 쓴다.
CONFIG = None

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


def resolve_input(name: str, raw_path: str) -> Path:
    """<name>의 takeout 원본 경로 문자열(CLI --input 또는 config.json의 takeout_paths에서
    옴)을 실제 data_dir로 바꾼다.

    - 폴더면 그 폴더를 그대로 data_dir로 쓴다 (원본 위치를 전혀 건드리지 않음).
    - .zip 파일이면 원본은 그대로 두고, 내용만 DATA_DIR/<name>/에 압축 해제해서
      거기를 data_dir로 쓴다 (사용자의 원본 다운로드 폴더에 수백 개 파일을
      흩뿌리지 않기 위함 — 압축 해제 결과물은 항상 이 프로젝트가 관리하는
      gitignore된 data/ 아래에만 생긴다).
    """
    src = Path(raw_path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"{name}={raw_path}: 경로가 존재하지 않습니다")
    if src.is_dir():
        return src
    if src.suffix.lower() == ".zip":
        dest = DATA_DIR / name
        extract_zip(src, dest)
        return dest
    raise ValueError(f"{name}={raw_path}: 폴더 또는 .zip 파일이어야 합니다")


def resolve_source(name: str, cli_value):
    """벤더 <name>의 takeout 원본 data_dir을 우선순위대로 정한다:
    --input CLI 값 > config.json의 takeout_paths.<name> > data/<name>/ 기본값."""
    if cli_value:
        return resolve_input(name, cli_value)
    configured = CONFIG.get("takeout_paths", {}).get(name)
    if configured:
        return resolve_input(name, configured)
    return DATA_DIR / name


def resolve_output_dir(cli_value):
    """마크다운 변환 결과 경로를 우선순위대로 정한다:
    --output-dir CLI 값 > config.json의 markdown_output_dir > result/ 기본값."""
    raw = cli_value or CONFIG.get("markdown_output_dir") or "result"
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = ROOT / p
    return p.resolve()


def resolve_vault_dir(cli_value):
    """실제 옵시디언 vault 경로를 우선순위대로 정한다:
    --vault-dir CLI 값 > config.json의 obsidian_vault_dir > 미설정(None)."""
    raw = cli_value or CONFIG.get("obsidian_vault_dir")
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def run_vendor(name: str, module: base.VendorModule, dry_run: bool, data_dir: Path, result_dir: Path):
    print("=" * 60)
    print(f"[{module.VENDOR_LABEL}] data_dir={data_dir}")
    print(f"[{module.VENDOR_LABEL}] result_dir={result_dir}")
    print("=" * 60)

    if not data_dir.exists():
        print(f"[건너뜀] {data_dir} 에서 {module.VENDOR_LABEL} takeout 데이터를 찾지 못했습니다.")
        return None

    zip_extracted = 0
    if not module.detect(data_dir):
        # 이미 풀려있는 데이터가 없으면, zip을 그대로 넣었다고 가정하고 풀어본 뒤 다시 감지.
        # 이미 압축이 풀려있었다면(예전 방식) 여기서 zip이 안 잡히므로 그냥 넘어간다.
        zip_extracted = extract_all_zips(data_dir)
        if zip_extracted:
            print(f"[{module.VENDOR_LABEL}] zip {zip_extracted}개 압축 해제함")

    if not module.detect(data_dir):
        if zip_extracted:
            # zip은 풀었는데도 여전히 못 찾음 — "아무것도 없음"과는 원인이 다르므로
            # (구조가 예상과 다름 등) 사용자가 헷갈리지 않게 구분해서 알린다.
            print(f"[건너뜀] {data_dir}: zip {zip_extracted}개를 풀었지만 "
                  f"{module.VENDOR_LABEL} takeout 구조를 여전히 인식하지 못했습니다. "
                  "README의 실제 export 구조를 확인하세요.")
        else:
            print(f"[건너뜀] {data_dir} 에서 {module.VENDOR_LABEL} takeout 데이터를 찾지 못했습니다.")
        return None

    stats = module.convert(data_dir, result_dir, dry_run)

    print()
    print(f"[{module.VENDOR_LABEL}] 결과: 세션 {stats.sessions_found}개 중 "
          f"신규 {stats.files_created}개 / 갱신 {stats.files_updated}개 / "
          f"변경없음 {stats.files_unchanged}개, 빈 대화 {stats.empty_skipped}개 스킵")
    print(f"[{module.VENDOR_LABEL}] 첨부파일: 해석 성공 {stats.attachments_ok}개 / "
          f"원본 없음 {stats.attachments_missing}개")
    if stats.parse_errors:
        print(f"[{module.VENDOR_LABEL}] ⚠️ 파싱 실패 {stats.parse_errors}건 — 위 로그의 [경고] 확인 필요")
    if dry_run:
        print(f"[{module.VENDOR_LABEL}] --dry-run: 실제 파일은 생성되지 않았습니다.")
    print()
    return stats


def publish_vendors(names, result_dir: Path, vault_dir, dry_run: bool):
    """--publish로 변환이 끝난 벤더들을 vault_dir/<vendor_subdir>/로 미러링한다.
    vault_dir이 없으면(설정 안 됨) 안내만 하고 아무것도 안 쓴다."""
    if vault_dir is None:
        print("[안내] obsidian_vault_dir이 config.json에 설정돼 있지 않습니다. "
              "--vault-dir로 이번 실행만 지정하거나 config.json을 직접 고치세요. "
              "발행 단계는 건너뜁니다.")
        return

    vault_subdirs = CONFIG.get("vault_subdirs", {})
    for name in names:
        subdir = vault_subdirs.get(name, name)
        vendor_vault_dir = vault_dir / subdir
        stats = publish_vendor(result_dir / name, vendor_vault_dir, dry_run)
        print(f"[발행:{name}] {vendor_vault_dir} <- 신규 {stats['created']}개 / "
              f"갱신 {stats['updated']}개 / 변경없음 {stats['unchanged']}개, "
              f"첨부파일 {stats['attachments_copied']}개 복사")
        if dry_run:
            print(f"[발행:{name}] --dry-run: 실제 파일은 생성되지 않았습니다.")


def main():
    global CONFIG
    CONFIG = load_config()

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--vendor", choices=sorted(VENDORS), action="append",
                         help="특정 벤더만 실행 (여러 번 지정 가능). 생략하면 감지되는 벤더 전부 실행.")
    parser.add_argument("--dry-run", action="store_true",
                         help="실제 파일을 생성하지 않고 파싱 결과만 미리 확인.")
    parser.add_argument("--input", action="append", default=[], metavar="VENDOR=PATH",
                         help="특정 벤더의 원본 데이터 위치를 이번 실행만 직접 지정 "
                              "(폴더 또는 .zip 파일, 여러 번 지정 가능). config.json의 "
                              "takeout_paths보다 우선한다. "
                              '예: --input gemini="C:\\Users\\me\\Downloads\\takeout.zip"')
    parser.add_argument("--output-dir", metavar="PATH",
                         help="마크다운 변환 결과 경로를 이번 실행만 지정 (기본: config.json의 "
                              "markdown_output_dir, 미설정이면 result/).")
    parser.add_argument("--vault-dir", metavar="PATH",
                         help="--publish 시 사용할 옵시디언 vault 경로를 이번 실행만 지정 "
                              "(기본: config.json의 obsidian_vault_dir).")
    parser.add_argument("--publish", action="store_true",
                         help="변환 후 vault_dir/<벤더별 하위폴더>/로 마크다운·첨부파일을 "
                              "upsert 미러링한다 (session_id/파일명 기준, 사용자가 vault 안에서 "
                              "옮긴 파일은 추적하지 않음).")
    args = parser.parse_args()

    targets = args.vendor or list(VENDORS)
    result_dir = resolve_output_dir(args.output_dir)
    vault_dir = resolve_vault_dir(args.vault_dir)

    print(f"[config] 마크다운 출력 경로: {result_dir}")
    print(f"[config] vault 경로: {vault_dir if vault_dir else '미설정'}")
    print()

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
        try:
            data_dir = resolve_source(name, inputs.get(name))
        except (FileNotFoundError, ValueError) as exc:
            print(f"[오류] {exc}")
            results[name] = None
            continue
        results[name] = run_vendor(name, module, args.dry_run, data_dir, result_dir / name)

    ran = {name: s for name, s in results.items() if s is not None}
    if not ran:
        print("실행된 벤더가 없습니다. data/<vendor>/ 에 raw takeout을 넣었는지 확인하세요.")
        sys.exit(1)

    if args.publish:
        publish_vendors(list(ran), result_dir, vault_dir, args.dry_run)

    failed = {name: s for name, s in ran.items() if s.parse_errors > 0}
    if failed:
        print("일부 파일이 파싱에 실패했습니다 (부분 성공):")
        for name, s in failed.items():
            print(f"  - {name}: {s.parse_errors}건")
        sys.exit(2)


if __name__ == "__main__":
    main()
