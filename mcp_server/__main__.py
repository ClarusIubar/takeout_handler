"""python -m mcp_server 진입점.

stdio transport로 뜨는 MCP 서버는 stdout을 JSON-RPC 메시지 채널로 쓰므로, 여기서 찍는
모든 진단 메시지는 stdout이 아니라 stderr로 보낸다 (run.py는 일반 CLI라 stdout에 찍지만,
이 모듈은 그 관례를 따르지 않는다 — 클라이언트가 프로세스를 띄우자마자 stdout을 프레이밍된
메시지로 읽기 시작할 수 있기 때문).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass


def main():
    from common.config import load_config
    from mcp_server.config import build_arg_parser, resolve_server_paths

    args = build_arg_parser().parse_args()

    try:
        result_dir, data_dirs = resolve_server_paths(args, load_config())
    except ValueError as exc:
        print(f"[오류] {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        from mcp_server.server import create_server
    except ImportError:
        print(
            "[오류] mcp 패키지가 설치돼 있지 않습니다. "
            "`pip install -e .[mcp]` 또는 `pip install -r requirements-mcp.txt`로 설치한 뒤 다시 실행하세요.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"[mcp_server] source={args.source} result_dir={result_dir}", file=sys.stderr)
    server = create_server(result_dir, data_dirs=data_dirs)
    server.run("stdio")


if __name__ == "__main__":
    main()
