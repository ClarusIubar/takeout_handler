# mcp_server/ 관련 가장 얕고 빠른 확인. mcp_server.config/index/pipeline/__main__은
# mcp SDK를 지연 임포트(main() 함수 안에서만)하므로 mcp 미설치 환경에서도 항상 돈다.
import importlib
import sys

import pytest

import mcp_server.__main__ as mcp_main

pytestmark = pytest.mark.smoke


def test_mcp_server_modules_import_without_mcp_installed():
    for name in ["mcp_server", "mcp_server.config", "mcp_server.index", "mcp_server.pipeline", "mcp_server.__main__"]:
        importlib.import_module(name)


def test_help_exits_zero_without_mcp_installed(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["mcp_server", "--help"])

    with pytest.raises(SystemExit) as exc_info:
        mcp_main.main()

    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "--source" in out


def test_missing_mcp_package_prints_install_hint_and_exits_1(monkeypatch, capsys, patched_config_path):
    # mcp가 실제로 설치돼 있는 환경에서도 "설치 안 됨" 경로를 검증할 수 있도록,
    # mcp_server.server 임포트만 강제로 실패시킨다 (sys.modules에 None을 넣으면 다음
    # `from mcp_server.server import ...`가 ImportError를 던지는 표준 트릭).
    monkeypatch.setitem(sys.modules, "mcp_server.server", None)
    monkeypatch.setattr("sys.argv", ["mcp_server"])

    with pytest.raises(SystemExit) as exc_info:
        mcp_main.main()

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "mcp" in err
    assert "requirements-mcp.txt" in err
