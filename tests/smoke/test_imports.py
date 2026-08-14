# 가장 얕고 빠른 확인: 전체 모듈이 문법 오류/깨진 import 없이 임포트되는지.
# 이것만으로도 "배포 직전 실수로 깨진 import를 커밋했다" 같은 사고를 즉시 잡는다.
import importlib

import pytest

pytestmark = pytest.mark.smoke


def test_all_modules_import_without_error():
    for name in [
        "run",
        "common.attachment_cache",
        "common.attachment_types",
        "common.config",
        "common.fs_discovery",
        "common.markdown_safety",
        "common.publish",
        "common.session_markdown",
        "common.text",
        "common.upsert",
        "common.zip_extract",
        "vendors.base",
        "vendors.chatgpt",
        "vendors.gemini",
    ]:
        importlib.import_module(name)
