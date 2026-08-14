# issue #13: __MACOSX/ 리소스 포크 사본이 알파벳순으로 정상 폴더보다 먼저 오는 경우가
# 많아, 필터링 없이 sorted()[0]을 그대로 고르면 conversations.json이 있어도 엉뚱한
# 쓰레기 사본을 조용히 선택할 수 있었다. detect()/convert() 전체를 통해 재현한다
# (헬퍼 함수 단위 필터링 자체는 tests/unit/test_fs_discovery.py, test_chatgpt_vendor.py에
# 이미 있음 — 여기는 "실제로 그 버그가 터지던 경로"를 벤더 진입점 레벨에서 고정한다).
import json

import pytest

from vendors.chatgpt import convert, detect

pytestmark = pytest.mark.regression


def test_macosx_copy_never_wins_over_real_export(tmp_path, minimal_chatgpt_export):
    data_dir = tmp_path / "data"

    # "__MACOSX"는 알파벳순으로 "real_export"보다 앞에 온다 — 필터링이 없으면 이쪽이
    # 선택되던 게 원래 버그.
    minimal_chatgpt_export(data_dir / "real_export", conversation_id="real-conv")

    junk_dir = data_dir / "__MACOSX" / "real_export"
    junk_dir.mkdir(parents=True)
    (junk_dir / "conversations.json").write_text(
        json.dumps([{"id": "junk-should-not-be-used", "mapping": {}}]), encoding="utf-8"
    )

    assert detect(data_dir) is True

    result_dir = tmp_path / "result"
    stats = convert(data_dir, result_dir, dry_run=False)

    md_files = sorted(result_dir.glob("*.md"))
    assert [f.stem for f in md_files] == ["real-conv"]
    assert stats.sessions_found == 1
