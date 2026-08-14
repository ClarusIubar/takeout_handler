# 최소 픽스처로 --dry-run 한 번이 예외 없이 끝까지 도는지만 확인하는 얕은 확인.
# 결과물의 세부 내용(frontmatter, turn 주석 등) 검증은 tests/integration/의 몫이다.
import pytest

import run

pytestmark = pytest.mark.smoke


def test_dry_run_single_vendor_completes_without_exception(
    tmp_path, minimal_chatgpt_export, patched_config_path, monkeypatch, capsys
):
    data_dir = tmp_path / "chatgpt_src"
    minimal_chatgpt_export(data_dir)

    monkeypatch.setattr("sys.argv", [
        "run.py",
        "--vendor", "chatgpt",
        "--input", f"chatgpt={data_dir}",
        "--output-dir", str(tmp_path / "result"),
        "--dry-run",
    ])

    run.main()  # 여기서 예외/SystemExit이 나면 이 테스트가 곧바로 실패

    out = capsys.readouterr().out
    assert "세션 1개" in out
    assert "--dry-run: 실제 파일은 생성되지 않았습니다" in out
