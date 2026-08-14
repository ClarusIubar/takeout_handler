# takeout_handler

한국어 | [English](README.en.md)

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

   원본을 `data/<vendor>/`로 옮기고 싶지 않으면(예: 다운로드 폴더에 있는 zip을 그대로
   쓰고 싶을 때) `--input`으로 위치를 직접 지정할 수 있다 — 코드 어디에도 실제 경로가
   박혀있지 않고 매 실행마다 원하는 곳을 가리킬 수 있다:

   ```bash
   python run.py --vendor gemini --input "gemini=C:\Users\me\Downloads\takeout.zip"
   ```

   폴더를 넘기면 그 폴더를 그대로 원본으로 쓰고(아무것도 복사/이동 안 함), `.zip`
   파일을 넘기면 원본은 그대로 둔 채 내용만 `data/<vendor>/`에 풀어서 쓴다.

3. 결과는 `result/<vendor>/*.md` (+ `result/<vendor>/Attachments/`)에 생성된다.

4. 검토가 끝났으면 `--publish`로 실제 옵시디언 vault에 반영한다 (아래 "설정" 참고).
   변환(2번)과 vault 반영(4번)을 분리해둔 이유는, 실제 PKM 저장소에 파일을 쓰는 건
   되돌리기 까다로운 작업이라 `result/`를 먼저 검토할 수 있게 하기 위함이다.

   ```bash
   python run.py --publish
   ```

## 설정 (config.json)

세 가지 경로 — takeout 원본 위치, 마크다운 변환 결과 위치, 실제 옵시디언 vault 위치 —
를 `config.json`으로 관리한다. 처음 실행하면 프로젝트 루트에 기본값으로 자동 생성된다
(구조는 `config.example.json` 참고). 개인 경로가 들어가는 파일이라 `.gitignore` 대상이다.

```json
{
  "takeout_paths": { "chatgpt": "", "gemini": "" },
  "markdown_output_dir": "result",
  "obsidian_vault_dir": "",
  "vault_subdirs": { "chatgpt": "ChatGPT", "gemini": "Gemini" }
}
```

**우선순위: CLI 플래그 > config.json > 내장 기본값.** 아무것도 안 정하면 기본값(원본은
`data/<vendor>/`, 변환 결과는 `result/`, vault는 미설정)으로 동작한다. 매번 다른 위치를
쓰고 싶으면 CLI로 그 실행만 오버라이드하고, 계속 같은 위치를 쓰고 싶으면 `config.json`을
직접 고치면 된다.

| 경로 | config.json 키 | CLI 오버라이드 | 기본값 |
|---|---|---|---|
| takeout 원본 | `takeout_paths.<vendor>` | `--input VENDOR=PATH` | `data/<vendor>/` |
| 마크다운 변환 결과 | `markdown_output_dir` | `--output-dir PATH` | `result/` |
| 옵시디언 vault | `obsidian_vault_dir` | `--vault-dir PATH` (`--publish`와 함께) | 미설정(발행 안 함) |

`--publish`로 vault에 반영할 때는 `vault_subdirs`에 설정된 이름으로 벤더별 하위 폴더가
자동 생성된다(`<vault>/ChatGPT/`, `<vault>/Gemini/`). **단순 미러링**이라 `vault_dir/
<vendor_subdir>/<filename>` 위치만 기준으로 upsert한다 — 사용자가 vault 안에서 노트를
다른 폴더로 옮기거나 이름을 바꿔도 추적하지 않으므로, 그 세션 내용이 나중에 바뀌면 옮긴
자리가 아니라 원래 위치에 새로 하나가 다시 생길 수 있다.

### 종료 코드

- `0`: 정상 완료.
- `1`: 실행된 벤더가 하나도 없음 (`data/<vendor>/`에 아무것도 없음).
- `2`: 일부 벤더가 부분적으로만 성공함 (예: `conversations-*.json` 중 하나가 깨져서
  파싱 실패) — 콘솔의 `[경고]`/`⚠️` 로그를 확인해야 한다. 자동화 스크립트에서 이
  파이프라인을 호출한다면 반드시 종료 코드를 검사할 것.

## 출력 형식

세션(대화) 1개당 마크다운 노트 1개. frontmatter에 `title`/`session_id`/`url`/`date`/
`turns_count`/`content_hash`/`tags`를 담고, 본문은 `> [!question]- User (...)` /
`> [!tip]- <Vendor> (...)` 콜아웃으로 turn을 나열한다. 이미지·파일 첨부는 `Attachments/`로
복사되고 가능하면 `![[...]]`로 임베드된다.

각 콜아웃 바로 앞에는 `<!-- turn: {"turn_index": 0, "role": "user", "parent_turn_index":
null, "has_attachment": false} -->` 형태의 HTML 주석이 붙는다. Obsidian 미리보기에는 안
보이지만, RAG 청킹 파이프라인이 콜아웃 문법(`[!question]` vs `[!tip]`)이나 "다음 질문
직전까지" 같은 순서 휴리스틱 없이 바로 QA 쌍·세션 경계·첨부 맥락을 읽어갈 수 있다.
- `parent_turn_index`: 그 답변이 어느 질문(turn_index)에 대한 것인지. 질문 턴은 항상
  `null`(새 turn window의 시작). 같은 질문에 답변이 여러 턴으로 나뉘어도(실제로 발생함 —
  긴 응답이 메시지 여러 개로 쪼개지는 경우) 전부 같은 `parent_turn_index`를 가리킨다.
