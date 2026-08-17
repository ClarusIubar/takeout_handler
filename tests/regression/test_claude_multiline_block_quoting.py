# 실제 사용자 zip으로 --dry-run 검증하다 발견한 버그: tool_call/tool_result/thinking
# 블록의 값이 여러 줄이면(예: github API 응답처럼 줄바꿈이 섞인 tool output), 렌더러가
# 첫 줄에만 "> "를 직접 붙이고 나머지 줄은 outer format_callout()이 씌우는 한 겹짜리
# "> "에만 의존했다. 그 결과 같은 블록 안에서 첫 줄은 "> > "(중첩 인용)인데 이어지는
# 줄은 "> "(한 겹)로 인용 깊이가 들쭉날쭉해졌다 — 렌더링이 깨지진 않지만 Obsidian에서
# 인용 블록 경계가 뒤섞여 보인다. _quote_lines()로 블록 내부에서부터 매 줄에 "> "를
# 붙이도록 고쳤다 — 그 배선이 실제로 맞는지 convert() 전체를 통해 고정한다.
import pytest

from vendors.claude import convert

pytestmark = pytest.mark.regression


def _standalone_export_with_multiline_tool_result(dir_path):
    dir_path.mkdir(parents=True, exist_ok=True)
    conv = {
        "uuid": "conv-multiline",
        "name": "Multiline tool output",
        "created_at": "2026-06-01T12:00:00.000000+00:00",
        "chat_messages": [
            {
                "uuid": "m-1", "sender": "human",
                "created_at": "2026-06-01T12:00:00.000000+00:00",
                "content": [{"type": "text", "text": "list repos"}],
            },
            {
                "uuid": "m-2", "sender": "assistant",
                "created_at": "2026-06-01T12:00:01.000000+00:00",
                "content": [
                    {"type": "tool_use", "name": "list_repos", "input": {}},
                    {
                        "type": "tool_result",
                        "content": [{"type": "text", "text": "repo-a\n\nrepo-b\nrepo-c"}],
                    },
                ],
            },
        ],
    }
    import json
    (dir_path / "conversations.json").write_text(
        json.dumps([conv], ensure_ascii=False), encoding="utf-8"
    )
    return dir_path


def test_multiline_tool_result_keeps_consistent_quote_depth(tmp_path):
    data_dir = tmp_path / "data"
    _standalone_export_with_multiline_tool_result(data_dir)
    result_dir = tmp_path / "result"

    convert(data_dir, result_dir, dry_run=False)

    text = (result_dir / "conv-multiline.md").read_text(encoding="utf-8")
    lines = text.split("\n")
    idx = next(i for i, l in enumerate(lines) if "Tool result" in l)

    # "Tool result" 헤더 줄과 그 뒤를 잇는 tool output의 각 줄(빈 줄 포함)이 전부
    # 같은 인용 깊이("> > ")를 유지해야 한다 — 예전 버그는 두 번째 줄부터 "> "
    # 한 겹으로 떨어졌다.
    assert lines[idx].startswith("> > ")
    assert lines[idx + 1] == "> > repo-a"
    assert lines[idx + 2] == "> > "
    assert lines[idx + 3] == "> > repo-b"
    assert lines[idx + 4] == "> > repo-c"
