"""sync_takeout tool의 부작용(raw export -> result_dir 재생성)을 구현한다.

run.py:run_vendor()를 블랙박스로 재사용한다 — 새 파싱/변환 로직을 만들지 않는다.
단, run_vendor()는 진행 상황을 print()로 stdout에 찍는데, MCP stdio transport는
stdout을 JSON-RPC 메시지 채널로 쓰므로 그 출력이 그대로 나가면 프로토콜이 깨진다.
그래서 호출을 감싸 stdout을 캡처하고, 캡처한 로그 텍스트를 반환값으로 넘긴다(어차피
tool 응답에 넣어 클라이언트에게 보여주면 되는 정보라 버릴 이유가 없다).
"""

import contextlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import run as _run  # noqa: E402
from vendors import base  # noqa: E402


def discover_vendors():
    return base.discover()


def sync_vendor(name, module, dry_run, data_dir, result_dir):
    """단일 벤더에 대해 run.py:run_vendor()를 호출한다.

    반환값: (stats: ConvertStats | None, log_text: str). data_dir이 없으면
    run_vendor()가 stats=None을 반환하는 경우와 동일하게 그대로 전달한다."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        stats = _run.run_vendor(name, module, dry_run, Path(data_dir), Path(result_dir))
    return stats, buf.getvalue()
