"""벤더 모듈이 따라야 하는 공통 인터페이스.

각 vendors/<name>.py 모듈은 다음을 제공해야 한다:
- VENDOR_TAG: str            frontmatter tags에 들어갈 짧은 식별자 (예: "chatgpt", "gemini")
- VENDOR_LABEL: str          callout 헤더에 쓰일 표시 이름 (예: "ChatGPT", "Gemini")
- detect(data_dir) -> bool   해당 벤더의 raw takeout 데이터가 data_dir 안에 있는지 판별
- convert(data_dir, result_dir, dry_run) -> ConvertStats   실제 변환 수행

이 계약은 두 층위로 강제된다:
- VendorModule(Protocol) — mypy/pyright 같은 정적 타입체커가 run.py의 호출부
  (`module.convert(data_dir, ...)` 등)에서 시그니처 불일치를 잡을 수 있게 함.
- validate() — REQUIRED_ATTRS 존재 여부를 런타임에 확인. docstring/Protocol뿐인
  계약은 새 벤더 모듈이 속성 하나를 빠뜨려도 run.py 실행 중간에서야 알 수 없는
  AttributeError로 터지므로, 등록 시점(discover())에 미리 걸러낸다.

discover()가 vendors/ 디렉터리를 스캔해서 벤더 모듈을 자동으로 찾으므로, 새 벤더를
추가할 때는 vendors/<name>.py 파일 하나만 놓으면 되고 run.py를 고칠 필요가 없다.
"""

import importlib
import pkgutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

REQUIRED_ATTRS = ("VENDOR_TAG", "VENDOR_LABEL", "detect", "convert")
_VENDORS_DIR = Path(__file__).resolve().parent


@runtime_checkable
class VendorModule(Protocol):
    """벤더 모듈의 구조적 타입. detect/convert는 클래스 메서드가 아니라 모듈 최상위
    함수이므로 (self 없이) Callable 속성으로 선언한다."""

    VENDOR_TAG: str
    VENDOR_LABEL: str
    detect: Callable[[Path], bool]
    convert: Callable[[Path, Path, bool], "ConvertStats"]


def validate(name, module):
    """module이 벤더 인터페이스를 다 구현했는지 확인한다. 빠진 게 있으면
    등록 시점에 바로 알 수 있도록 명확한 메시지로 예외를 던진다 (isinstance()의
    bool 하나짜리 결과보다 어떤 속성이 빠졌는지 알려주는 쪽이 디버깅에 낫다)."""
    missing = [attr for attr in REQUIRED_ATTRS if not hasattr(module, attr)]
    if missing:
        raise TypeError(
            f"vendor module '{name}' is missing required attribute(s): {', '.join(missing)}"
        )


def discover():
    """vendors/ 디렉터리 아래 모든 서브모듈(base.py 자신은 제외)을 찾아서
    이름 -> 모듈 dict로 반환한다. 각 모듈은 validate()로 인터페이스를 검증한다."""
    discovered = {}
    for modinfo in pkgutil.iter_modules([str(_VENDORS_DIR)]):
        name = modinfo.name
        if name == "base":
            continue
        module = importlib.import_module(f"vendors.{name}")
        validate(name, module)
        discovered[name] = module
    return discovered


@dataclass
class ConvertStats:
    vendor_tag: str
    sessions_found: int = 0
    files_created: int = 0
    files_updated: int = 0
    files_unchanged: int = 0
    empty_skipped: int = 0
    attachments_ok: int = 0
    attachments_missing: int = 0
    parse_errors: int = 0
