from pathlib import Path

from common.attachment_cache import BaseAttachmentResolver


def test_stats_dedups_by_rel_path_across_multiple_cache_keys(tmp_path):
    resolver = BaseAttachmentResolver(attachments_dir=tmp_path, dry_run=True)
    # Gemini류 벤더는 원본 요청 파일명과 실제로 찾은 basename, 두 키로
    # 같은 결과를 캐시한다 (확장자 fallback 매칭). rel_path 기준으로 1개로만 세야 한다.
    same_result = ("Attachments/foo.png", "foo.png", True)
    resolver._cache["foo.png"] = same_result
    resolver._cache["foo"] = same_result
    resolver._cache["missing.pdf"] = None

    ok, missing = resolver.stats()
    assert ok == 1
    assert missing == 1


def test_guarded_copy_skips_when_dry_run(tmp_path):
    resolver = BaseAttachmentResolver(attachments_dir=tmp_path / "Attachments", dry_run=True)
    calls = []
    resolver._guarded_copy(tmp_path / "Attachments" / "x.png", lambda: calls.append(1))
    assert calls == []
    assert not (tmp_path / "Attachments").exists()


def test_guarded_copy_runs_and_creates_dir_when_not_dry_run(tmp_path):
    resolver = BaseAttachmentResolver(attachments_dir=tmp_path / "Attachments", dry_run=False)
    dest = tmp_path / "Attachments" / "x.png"
    calls = []
    resolver._guarded_copy(dest, lambda: (dest.write_bytes(b"data"), calls.append(1)))
    assert calls == [1]
    assert dest.exists()


def test_guarded_copy_skips_if_dest_already_exists(tmp_path):
    resolver = BaseAttachmentResolver(attachments_dir=tmp_path / "Attachments", dry_run=False)
    dest = tmp_path / "Attachments" / "x.png"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"already there")
    calls = []
    resolver._guarded_copy(dest, lambda: calls.append(1))
    assert calls == []
