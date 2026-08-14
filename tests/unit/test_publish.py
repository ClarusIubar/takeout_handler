from common.publish import publish_vendor


def _write_note(dir_path, name, content_hash, body="본문"):
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / name).write_text(
        f"---\ncontent_hash: {content_hash}\n---\n{body}", encoding="utf-8", newline=""
    )


def test_publish_vendor_creates_new_notes(tmp_path):
    result_dir = tmp_path / "result"
    vault_dir = tmp_path / "vault"
    _write_note(result_dir, "a.md", "hash-a")
    _write_note(result_dir, "b.md", "hash-b")

    stats = publish_vendor(result_dir, vault_dir, dry_run=False)

    assert stats == {"created": 2, "updated": 0, "unchanged": 0, "attachments_copied": 0}
    assert (vault_dir / "a.md").read_text(encoding="utf-8") == (result_dir / "a.md").read_text(encoding="utf-8")


def test_publish_vendor_skips_unchanged_notes(tmp_path):
    result_dir = tmp_path / "result"
    vault_dir = tmp_path / "vault"
    _write_note(result_dir, "a.md", "hash-a")
    publish_vendor(result_dir, vault_dir, dry_run=False)

    # vault 쪽을 사용자가 손댔다고 가정 (해시는 그대로, 본문만 다르게)
    (vault_dir / "a.md").write_text("---\ncontent_hash: hash-a\n---\n손으로 고친 내용", encoding="utf-8")

    stats = publish_vendor(result_dir, vault_dir, dry_run=False)

    assert stats["unchanged"] == 1
    assert stats["created"] == 0
    assert stats["updated"] == 0
    assert "손으로 고친 내용" in (vault_dir / "a.md").read_text(encoding="utf-8")  # 안 건드림


def test_publish_vendor_updates_when_source_changed(tmp_path):
    result_dir = tmp_path / "result"
    vault_dir = tmp_path / "vault"
    _write_note(result_dir, "a.md", "hash-old")
    publish_vendor(result_dir, vault_dir, dry_run=False)

    _write_note(result_dir, "a.md", "hash-new", body="새 내용")
    stats = publish_vendor(result_dir, vault_dir, dry_run=False)

    assert stats == {"created": 0, "updated": 1, "unchanged": 0, "attachments_copied": 0}
    assert "새 내용" in (vault_dir / "a.md").read_text(encoding="utf-8")


def test_publish_vendor_copies_missing_attachments_only(tmp_path):
    result_dir = tmp_path / "result"
    vault_dir = tmp_path / "vault"
    _write_note(result_dir, "a.md", "hash-a")
    attachments = result_dir / "Attachments"
    attachments.mkdir()
    (attachments / "img.png").write_bytes(b"image-bytes")

    stats = publish_vendor(result_dir, vault_dir, dry_run=False)

    assert stats["attachments_copied"] == 1
    assert (vault_dir / "Attachments" / "img.png").read_bytes() == b"image-bytes"

    # 재실행하면 이미 있으니 다시 복사 안 함
    stats2 = publish_vendor(result_dir, vault_dir, dry_run=False)
    assert stats2["attachments_copied"] == 0


def test_publish_vendor_dry_run_does_not_write(tmp_path):
    result_dir = tmp_path / "result"
    vault_dir = tmp_path / "vault"
    _write_note(result_dir, "a.md", "hash-a")

    stats = publish_vendor(result_dir, vault_dir, dry_run=True)

    assert stats["created"] == 1
    assert not vault_dir.exists()


def test_publish_vendor_missing_result_dir_returns_zero_stats(tmp_path):
    stats = publish_vendor(tmp_path / "does-not-exist", tmp_path / "vault", dry_run=False)
    assert stats == {"created": 0, "updated": 0, "unchanged": 0, "attachments_copied": 0}
