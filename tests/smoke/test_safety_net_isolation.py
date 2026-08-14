# _isolate_real_project_paths(tests/conftest.py) autouse fixture가 실제로 안전망
# 역할을 하는지 증명하는 테스트. 이 테스트는 patched_config_path도 --input도 의도적으로
# 안 쓴다 — "새 테스트를 짜다가 이 둘을 깜빡했다"는 상황을 그대로 재현한다. autouse
# fixture가 없다면 이 테스트는 실제 프로젝트의 config.json을 건드리거나 실제
# data/<vendor>/(개인 데이터)를 읽으려 시도했을 것이다.
import pytest

import run

pytestmark = pytest.mark.smoke


def test_forgetting_input_and_config_patch_still_stays_isolated(monkeypatch):
    monkeypatch.setattr("sys.argv", ["run.py", "--vendor", "chatgpt"])

    with pytest.raises(SystemExit) as exc_info:
        run.main()

    # DATA_DIR이 autouse fixture 덕분에 존재하지 않는 tmp 경로로 이미 돌려져 있으므로,
    # 실제 data/chatgpt/를 읽지 않고 "실행된 벤더 없음"으로 안전하게 끝난다.
    assert exc_info.value.code == 1
