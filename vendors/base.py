"""벤더 모듈이 따라야 하는 공통 인터페이스.

각 vendors/<name>.py 모듈은 다음을 제공해야 한다:
- VENDOR_TAG: str            frontmatter tags에 들어갈 짧은 식별자 (예: "chatgpt", "gemini")
- VENDOR_LABEL: str          callout 헤더에 쓰일 표시 이름 (예: "ChatGPT", "Gemini")
- detect(data_dir) -> bool   해당 벤더의 raw takeout 데이터가 data_dir 안에 있는지 판별
- convert(data_dir, result_dir, dry_run) -> ConvertStats   실제 변환 수행

REQUIRED_ATTRS로 이 계약을 런타임에 검증한다 (validate() 참고) — docstring뿐인
계약은 새 벤더 모듈이 속성 하나를 빠뜨려도 run.py 실행 중간에서야 알 수 없는
AttributeError로 터지므로, 등록 시점에 미리 걸러낸다.
"""

from dataclasses import dataclass

REQUIRED_ATTRS = ("VENDOR_TAG", "VENDOR_LABEL", "detect", "convert")


def validate(name, module):
    """module이 벤더 인터페이스를 다 구현했는지 확인한다. 빠진 게 있으면
    등록 시점에 바로 알 수 있도록 명확한 메시지로 예외를 던진다."""
    missing = [attr for attr in REQUIRED_ATTRS if not hasattr(module, attr)]
    if missing:
        raise TypeError(
            f"vendor module '{name}' is missing required attribute(s): {', '.join(missing)}"
        )


@dataclass
class ConvertStats:
    vendor_tag: str
    sessions_found: int = 0
    files_written: int = 0
    empty_skipped: int = 0
    attachments_ok: int = 0
    attachments_missing: int = 0
    parse_errors: int = 0
