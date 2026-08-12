"""벤더 모듈이 따라야 하는 공통 인터페이스.

각 vendors/<name>.py 모듈은 다음을 제공해야 한다:
- VENDOR_TAG: str            frontmatter tags에 들어갈 짧은 식별자 (예: "chatgpt", "gemini")
- VENDOR_LABEL: str          callout 헤더에 쓰일 표시 이름 (예: "ChatGPT", "Gemini")
- detect(data_dir) -> bool   해당 벤더의 raw takeout 데이터가 data_dir 안에 있는지 판별
- convert(data_dir, result_dir, dry_run) -> ConvertStats   실제 변환 수행
"""

from dataclasses import dataclass, field


@dataclass
class ConvertStats:
    vendor_tag: str
    sessions_found: int = 0
    files_written: int = 0
    empty_skipped: int = 0
    attachments_ok: int = 0
    attachments_missing: int = 0
    notes: list = field(default_factory=list)
