from datetime import datetime

from vendors.gemini import (
    _AttachmentResolver,
    _extract_gemini_session_id,
    _find_activity_html,
    _find_outer_cell_blocks,
    _parse_kst,
    detect,
)


def test_parse_kst_pm_hour_conversion():
    assert _parse_kst("2024. 3. 5. 오후 3:20:10 KST") == datetime(2024, 3, 5, 15, 20, 10)


def test_parse_kst_am_12_is_midnight():
    assert _parse_kst("2024. 3. 5. 오전 12:00:00 KST") == datetime(2024, 3, 5, 0, 0, 0)


def test_parse_kst_pm_12_stays_noon():
    assert _parse_kst("2024. 3. 5. 오후 12:00:00 KST") == datetime(2024, 3, 5, 12, 0, 0)


def test_parse_kst_no_match_returns_none():
    assert _parse_kst("이 문장에는 타임스탬프가 없습니다") is None


def test_extract_session_id_takes_last_match():
    # 본문 중 예시로 언급된 첫 링크가 아니라, caption 영역의 마지막 링크를 채택해야 한다.
    links = [
        "https://gemini.google.com/app/aaa111",
        "https://example.com/other",
        "https://gemini.google.com/app/bbb222",
    ]
    assert _extract_gemini_session_id(links) == "bbb222"


def test_extract_session_id_none_when_no_gemini_link():
    assert _extract_gemini_session_id(["https://example.com"]) is None


def test_find_outer_cell_blocks_splits_on_each_marker():
    content = (
        'prefix<div class="outer-cell x">A</div>'
        '<div class="outer-cell y">B</div>'
    )
    blocks = _find_outer_cell_blocks(content)
    assert len(blocks) == 2
    assert blocks[0].startswith('<div class="outer-cell x">')
    assert blocks[1].startswith('<div class="outer-cell y">')


def test_find_outer_cell_blocks_no_marker_returns_empty():
    assert _find_outer_cell_blocks("no markers here") == []


def test_find_activity_html_locates_file_nested_like_google_takeout(tmp_path):
    # 실제 Google Takeout zip은 data_dir 최상위가 아니라
    # Takeout/<서비스명>/내활동.html 처럼 한 겹 이상 감싸져 있다.
    nested = tmp_path / "Takeout" / "Gemini 앱"
    nested.mkdir(parents=True)
    html_path = nested / "내활동.html"
    html_path.write_text("<html></html>", encoding="utf-8")

    found = _find_activity_html(tmp_path)

    assert found == html_path
    assert detect(tmp_path) is True


def test_attachment_resolver_looks_up_files_relative_to_given_dir_not_repo_root(tmp_path):
    # 첨부 미디어는 html과 같은 폴더에 나란히 있다 (data_dir 최상위가 아니라).
    # 리졸버에 html이 실제로 들어있는 폴더를 넘기지 않으면 파일을 못 찾는다 — 이게
    # nested export를 그대로 넣었을 때 첨부파일이 전부 "누락"으로 나오던 버그였다.
    nested = tmp_path / "Takeout" / "Gemini 앱"
    nested.mkdir(parents=True)
    (nested / "photo.png").write_bytes(b"fake-image-bytes")

    attachments_dir = tmp_path / "out" / "Attachments"
    resolver = _AttachmentResolver(nested, attachments_dir, "내활동.html", dry_run=False)

    resolved = resolver.resolve("photo.png")

    assert resolved is not None
    rel_path, display_name, is_embeddable = resolved
    assert rel_path == "Attachments/photo.png"
    assert is_embeddable is True
    assert (attachments_dir / "photo.png").read_bytes() == b"fake-image-bytes"


def test_attachment_resolver_returns_none_when_given_wrong_base_dir(tmp_path):
    # 회귀 방지: data_dir 최상위(파일이 실제로 있는 곳이 아닌)를 리졸버에 넘기면
    # 존재하는 첨부파일도 못 찾아야 한다 — 고치기 전 버그를 정확히 재현.
    nested = tmp_path / "Takeout" / "Gemini 앱"
    nested.mkdir(parents=True)
    (nested / "photo.png").write_bytes(b"fake-image-bytes")

    attachments_dir = tmp_path / "out" / "Attachments"
    wrong_base_resolver = _AttachmentResolver(tmp_path, attachments_dir, "내활동.html", dry_run=False)

    assert wrong_base_resolver.resolve("photo.png") is None
