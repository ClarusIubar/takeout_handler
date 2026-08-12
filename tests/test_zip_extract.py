import zipfile

from common.zip_extract import extract_all_zips


def test_extract_all_zips_flat(tmp_path):
    zpath = tmp_path / "export.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("conversations.json", "[]")

    count = extract_all_zips(tmp_path)

    assert count == 1
    assert (tmp_path / "conversations.json").exists()
    assert zpath.exists()  # 원본 zip은 지우지 않는다


def test_extract_all_zips_preserves_internal_nesting(tmp_path):
    # Google Takeout은 zip 내부가 Takeout/<서비스명>/... 처럼 한 겹 이상 감싸져 있다.
    zpath = tmp_path / "takeout-001.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("Takeout/Gemini 앱/내활동.html", "<html></html>")

    extract_all_zips(tmp_path)

    assert (tmp_path / "Takeout" / "Gemini 앱" / "내활동.html").exists()


def test_extract_all_zips_multiple_parts_merge(tmp_path):
    # Google Takeout처럼 대용량 export가 여러 파트로 쪼개진 경우: 파트마다 독립적인
    # zip이고, 같은 상위 폴더 구조를 공유하므로 순서 상관없이 합쳐져야 한다.
    z1 = tmp_path / "takeout-001.zip"
    z2 = tmp_path / "takeout-002.zip"
    with zipfile.ZipFile(z1, "w") as zf:
        zf.writestr("Takeout/a.txt", "a")
    with zipfile.ZipFile(z2, "w") as zf:
        zf.writestr("Takeout/b.txt", "b")

    count = extract_all_zips(tmp_path)

    assert count == 2
    assert (tmp_path / "Takeout" / "a.txt").read_text() == "a"
    assert (tmp_path / "Takeout" / "b.txt").read_text() == "b"


def test_extract_all_zips_no_zip_returns_zero(tmp_path):
    assert extract_all_zips(tmp_path) == 0


def test_extract_all_zips_missing_dir_returns_zero(tmp_path):
    assert extract_all_zips(tmp_path / "does-not-exist") == 0
