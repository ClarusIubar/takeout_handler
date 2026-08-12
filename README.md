# takeout_handler

ChatGPT / Gemini Takeout(데이터 내보내기)을 옵시디언 호환 마크다운으로 변환하는 통합
파이프라인. 각 벤더의 원본 export 형식이 완전히 달라서 파싱 로직은 벤더별로 분리돼
있지만, 코드펜스 안전장치·frontmatter 조립·callout 포맷 같은 공통 로직은 `common/`에
하나로 모아서 공유한다.

## 사용법

1. 벤더가 준 원본 zip을 **압축을 풀지 않고 그대로** 아래 위치에 넣는다 (이미 풀어서
   넣어도 동작함 — 아래 "실제 벤더 export가 어떻게 생겼는지" 참고).

   ```
   data/
   ├── chatgpt/   # ChatGPT의 Data export zip을 그대로, 또는 압축을 푼 내용
   └── gemini/    # Google Takeout zip을 그대로, 또는 압축을 푼 내용
   ```

   `run.py`가 각 벤더 폴더에서 필요한 파일을 못 찾으면 그 폴더 안의 `*.zip`을 자동으로
   그 자리에 풀어본 뒤 다시 찾는다 (`common/zip_extract.py`). Google Takeout처럼 여러
   파트 zip으로 쪼개져 있으면 전부 같은 폴더에 넣으면 된다 — 파트별로 순서 상관없이
   풀려서 자연스럽게 합쳐진다. 원본 zip 파일은 지우지 않는다.

   **실제 벤더 export가 어떻게 생겼는지** (압축 풀었을 때 기준):
   - **ChatGPT** ("설정 → 데이터 제어 → 내보내기"로 받는 zip): 보통 폴더로 안 감싸져
     있고 `conversations.json`, `chat.html`, `file_*.dat` 등이 압축 최상위에 바로
     나온다. 압축 해제 도구에 따라 폴더 하나로 한 번 더 감싸일 수도 있는데, 그 경우도
     재귀 탐색으로 찾으므로 상관없다.
   - **Gemini** (Google Takeout에서 "Gemini 앱"만 선택해서 받는 zip): 항상
     `Takeout/<서비스명>/` 처럼 한 겹 이상 감싸져 있고, 그 안에 `내 활동.html`과 첨부
     미디어 파일들이 나란히 들어있다. `Takeout/` 폴더째로 `data/gemini/`에 넣으면 된다
     (하위 폴더를 직접 뒤져서 꺼낼 필요 없음).

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

### 종료 코드

- `0`: 정상 완료.
- `1`: 실행된 벤더가 하나도 없음 (`data/<vendor>/`에 아무것도 없음).
- `2`: 일부 벤더가 부분적으로만 성공함 (예: `conversations-*.json` 중 하나가 깨져서
  파싱 실패) — 콘솔의 `[경고]`/`⚠️` 로그를 확인해야 한다. 자동화 스크립트에서 이
  파이프라인을 호출한다면 반드시 종료 코드를 검사할 것.

## 출력 형식

세션(대화) 1개당 마크다운 노트 1개. frontmatter에 `title`/`session_id`/`url`/`date`/
`turns_count`/`tags`를 담고, 본문은 `> [!question]- User (...)` / `> [!tip]- <Vendor>
(...)` 콜아웃으로 turn을 나열한다. 이미지·파일 첨부는 `Attachments/`로 복사되고
가능하면 `![[...]]`로 임베드된다.

## 요구사항

런타임 파이프라인 자체는 표준 라이브러리만 사용한다 (Python 3.10+). 외부 패키지 설치
불필요. 테스트를 돌리려면 `pip install -r requirements-dev.txt` (pytest만 추가됨).

## 구조

```
common/                # 두 벤더가 공유하는 마크다운 안전장치 / 텍스트 유틸 / frontmatter 조립
├── markdown_safety.py   # 코드펜스 안전장치
├── text.py               # first_sentence / yaml_quote / sanitize_filename / format_callout
├── session_markdown.py  # frontmatter + callout 마크다운 조립
├── attachment_cache.py  # 첨부파일 리졸버 공통 뼈대 (캐싱, dry-run 복사, 집계)
└── zip_extract.py        # data/<vendor>/의 *.zip을 그 자리에 압축 해제
vendors/
├── base.py             # 벤더 모듈 인터페이스 계약 + 런타임 검증(validate)
├── chatgpt.py           # conversations*.json 트리 파싱 + .dat 첨부파일 복원
└── gemini.py             # "내 활동.html" 블록 파싱 + 로컬 첨부파일 매칭
run.py                  # CLI: 벤더 등록 시점 인터페이스 검증 + 자동 감지 + 실행
tests/                  # pytest — common/ 순수 함수 + 벤더 파싱 로직(트리 브랜치 선택,
                        # KST 파싱 등) 유닛 테스트
```

## 개발

```bash
pip install -r requirements-dev.txt
pytest
```

`common/`의 함수들은 순수 함수라 파일시스템 없이 바로 테스트한다. 벤더별 파서 중
`_active_branch_nodes`(ChatGPT 브랜치 선택), `_parse_kst`(Gemini 시간 파싱) 등
핵심 로직도 합성 데이터로 커버한다. 실제 대용량 takeout 데이터를 이용한 전체 파이프라인
검증(기존 결과물과의 byte-diff)은 자동 테스트에 포함하지 않았다 — 개인 데이터라 커밋할
수 없기 때문에, 회귀가 의심될 때 수동으로 재실행해서 비교한다.
