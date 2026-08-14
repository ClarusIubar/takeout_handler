# issue #11: 첨부 미디어는 data_dir 최상위가 아니라 내활동.html과 같은 폴더(중첩된
# Takeout/<서비스명>/)에 나란히 있다. convert()가 첨부파일 리졸버에 최상위 data_dir을
# 넘기면(예전 버그) 실제로 존재하는 첨부파일도 전부 "누락"으로 잘못 처리된다.
# html_file.parent를 기준으로 찾는지, convert() 전체를 통해 재현한다 (리졸버 단위
# 테스트는 tests/unit/test_gemini_vendor.py에 이미 있음 — 여기는 벤더 진입점 레벨에서
# 그 배선이 실제로 맞는지 고정한다).
import pytest

from vendors.gemini import convert, detect

pytestmark = pytest.mark.regression


def _gemini_export_with_image_attachment(dir_path, session_id="session-abc123",
                                          image_filename="photo.png"):
    nested = dir_path / "Takeout" / "Gemini 앱"
    nested.mkdir(parents=True, exist_ok=True)
    # 첨부파일은 html과 "같은" 폴더에 둔다 — data_dir 최상위(dir_path)에는 두지 않는다.
    (nested / image_filename).write_bytes(b"fake-image-bytes")

    html = (
        '<div class="outer-cell mdl-cell mdl-cell--12-col mdl-shadow--2dp">'
        f'<a href="https://gemini.google.com/app/{session_id}">caption</a>'
        '<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">'
        "질문입니다항목을 검색함<br>"
        "2024. 3. 5. 오후 3:20:10 KST<br>"
        f'<img src="{image_filename}">'
        "답변입니다"
        "</div></div>"
    )
    (nested / "내활동.html").write_text(html, encoding="utf-8")
    return nested


def test_attachment_found_via_html_parent_not_top_level_data_dir(tmp_path):
    data_dir = tmp_path / "data"
    _gemini_export_with_image_attachment(data_dir)

    assert detect(data_dir) is True
    # 첨부파일이 data_dir 최상위에는 없다는 걸 명시적으로 확인 — 예전 버그처럼
    # 최상위 기준으로 찾으면 반드시 실패하는 조건.
    assert not (data_dir / "photo.png").exists()

    result_dir = tmp_path / "result"
    stats = convert(data_dir, result_dir, dry_run=False)

    assert stats.sessions_found == 1
    assert stats.attachments_ok == 1
    assert stats.attachments_missing == 0
    assert (result_dir / "Attachments" / "photo.png").read_bytes() == b"fake-image-bytes"
