from common.text import clean_text, first_sentence, format_callout, sanitize_filename, yaml_quote


def test_first_sentence_cuts_at_period():
    # 종결부호 자체는 결과에 포함되지 않는다 (자르는 지점 = 매치된 부호의 시작 인덱스).
    assert first_sentence("첫 문장입니다. 두번째 문장.") == "첫 문장입니다"


def test_first_sentence_ignores_period_inside_url():
    text = "다음 링크를 참고: https://example.com/a.b.c 그리고 계속 설명."
    assert first_sentence(text) == "다음 링크를 참고: https://example.com/a.b.c 그리고 계속 설명"


def test_first_sentence_empty_input():
    assert first_sentence("") == "(빈 프롬프트)"
    assert first_sentence(None) == "(빈 프롬프트)"


def test_first_sentence_truncates_long_single_sentence():
    text = "가" * 300
    assert len(first_sentence(text)) == 150


def test_yaml_quote_escapes_backslash_and_quote():
    assert yaml_quote('say "hi"\\end') == 'say \\"hi\\"\\\\end'


def test_sanitize_filename_replaces_illegal_chars():
    # 연속된 금지 문자는 각각 개별 '_'로 치환된다 (합쳐지지 않음).
    assert sanitize_filename('a:b/c*d?"e<f>g|h') == "a_b_c_d__e_f_g_h"


def test_sanitize_filename_strips_control_chars():
    assert sanitize_filename("a\x00b\x1fc") == "a_b_c"


def test_sanitize_filename_falls_back_when_empty():
    assert sanitize_filename("   ", fallback="unknown") == "unknown"


def test_clean_text_collapses_blank_lines():
    assert clean_text("a\n\n\n\nb") == "a\n\nb"


def test_format_callout_prefixes_each_line():
    assert format_callout("line1\nline2") == "> line1\n> line2"


def test_format_callout_empty_text():
    assert format_callout("   ") == "> (내용 없음)"
