import json

from vendors.chatgpt import (
    _active_branch_nodes,
    _choose_fallback_leaf,
    _find_conversation_candidates,
    _find_conversations_dir,
    _load_conversations,
    _sniff_ext,
    detect,
)


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


def test_find_conversation_candidates_ignores_macosx_junk(tmp_path):
    # macOS에서 압축/전송된 zip에는 흔히 __MACOSX/ 리소스 포크 사본이 같이 들어있고,
    # 알파벳순 정렬에서 정상 폴더보다 앞에 오는 경우가 많아 잘못 선택될 위험이 있다.
    real = tmp_path / "real-export"
    real.mkdir()
    (real / "conversations.json").write_text("[]", encoding="utf-8")
    junk = tmp_path / "__MACOSX" / "real-export"
    junk.mkdir(parents=True)
    (junk / "conversations.json").write_text("[]", encoding="utf-8")

    candidates = _find_conversation_candidates(tmp_path)

    assert candidates == [real]


def test_find_conversation_candidates_reports_genuine_ambiguity(tmp_path):
    # __MACOSX가 아닌, 진짜 서로 다른 두 폴더에 conversations.json이 있으면(재실행
    # 잔여물 등) 둘 다 후보로 나와야 한다 — 조용히 하나만 고르면 안 됨.
    a = tmp_path / "attempt-1"
    b = tmp_path / "attempt-2"
    a.mkdir()
    b.mkdir()
    (a / "conversations.json").write_text("[]", encoding="utf-8")
    (b / "conversations.json").write_text("[]", encoding="utf-8")

    candidates = _find_conversation_candidates(tmp_path)

    assert set(candidates) == {a, b}


def test_load_conversations_non_list_top_level_counts_as_error(tmp_path, capsys):
    (tmp_path / "conversations.json").write_text('{"not": "a list"}', encoding="utf-8")

    conversations, errors = _load_conversations(tmp_path)

    assert conversations == []
    assert errors == 1
    assert "list가 아니라" in capsys.readouterr().out


def test_load_conversations_duplicate_id_is_logged(tmp_path, capsys):
    conv = {"id": "dup-id", "title": "t"}
    (tmp_path / "conversations-a.json").write_text(json.dumps([conv]), encoding="utf-8")
    (tmp_path / "conversations-b.json").write_text(json.dumps([conv]), encoding="utf-8")

    conversations, errors = _load_conversations(tmp_path)

    assert len(conversations) == 1  # 중복 제거는 여전히 동작
    assert errors == 0  # 파싱 실패는 아니므로 parse_errors로는 안 잡음
    assert "중복 conversation_id" in capsys.readouterr().out


def test_sniff_ext_recognizes_wav_and_mp4(tmp_path):
    wav_path = tmp_path / "a.dat"
    wav_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
    assert _sniff_ext(wav_path) == ".wav"

    mp4_path = tmp_path / "b.dat"
    mp4_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    assert _sniff_ext(mp4_path) == ".mp4"


def test_sniff_ext_still_distinguishes_webp_from_wav(tmp_path):
    # RIFF 헤더는 WAV/WEBP가 공유하므로 오프셋 8~12의 실제 태그로 구분해야 한다.
    webp_path = tmp_path / "c.dat"
    webp_path.write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8 ")
    assert _sniff_ext(webp_path) == ".webp"
