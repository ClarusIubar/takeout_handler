"""프로젝트 설정 파일(config.json) 로더.

세 가지 경로를 설정할 수 있다: 벤더별 takeout 원본 위치, 마크다운 변환 결과 위치,
실제 옵시디언 vault 위치. 우선순위는 항상 CLI 플래그 > config.json > 내장 기본값이다
(run.py에서 실제로 이 우선순위를 적용한다 — 이 모듈은 config.json을 읽어오는 것만 담당).

config.json이 없으면 기본값으로 새로 만들어서, 사용자가 어떤 키를 고치면 되는지
바로 알 수 있게 한다. 개인 vault 절대경로가 들어가는 파일이라 .gitignore 대상이다
(config.example.json이 구조를 보여주는 커밋용 플레이스홀더).
"""

import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"

DEFAULTS = {
    # {"chatgpt": "C:/.../export.zip", ...} - 비어있으면 벤더별로 data/<vendor>/ 사용
    "takeout_paths": {},
    "markdown_output_dir": "result",
    # 미설정(None)이면 --publish 실행 시 안내만 하고 아무 데도 안 씀
    "obsidian_vault_dir": None,
    "vault_subdirs": {"chatgpt": "ChatGPT", "gemini": "Gemini", "claude": "Claude"},
}


def load_config(path=None):
    """config.json이 없으면 기본값으로 새로 만들고 안내 메시지를 출력한 뒤 기본값을
    반환한다. 있으면 읽어서 기본값과 병합해서 반환한다 — 나중에 새 키가 추가돼도
    기존 config.json에 그 키가 없으면 기본값으로 채워지므로 마이그레이션이 필요 없다.
    파일이 손상돼 파싱이 안 되면 경고를 찍고 기본값으로 폴백한다(기존 파일은 안 건드림
    — 사용자가 직접 고칠 수 있게 그대로 둔다).

    path: 테스트에서 실제 프로젝트의 config.json 대신 임시 경로를 주입할 수 있게 하는
    파라미터. 생략하면 실제 프로젝트 루트의 config.json(CONFIG_PATH)을 쓴다."""
    path = path or CONFIG_PATH

    if not path.exists():
        path.write_text(
            json.dumps(DEFAULTS, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"[config] {path} 이(가) 없어서 기본값으로 새로 만들었습니다. "
              "필요하면 직접 열어서 고치세요.")
        return dict(DEFAULTS)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[config] {path} 파싱 실패({exc}) — 이번 실행은 기본값을 씁니다.")
        return dict(DEFAULTS)

    if not isinstance(data, dict):
        print(f"[config] {path}의 최상위가 객체가 아닙니다 — 이번 실행은 기본값을 씁니다.")
        return dict(DEFAULTS)

    merged = dict(DEFAULTS)
    merged.update(data)
    return merged
