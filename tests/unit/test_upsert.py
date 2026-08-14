from common.upsert import write_upsert


def test_write_upsert_creates_new_file(tmp_path):
    fp = tmp_path / "a.md"
    action = write_upsert(fp, "---\ncontent_hash: abc\n---\nbody", "abc", dry_run=False)
    assert action == "created"
    assert fp.read_text(encoding="utf-8") == "---\ncontent_hash: abc\n---\nbody"


def test_write_upsert_skips_when_hash_matches_existing(tmp_path):
    fp = tmp_path / "a.md"
    # 사용자가 옵시디언에서 직접 손댄 상황을 흉내: 저장된 해시는 같지만
    # 실제 저장된 본문은 새로 렌더링한 내용과 다르게 만들어둔다.
    fp.write_text("---\ncontent_hash: abc\n---\n손으로 고친 내용", encoding="utf-8")

    action = write_upsert(fp, "---\ncontent_hash: abc\n---\n새로 렌더링된 내용", "abc", dry_run=False)

    assert action == "unchanged"
    assert fp.read_text(encoding="utf-8") == "---\ncontent_hash: abc\n---\n손으로 고친 내용"  # 안 건드림


def test_write_upsert_updates_when_hash_differs(tmp_path):
    fp = tmp_path / "a.md"
    fp.write_text("---\ncontent_hash: old\n---\n예전 내용", encoding="utf-8")

    action = write_upsert(fp, "---\ncontent_hash: new\n---\n새 내용", "new", dry_run=False)

    assert action == "updated"
    assert fp.read_text(encoding="utf-8") == "---\ncontent_hash: new\n---\n새 내용"


def test_write_upsert_dry_run_does_not_write_but_still_classifies(tmp_path):
    fp = tmp_path / "a.md"
    action = write_upsert(fp, "content", "abc", dry_run=True)
    assert action == "created"
    assert not fp.exists()


def test_write_upsert_dry_run_detects_unchanged_without_writing(tmp_path):
    fp = tmp_path / "a.md"
    fp.write_text("---\ncontent_hash: abc\n---\nbody", encoding="utf-8")

    action = write_upsert(fp, "---\ncontent_hash: abc\n---\nbody", "abc", dry_run=True)

    assert action == "unchanged"


def test_write_upsert_missing_hash_field_in_existing_file_treated_as_update(tmp_path):
    # 이번 기능 적용 전에 만들어진 기존 .md는 content_hash 필드가 없다 — 그런 파일은
    # "변경없음"으로 잘못 판단하지 않고 갱신 대상으로 잡아서 필드를 새로 채워야 한다.
    fp = tmp_path / "a.md"
    fp.write_text("---\ntitle: 예전 형식\n---\n본문", encoding="utf-8")

    action = write_upsert(fp, "---\ncontent_hash: new\n---\n본문", "new", dry_run=False)

    assert action == "updated"


def test_write_upsert_corrupted_existing_file_treated_as_update(tmp_path):
    fp = tmp_path / "a.md"
    fp.write_text("frontmatter가 아예 없는 이상한 파일", encoding="utf-8")

    action = write_upsert(fp, "새 내용", "abc", dry_run=False)

    assert action == "updated"
    assert fp.read_text(encoding="utf-8") == "새 내용"
