from datetime import datetime

from vendors.gemini import _extract_gemini_session_id, _find_outer_cell_blocks, _parse_kst


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
