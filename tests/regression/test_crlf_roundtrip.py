# issue #16: --publish의 read-then-rewrite 사이클에서 대화 원문에 이미 섞여 있던 \r\n이
# 기본 텍스트 모드 읽기/쓰기 때문에 사이클마다 \r가 하나씩 더 붙어 불어나던 버그.
# newline=''을 안 쓰면 재현되므로, 이 테스트가 통과하는 한 그 회귀는 못 돌아온다.
import pytest

from common.publish import publish_vendor
from common.upsert import write_upsert

pytestmark = pytest.mark.regression


def _write_note(dir_path, name, content_hash, body="본문"):
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / name).write_text(
        f"---\ncontent_hash: {content_hash}\n---\n{body}", encoding="utf-8", newline=""
    )


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


def test_publish_vendor_preserves_embedded_crlf_exactly(tmp_path):
    # 실측 회귀 케이스: 대화 원문에 이미 \r\n이 섞여 있으면(Windows 코드 붙여넣기 등),
    # result/에서 읽어서 vault/에 다시 쓰는 것만으로 바이트가 불어나면 안 된다.
    result_dir = tmp_path / "result"
    vault_dir = tmp_path / "vault"
    _write_note(result_dir, "a.md", "h1", body="code:\r\n  const x = 1;\r\n")

    publish_vendor(result_dir, vault_dir, dry_run=False)

    assert (vault_dir / "a.md").read_bytes() == (result_dir / "a.md").read_bytes()
