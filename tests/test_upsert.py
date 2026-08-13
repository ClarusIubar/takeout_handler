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


def test_write_upsert_preserves_embedded_crlf_exactly_across_read_write_cycles(tmp_path):
    # 대화 원문에 이미 \r\n이 섞여 있으면(Windows에서 작성된 코드를 붙여넣은 경우 등),
    # 기본 텍스트 모드로 읽고 다시 쓰면 매 사이클마다 \r가 하나씩 더 붙어서 내용이
    # 조금씩 불어난다 — write_upsert가 newline=''로 이걸 막는지 확인.
    fp = tmp_path / "a.md"
    tricky = "---\ncontent_hash: h1\n---\ncode:\r\n  const x = 1;\r\n"

    write_upsert(fp, tricky, "h1", dry_run=False)
    first_bytes = fp.read_bytes()

    # publish.py처럼 다시 읽어서 그대로 재기록하는 상황을 흉내: 해시가 바뀌어서
    # "updated"로 다시 써져도 바이트가 늘어나지 않아야 한다.
    reread = fp.read_text(encoding="utf-8", newline="")
    assert reread == tricky  # 읽기 자체도 원본 그대로여야 함
    write_upsert(fp, reread, "h2", dry_run=False)

    assert fp.read_bytes() == first_bytes
