# takeout_handler

ChatGPT / Gemini Takeout(데이터 내보내기)을 옵시디언 호환 마크다운으로 변환하는 통합
파이프라인. 각 벤더의 원본 export 형식이 완전히 달라서 파싱 로직은 벤더별로 분리돼
있지만, 코드펜스 안전장치·frontmatter 조립·callout 포맷 같은 공통 로직은 `common/`에
하나로 모아서 공유한다.

## 사용법

1. 각 벤더의 Takeout 압축을 풀어서 아래 위치에 그대로 넣는다.

   ```
   data/
   ├── chatgpt/   # ChatGPT Takeout 압축 해제 내용 그대로
   │              # (conversations.json 또는 conversations-*.json, file_*.dat,
   │              #  conversation_asset_file_names.json 등)
   └── gemini/    # Gemini Takeout 압축 해제 내용 그대로
                  # ("내 활동.html" + 참조된 첨부 미디어 파일들)
   ```

2. 실행한다.

   ```bash
   python run.py
   ```

   `data/` 아래 존재가 감지되는 벤더만 자동으로 골라 실행한다. 특정 벤더만 실행하려면
   `--vendor chatgpt` 또는 `--vendor gemini`를 지정한다. `--dry-run`을 붙이면 실제
   파일을 만들지 않고 파싱 결과(세션 수, 스킵 수, 첨부파일 해석 성공/실패 수)만 콘솔에
   출력한다.

3. 결과는 `result/<vendor>/*.md` (+ `result/<vendor>/Attachments/`)에 생성된다. 검토
   후 옵시디언 vault로 옮겨서 쓰면 된다.

## 출력 형식

세션(대화) 1개당 마크다운 노트 1개. frontmatter에 `title`/`session_id`/`url`/`date`/
`turns_count`/`tags`를 담고, 본문은 `> [!question]- User (...)` / `> [!tip]- <Vendor>
(...)` 콜아웃으로 turn을 나열한다. 이미지·파일 첨부는 `Attachments/`로 복사되고
가능하면 `![[...]]`로 임베드된다.

## 요구사항

표준 라이브러리만 사용한다 (Python 3.10+). 외부 패키지 설치 불필요.

## 구조

```
common/            # 두 벤더가 공유하는 마크다운 안전장치 / 텍스트 유틸 / frontmatter 조립
vendors/
├── chatgpt.py      # conversations*.json 트리 파싱 + .dat 첨부파일 복원
└── gemini.py       # "내 활동.html" 블록 파싱 + 로컬 첨부파일 매칭
run.py              # CLI: 벤더 자동 감지 + 실행
```
