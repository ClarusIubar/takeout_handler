from vendors.chatgpt import _active_branch_nodes, _choose_fallback_leaf, _find_conversations_dir, detect


def _mapping():
    """root -> a -> {b, c} (b/c는 같은 질문에 대한 재생성 분기; c가 더 최신)."""
    return {
        "root": {"id": "root", "message": None, "parent": None, "children": ["a"]},
        "a": {"id": "a", "message": {"create_time": 1}, "parent": "root", "children": ["b", "c"]},
        "b": {"id": "b", "message": {"create_time": 2}, "parent": "a", "children": []},
        "c": {"id": "c", "message": {"create_time": 3}, "parent": "a", "children": []},
    }


def test_active_branch_nodes_follows_current_node_to_root():
    conv = {"mapping": _mapping(), "current_node": "c"}
    ids = [n["id"] for n in _active_branch_nodes(conv)]
    # "b"는 재생성되어 버려진 분기이므로 활성 브랜치에서 제외돼야 한다.
    assert ids == ["root", "a", "c"]


def test_active_branch_nodes_falls_back_to_latest_leaf_when_current_node_missing():
    conv = {"mapping": _mapping(), "current_node": "does-not-exist"}
    ids = [n["id"] for n in _active_branch_nodes(conv)]
    assert ids[-1] == "c"


def test_active_branch_nodes_empty_mapping_returns_empty():
    assert _active_branch_nodes({"mapping": {}, "current_node": None}) == []


def test_choose_fallback_leaf_picks_max_timestamp_leaf():
    assert _choose_fallback_leaf(_mapping()) == "c"


def test_choose_fallback_leaf_empty_mapping_returns_none():
    assert _choose_fallback_leaf({}) is None


def test_find_conversations_dir_flat(tmp_path):
    (tmp_path / "conversations.json").write_text("[]", encoding="utf-8")
    assert _find_conversations_dir(tmp_path) == tmp_path
    assert detect(tmp_path) is True


def test_find_conversations_dir_handles_one_level_of_nesting(tmp_path):
    # 압축 해제 도구에 따라 zip 내용이 폴더 하나로 한 번 더 감싸질 수 있다.
    nested = tmp_path / "chatgpt-export-2024"
    nested.mkdir()
    (nested / "conversations.json").write_text("[]", encoding="utf-8")
    assert _find_conversations_dir(tmp_path) == nested
    assert detect(tmp_path) is True


def test_find_conversations_dir_missing_returns_none(tmp_path):
    assert _find_conversations_dir(tmp_path) is None
    assert detect(tmp_path) is False