- `has_attachment`: 그 턴 바로 뒤에 첨부파일 블록이 붙는지 여부.

파일명은 `title`이 아니라 `session_id` 기준이다 — Gemini는 ChatGPT와 달리 대화별
title을 제공하지 않기 때문이다 (설계 이유는 위키의
[Output Format](https://github.com/ClarusIubar/takeout_handler/wiki/Output-Format) 참고).

## MCP 서버 (선택 사항)

`result/`(또는 `--publish`한 vault)에 이미 렌더링된 세션을 Claude 같은 MCP 클라이언트가
직접 조회할 수 있게 `mcp_server/`가 [MCP](https://modelcontextprotocol.io) 서버를
제공한다. 파서/렌더러(`vendors/`, `common/`)는 건드리지 않고, 이미 만들어진 마크다운을
읽기만 한다 — `python run.py`로 변환/발행하는 흐름과는 별개다.

```bash
pip install -e .[mcp]   # 또는: pip install -r requirements-mcp.txt
python -m mcp_server    # --source vault로 vault를 직접 조회하게 바꿀 수도 있음
```

제공하는 tool: `list_sessions`(목록), `search_sessions`(제목/turn 텍스트 단순 검색),
`get_session`(세션 하나 전체 조회), `sync_takeout`(원본 재변환 — `result/`만 갱신하고
vault는 절대 건드리지 않는 유일한 쓰기 tool). 인증/원격 전송은 지원하지 않는다(stdio only,
로컬 프로세스로만 뜸).

**Claude Desktop** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "takeout-handler": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/takeout_handler"
    }
  }
}
```

**Claude Code**:
```bash
claude mcp add takeout-handler -- python -m mcp_server
```
(저장소 디렉터리에서 실행하거나, `cwd`를 저장소 경로로 지정)

## 요구사항

런타임 파이프라인 자체는 표준 라이브러리만 사용한다 (Python 3.10+). 외부 패키지 설치
불필요. 테스트를 돌리려면 `pip install -r requirements-dev.txt` (pytest만 추가됨).

MCP 서버 기능(`mcp_server/`, 아래 참고)만 예외적으로 `mcp` SDK를 필요로 한다 — 이 기능을
쓰지 않으면 설치할 필요 없다. `pip install -e .[mcp]` 또는 `pip install -r
requirements-mcp.txt`.

## 구조

```
common/                  # 두 벤더가 공유하는 로직
├── markdown_safety.py     # 코드펜스 안전장치
├── text.py                 # first_sentence / yaml_quote / sanitize_filename / format_callout
├── session_markdown.py    # frontmatter + callout 마크다운 조립, content_hash 계산/추출
├── attachment_cache.py    # 첨부파일 리졸버 공통 뼈대 (캐싱, dry-run 복사, 집계)
├── attachment_types.py    # 첨부파일 확장자 분류 (임베드 가능 여부 등, 두 벤더 공통)
├── zip_extract.py          # data/<vendor>/의 *.zip을 그 자리에 압축 해제 (zip slip 방어 포함)
├── fs_discovery.py         # __MACOSX 등 압축 도구 쓰레기 경로 필터링, 후보 모호성 처리
├── upsert.py                # content_hash 비교 기반 upsert 쓰기 (result/용)
├── publish.py                # result/ → 실제 vault 미러링 (--publish용, upsert 재사용)
├── config.py                  # config.json 로더 (없으면 기본값으로 생성)
└── session_reader.py            # session_markdown.py의 역함수 — 렌더링된 .md → SessionRecord (mcp_server용)
vendors/
├── base.py               # 벤더 모듈 인터페이스 계약(Protocol) + 런타임 검증 + 자동 탐색
├── chatgpt.py             # conversations*.json 트리 파싱 + .dat 첨부파일 복원
└── gemini.py               # "내 활동.html" 블록 파싱 + 로컬 첨부파일 매칭
mcp_server/               # MCP 서버 (선택 사항, 위 참고) — result/vault를 읽기만 함
├── config.py               # CLI 플래그/config.json 경로 해석
├── index.py                 # 렌더링된 .md 전체를 인메모리 조회 인덱스로 구성
├── pipeline.py               # sync_takeout용 — run.py:run_vendor() 재사용
├── server.py                  # tool/resource 등록
└── __main__.py                  # python -m mcp_server 진입점
run.py                    # CLI: config 로딩 + 경로 우선순위 해석 + 벤더 실행 + 발행
config.example.json       # config.json 구조 예시 (실제 config.json은 .gitignore 대상)
tests/                    # pytest — common/ 순수 함수 + 벤더 파싱 로직(트리 브랜치 선택,
                          # KST 파싱 등) + config/publish 유닛 테스트
```

## 개발

```bash
pip install -r requirements-dev.txt
pytest
```

`tests/`는 `unit`/`regression`/`integration`/`smoke` 4개 계층으로 나뉘어 있고,
`pytest -m smoke`처럼 계층별로 따로 돌릴 수 있다. 계층별 구성과 테스트 격리 방식은
위키의 [Development](https://github.com/ClarusIubar/takeout_handler/wiki/Development) 참고.

실제 대용량 takeout 데이터를 이용한 전체 파이프라인 검증(기존 결과물과의 byte-diff)은
자동 테스트에 포함하지 않았다 — 개인 데이터라 커밋할 수 없기 때문에, 회귀가 의심될 때
수동으로 재실행해서 비교한다.
