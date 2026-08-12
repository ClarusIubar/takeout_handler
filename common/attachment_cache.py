"""벤더별 첨부파일 리졸버가 공유하는 캐싱 + dry-run 복사 뼈대.

실제 파일을 어디서/어떻게 찾는지(원본 조회 전략)는 벤더마다 다르다
(ChatGPT는 .dat 블롭을 파일 ID로 찾고, Gemini는 href 파일명을 확장자
fallback까지 동원해 찾는다). 하지만 "찾은 결과를 캐싱하고, dry-run이면
실제 복사를 건너뛰고, 최종 성공/실패 건수를 집계하는" 부분은 동일하므로
여기 하나로 모은다. 벤더 서브클래스는 resolve()만 구현하면 된다.
"""

from pathlib import Path


class BaseAttachmentResolver:
    def __init__(self, attachments_dir: Path, dry_run: bool):
        self.attachments_dir = attachments_dir
        self.dry_run = dry_run
        self._cache = {}

    def stats(self):
        """(해석 성공 고유 파일 수, 실패 건수)를 반환한다.

        같은 실제 파일이 여러 캐시 키(원본 요청명/실제 basename 등)로 중복
        캐시될 수 있으므로, 성공 건은 rel_path 기준으로 중복 제거해서 센다.
        """
        resolved_paths = {v[0] for v in self._cache.values() if v is not None}
        missing = sum(1 for v in self._cache.values() if v is None)
        return len(resolved_paths), missing

    def _guarded_copy(self, dest_path: Path, copy_fn):
        """dry_run이 아니면 attachments_dir을 만들고, 대상이 아직 없을 때만
        copy_fn()을 실행한다. copy_fn 자체(바이트 write vs shutil.copy2 등)는
        벤더마다 다를 수 있어 호출자가 넘긴다."""
        if not self.dry_run:
            self.attachments_dir.mkdir(parents=True, exist_ok=True)
            if not dest_path.exists():
                copy_fn()
