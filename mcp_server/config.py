"""mcp_server 전용 경로 해석.

common.config.load_config()를 재사용하고, run.py와 동일하게
CLI 플래그 > config.json > 내장 기본값 우선순위를 따른다. run.py의 CONFIG/DATA_DIR
전역 상태에는 의존하지 않는다 — mcp_server는 run.py와 별도 프로세스로 뜨므로 독립적으로
해석한다.
"""

import argparse
from pathlib import Path

from common.config import load_config
from common.zip_extract import extract_zip
from vendors import base

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def build_arg_parser():
    parser = argparse.ArgumentParser(
        prog="python -m mcp_server",
        description="Takeout 파이프라인 결과를 MCP 서버로 노출한다 (stdio transport).",
    )
    parser.add_argument("--source", choices=["result", "vault"], default="result",
                         help="조회 대상 루트: 'result'(markdown_output_dir, 기본값) 또는 "
                              "'vault'(obsidian_vault_dir).")
    parser.add_argument("--result-dir", metavar="PATH",
                         help="--source result일 때 사용할 경로를 이번 실행만 오버라이드.")
    parser.add_argument("--vault-dir", metavar="PATH",
                         help="--source vault일 때 사용할 경로를 이번 실행만 오버라이드.")
    return parser


def _resolve_data_dir(name: str, raw_path):
    """config.json의 takeout_paths.<name>을 실제 data_dir로 바꾼다 (run.py:resolve_input과
    동일한 규칙: 폴더면 그대로, .zip이면 DATA_DIR/<name>/에 풀어서 씀). 설정이 없으면
    data/<name>/ 기본값."""
    if not raw_path:
        return DATA_DIR / name
    src = Path(raw_path).expanduser().resolve()
    if src.is_dir():
        return src
    if src.suffix.lower() == ".zip":
        dest = DATA_DIR / name
        extract_zip(src, dest)
        return dest
    return DATA_DIR / name


def resolve_server_paths(cli_args=None, config=None):
    """(result_dir: Path, data_dirs: {vendor_tag: Path}) 튜플을 반환한다.

    result_dir: 조회 tool/resource가 읽어올 루트 (--source에 따라 markdown_output_dir
        또는 obsidian_vault_dir).
    data_dirs: sync_takeout이 참조할 벤더별 raw export 위치, 감지되는 벤더 전체에 대해 채움."""
    if cli_args is None:
        cli_args = build_arg_parser().parse_args([])
    if config is None:
        config = load_config()

    if cli_args.source == "vault":
        raw = cli_args.vault_dir or config.get("obsidian_vault_dir")
        if not raw:
            raise ValueError(
                "--source vault를 쓰려면 obsidian_vault_dir이 필요합니다 "
                "(--vault-dir로 지정하거나 config.json에 설정하세요)."
            )
        result_dir = Path(raw).expanduser().resolve()
    else:
        raw = cli_args.result_dir or config.get("markdown_output_dir") or "result"
        p = Path(raw).expanduser()
        result_dir = (p if p.is_absolute() else (ROOT / p)).resolve()

    vendors = base.discover()
    takeout_paths = config.get("takeout_paths", {})
    data_dirs = {name: _resolve_data_dir(name, takeout_paths.get(name)) for name in vendors}

    return result_dir, data_dirs
