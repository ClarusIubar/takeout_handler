# --help가 죽지 않고 정상 종료하는지 (argparse 기본 동작: SystemExit(0)).
import pytest

import run

pytestmark = pytest.mark.smoke


def test_help_exits_zero(patched_config_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["run.py", "--help"])

    with pytest.raises(SystemExit) as exc_info:
        run.main()

    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "--vendor" in out
    assert "--dry-run" in out
