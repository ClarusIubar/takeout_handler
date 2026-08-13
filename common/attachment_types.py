"""첨부파일 확장자별 분류 — 두 벤더가 완전히 동일한 기준을 쓴다. Obsidian 네이티브
임베드 가능 여부는 어느 벤더에서 왔는지가 아니라 파일 형식 자체의 성질이므로,
따로 정의를 두 벤더 파일에 각각 복붙할 이유가 없다."""

IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}
AUDIO_EXTS = {'.wav'}
PDF_EXTS = {'.pdf'}
EMBED_EXTS = IMAGE_EXTS | AUDIO_EXTS | PDF_EXTS  # 이미지+음성+PDF 전부 Obsidian 네이티브 임베드
