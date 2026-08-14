# run.main()의 종료 코드 계약을 CLI 진입점 레벨에서 고정한다:
# 실행된 벤더가 하나도 없으면 exit 1, 실행됐지만 parse_errors>0인 벤더가 있으면 exit 2.
# 지금까지 개별 헬퍼 함수(예: _load_conversations의 non-list 감지)는 유닛 테스트가
# 있었지만, 그게 실제로 main()의 종료 코드까지 이어지는지 검증하는 테스트는 없었다.
#
# 두 테스트 모두 --input으로 실제 존재하는 빈/이상 tmp 디렉터리를 명시적으로 넘긴다 —
# --input을 생략하면 resolve_source가 DATA_DIR/<vendor>/(실제 프로젝트의 data/ 폴더,
# 개인 데이터가 들어있을 수 있음)로 폴백하므로 절대 생략하면 안 된다.
import json

import pytest

import run

pytestmark = pytest.mark.integration


def test_no_vendor_data_exits_1(tmp_path, patched_config_path, monkeypatch):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    monkeypatch.setattr("sys.argv", [
        "run.py",
        "--vendor", "chatgpt",
        "--input", f"chatgpt={empty_dir}",
    ])

    with pytest.raises(SystemExit) as exc_info:
        run.main()

    assert exc_info.value.code == 1


def test_malformed_top_level_json_exits_2(tmp_path, patched_config_path, monkeypatch):
    bad_dir = tmp_path / "bad_chatgpt"
    bad_dir.mkdir()
    # 최상위가 list가 아닌 conversations.json — _load_conversations가 parse_errors로 집계.
    (bad_dir / "conversations.json").write_text(
        json.dumps({"not": "a list"}), encoding="utf-8"
    )

    monkeypatch.setattr("sys.argv", [
        "run.py",
        "--vendor", "chatgpt",
        "--input", f"chatgpt={bad_dir}",
        "--output-dir", str(tmp_path / "result"),
    ])

    with pytest.raises(SystemExit) as exc_info:
        run.main()

    assert exc_info.value.code == 2
