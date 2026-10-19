# 식품 표시·광고 도우미 챗봇 설계

2026-10-15 · 기준 문서: `식품 표시·광고 점검 챗봇 개요서.md`, 데모 화면(https://claude.ai/artifact/9CSFLUBRAHfzLTfuLbTyRc), 참고 구현: https://github.com/junhyuk0114/Aesthetic_chatbot

## 1. 목표와 합의 사항

카페·음식점·반찬가게 운영자와 온라인 식품 판매자가 메뉴판·상세페이지·SNS 문구를 넣으면, 위반 소지를 근거 조문(건강기능식품은 인정 기능성 문구 포함)과 함께 안내하는 RAG 챗봇을 4일 안에 만든다.

브레인스토밍에서 정한 것:

| 항목 | 결정 |
|---|---|
| 저장소 구성 | 에스테틱 챗봇 저장소를 이 폴더에 복사해 식품용으로 고친다 (폴더 구조·camelCase 함수명 유지) |
| 화면 | Spring을 쓰지 않고, FastAPI가 정적 HTML/JS(데모 화면 기반)를 함께 제공한다 |
| 식품 종류 선택 | 두 칸 토글 `[ 일반식품 \| 건강기능식품 ]`, 선택 전에는 입력 잠금 (필수) |
| 화면 답변 상태 | 4가지: 위반 소지 큼 / 위반 소지 낮음 / 판단 어려움 / 범위 밖 |
| 답변 형식 | 개요서 05장 그대로: 판단 한 줄 → 해야 할 일 → 근거 → 하단 고정 문구 |
| 거절 | 범위 밖·근거 없음은 LLM이 Context를 보고 스스로 판단 (점수 임계값 같은 별도 근거 검사·인용 검사 없음) |
| 표시사항 질문 | “표시사항에 꼭 넣어야 하는 항목은?” 같은 정보 질문은 범위 밖 |
| PostgreSQL | 사용하지 않음. 수집 이력은 `logs/*.jsonl` 파일로 기록 |
| 법령 데이터 | 개요서 03장 1~10번을 법제처 OpenAPI로 수집 (현재 미수집) |
| 식약처 데이터 | 이미 정제된 `data/foodsafety/materials.jsonl` 731건 사용 |
| git | GitHub `jynlee/food-ad-helper` private 저장소 |

## 2. 폴더 구조

```
food-ad-helper/
├─ scripts/
│  ├─ common/food_common.py        # mazel_common.py에서 PostgreSQL 제거, appendLog() 추가
│  ├─ collect/
│  │  ├─ law_map.py                # 수집 대상 표 (LAW_TARGETS, ADMRUL_TARGETS)
│  │  ├─ law_parse.py              # 법제처 JSON → 문서 (순수 함수)
│  │  ├─ law_store.py              # food-law-articles 매핑·비교·적용
│  │  ├─ collect_law.py            # 법률·시행령·시행규칙 8개 (target=law)
│  │  ├─ collect_admrul.py         # 고시 2개 (target=admrul)
│  │  ├─ fetch_foodsafety.py       # src/에서 이동 (원본 수집, 재실행하지 않음)
│  │  ├─ build_materials.py        # src/에서 이동 (정제)
│  │  └─ index_materials.py        # materials.jsonl → food-materials 인덱스
│  └─ rag/
│     ├─ embed_index.py            # 두 인덱스의 knn_vector 채우기
│     ├─ search_hybrid.py          # searchLaw(), searchMaterials()
│     ├─ answer_format.py          # 프롬프트 조립, LLM 출력 파싱, 근거 번호 → 조문 정보 (순수 함수)
│     ├─ rag_pipeline.py           # runFoodRag(): 검색 → 생성 → 파싱
│     ├─ rag_server.py             # FastAPI: /rag/query, /rag/health, /rag/status, 정적 화면 /
│     ├─ qa_cache.py               # 그대로 (scope만 변경)
│     └─ warm_cache.py             # FAQ를 식품 문구로 교체
├─ web/index.html                  # 데모 화면을 옮기고 API 연결
├─ data/law/                       # 법제처 원본 JSON (<법령ID>.json)
├─ data/foodsafety/                # 현재 그대로
├─ eval/questions.jsonl · metrics.py · eval_retrieval.py · eval_answers.py · report_*.md
├─ tests/                          # pytest (순수 함수만)
├─ logs/                           # collect.jsonl, law_history.jsonl (git 제외)
├─ docs/
├─ .env.example · requirements.txt · README.md
```

`src/`는 파일을 `scripts/collect/`로 옮긴 뒤 삭제한다. 두 스크립트의 `DIR`/`OUT_DIR`은 프로젝트 루트 기준 상대 경로라 그대로 동작한다(루트에서 실행).

에스테틱 저장소에서 가져오지 않는 것: `SPRING/` 전체, `collect_hazard.py`, `explore_api.py`, `init_db.sql`, `hazard-products` 관련 함수, `SYSTEM_PROMPT_LIST*`, `SYSTEM_PROMPT_COMBINED`, 추천질문(`extractSuggestions`, `filterGroundedSuggestions`), `stripSourceMentions`(출처를 지우는 함수라 이번 요구와 반대).

## 3. 설정 (`.env`)

```
LAW_OC=              # 법제처 OpenAPI OC
FOODSAFETY_KEY=      # 식품안전나라 (원본 재수집할 때만)
OS_HOST=https://localhost:9200
OS_USER=admin
OS_PASSWORD=
OLLAMA_HOST=http://localhost:11434
EMBED_MODEL=bge-m3
LLM_MODEL=gemma4:e4b
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
QA_CACHE_THRESHOLD=0.95
QA_CACHE_TTL_SEC=604800
```

`loadConfig()`는 에스테틱 버전에서 DB 항목을 빼고 `lawApiKey`를 `LAW_OC`에서 읽는다. 비밀번호 기본값은 코드에 두지 않는다.

## 4. 데이터 준비 (한 번 실행, 월 1회 재실행)

### 4.1 수집 대상 표 (`law_map.py`)

```python
LAW_TARGETS = [      # 법제처 현행 명칭. ID는 목록 조회(lawSearch.do)로 자동 확인해 data/law/resolved_ids.json 에 저장
    {"name": "식품 등의 표시·광고에 관한 법률", "kind": "법률", "food_type": "공통"},
    # 2 시행령, 3 시행규칙 → 공통
    # 4 건강기능식품에 관한 법률, 5 시행령, 6 시행규칙 → 건강기능식품
    {"name": "식품위생법", "kind": "법률", "food_type": "일반식품", "articles": ["44"], "annexes": []},
    {"name": "식품위생법 시행규칙", "kind": "시행규칙", "food_type": "일반식품", "articles": ["57"], "annexes": ["17"]},
]
ADMRUL_TARGETS = [   # 행정규칙. target=admrul 목록 조회로 행정규칙일련번호 확인
    {"name": "부당한 표시 또는 광고의 내용 기준", "kind": "고시", "food_type": "공통"},
    {"name": "건강기능식품의 기준 및 규격", "kind": "고시", "food_type": "건강기능식품"},
]
```

- `food_type` 값은 `공통` / `일반식품` / `건강기능식품`.
- 이름 매칭: 공백·가운뎃점을 빼고 같은 이름을 우선, 없으면 이름을 포함하는 후보가 하나일 때만 고른다. 고를 수 없으면 후보 목록을 보여주고 실패한다.
- `articles`가 있으면 그 조문만, `annexes`가 있으면 그 별표만 인덱싱한다(빈 리스트는 별표 없음). 식품위생법·시행규칙의 조문 번호(영업자 준수사항 제44조, 식품접객영업자 준수사항 시행규칙 제57조·별표 17)는 1일차에 A가 원본으로 확인한다.

### 4.2 법령 수집 (`collect_law.py`)

에스테틱 `collect_law.py`의 흐름을 유지한다.

1. `lawService.do?target=law&ID=<ID>&type=JSON` 호출, 응답을 `data/law/<ID>.json`에 저장. `--offline` 옵션이면 API 대신 저장된 파일을 읽는다.
2. `parseClauses()`: 항 단위 문서 생성, 호·목 내용 이어붙이기 (에스테틱과 동일). `조문여부=전문`(장·절 제목)은 건너뛴다. `articles` 필터 적용.
   `parseAnnexes()`: 별표도 문서로 만든다(식품표시광고법 시행령의 부당한 표시·광고 구체 내용 등이 별표에 있음). 별표 본문은 1,200자 안팎으로 줄 단위로 나눠 `article_no="별표 n"`, `clause_no="0"`으로 저장한다. `LAW_TARGETS`의 `annexes`가 있으면 그 별표만 넣는다.
3. `diffAndSnapshot()`: `content_hash` 비교로 바뀐 조문만 다시 인덱싱. 변경 이력은 `logs/law_history.jsonl`에 한 줄씩 기록(`recordLawHistory` 대체).
4. 실행 결과는 `logs/collect.jsonl`에 기록(`recordLog` 대체). `updateLawMeta`는 없앤다.

이력 기록은 모두 `food_common.appendLog(kind, record)` 한 함수만 거친다(`kind`: `collect` | `law_history`). 수집 스크립트는 저장 위치를 모른다. 나중에 OpenSearch `collect-log` 인덱스로 옮기려면 이 함수 안쪽만 `osClient.index()`로 바꾸고, 기존 jsonl은 한 번 읽어 bulk 적재하면 된다.

### 4.3 고시 수집 (`collect_admrul.py`)

- `lawService.do?target=admrul&ID=<ID>&type=JSON` 호출, `data/law/admrul_<ID>.json` 저장.
- 조 단위로 문서를 만든다(고시는 항 구조가 법령과 달라 1차는 조 단위, 받아 본 뒤 조정). 별표·별지가 본문에 있으면 별표 단위 문서로 추가한다.
- 문서 필드와 해시 비교·로그는 4.2와 같고, `kind="고시"`.
- 10번 고시를 받지 못하면 1~9번으로 진행하고, 08장 대응(“인정된 기능성인지 식약처 확인 필요”)을 프롬프트 지시로 넣는다.

### 4.4 인덱스

**`food-law-articles`** (법제처 법령·고시)

| 필드 | 타입 | 설명 |
|---|---|---|
| `_id` | — | `law_<ID>_<조문키>_<항번호>` / `admrul_<ID>_<조번호>` |
| `law_name` | keyword | 법령명 |
| `law_id` | keyword | 법제처 ID |
| `kind` | keyword | 법률 / 시행령 / 시행규칙 / 고시 |
| `food_type` | keyword | 공통 / 일반식품 / 건강기능식품 |
| `source_key` | keyword | `law_<ID>` / `admrul_<ID>` (재수집 때 삭제 감지 범위) |
| `article_no`, `clause_no` | keyword | 표시용 조문 번호(예: `8`, `3의2`, `별표 1`), 항 번호(없으면 `0`) |
| `title`, `content` | text | 조문 제목, 본문(`제n조(제목) n항\n...`) |
| `content_hash` | keyword | 변경 감지 |
| `effective_date` | date | 시행일 |
| `collected_at` | date | 수집일 (답변의 수집 기준일) |
| `knn_vector` | knn_vector 1024, hnsw, cosinesimil, lucene | BGE-M3 |

**`food-materials`** (식약처 인정 기능성, `index_materials.py`가 적재)

`materials.jsonl`의 필드(`_id`=인정번호, `material`, `claims`, `daily_intake`, `caution`, `approved`, `text`, `source`, `sector`, `datasets`)를 그대로 넣고 `collected_at`(materials.jsonl 파일 수정일), `knn_vector`를 더한다. `text`가 BM25·임베딩 대상이다.

`embed_index.py`는 인덱스마다 임베딩할 필드를 고른다: `food-law-articles`는 `content`, `food-materials`는 `text`. 실행 순서는 `collect_law` → `collect_admrul` → `index_materials` → `embed_index --index food-law-articles` → `embed_index --index food-materials`. 월 1회 갱신은 같은 순서를 다시 실행한다(바뀐 조문만 다시 인덱싱·임베딩).

## 5. 질의 처리

### 5.1 요청

`POST /rag/query`

```json
{ "query": "우리 카페 홍삼차, 혈당 관리에 최고!", "food_type": "general", "usage": "sns" }
```

| 필드 | 값 | 필수 |
|---|---|---|
| `query` | 문자열, 공백 제외 1자 이상 | 예 (아니면 400) |
| `food_type` | `general` \| `health` | 예 (아니면 422) |
| `usage` | `menu` \| `page` \| `sns` \| `null` | 아니요 |

`food_type` → 인덱스 값: `general` → `일반식품`, `health` → `건강기능식품`.

### 5.2 처리 순서 (`runFoodRag`)

1. **캐시 조회**: `lookupCache(..., docType="food", scope=f"{food_type}:{usage or '_'}")`. 적중하면 그대로 반환.
2. **법령 검색**: `searchLaw(query, foodType, topK=5)` — 하이브리드(BM25 0.3 + kNN 0.7, 검색 파이프라인 `food-hybrid-pipeline`), 필터 `food_type ∈ {선택값, 공통}`.
3. **인정 문구 검색**: `food_type=health`일 때만 `searchMaterials(query, topK=3)`.
4. **Context 조립**: 법령 결과에 `[1]`~`[5]`, 인정 문구에 이어지는 번호(`[6]`~`[8]`)를 붙인다.
   ```
   [법령 조문]
   [1] 식품 등의 표시·광고에 관한 법률 제8조 1항 (부당한 표시 또는 광고행위의 금지)
   ...본문...
   [인정 기능성 문구]
   [6] 원료: 홍삼 (인정번호 2024-20) / 인정 문구: 혈당 조절에 도움을 줄 수 있음
   ```
5. **LLM 생성 1회** (`generateAnswer`, temperature 0.1, num_ctx 8192 — 기존과 동일). 프롬프트에 식품 종류와 사용처를 넣는다. 사용처 지시: 메뉴판 → 메뉴명·설명 포함, 상세페이지 → 제품명·이미지 속 글자·후기 포함, SNS → 해시태그·이미지 속 글자 포함.
6. **파싱과 응답 조립** (`answer_format.py`).
7. **캐시 저장** 후 응답.

검색 결과가 0건이면 LLM을 부르지 않고 `out_of_scope`(사유 `no_basis`)로 응답한다.

### 5.3 LLM 출력 형식 (시스템 프롬프트로 강제)

```
[판단] 큼 | 낮음 | 어려움 | 범위밖
[판단이유] 한두 문장 (예: 일반식품에서 질병 예방·치료 효과를 나타내는 표현은 부당한 표시·광고에 해당할 수 있습니다.)
[해야할일]
1. ...
2. ...
[근거]
2 | 이 조문이 문구와 어떻게 관련되는지 한 문장 요약
6 | 인정 문구와의 비교 한 문장
[범위밖사유] 주제 | 근거없음        ← [판단] 범위밖일 때만
[식품종류] 일치 | 불일치
```

시스템 프롬프트 규칙:

- Context에 있는 내용만 근거로 쓴다. 근거는 Context 번호로만 적고 법령명·조문 번호를 직접 쓰지 않는다.
- “위법입니다”, “불법입니다”처럼 단정하지 않는다. 판단은 큼/낮음/어려움 중 하나.
- 질문이 식품·건강기능식품 표시·광고 문구 점검이 아니면(표시사항 항목 안내, 영업 신고·인허가, 위생 기준, 세금, 화장품·의약품 광고, 처분 결과 예측 등) `[판단] 범위밖`, `[범위밖사유] 주제`.
- Context 조문이 질문과 관련이 없으면 `[판단] 범위밖`, `[범위밖사유] 근거없음`.
- “위법인가요?” 같은 단정 요구는 위반 소지 수준과 근거만 답하고 해야 할 일에 전문가 상담을 넣는다.
- 질문 내용이 선택한 식품 종류와 다르면(예: 일반식품을 골랐는데 “건강기능식품인데…”) `[식품종류] 불일치`.
- 건강기능식품: 인정 문구와 같은 범위의 표현만 허용, 넘어서면 큼. 인정 문구를 찾지 못하면 어려움으로 두고 “인정된 기능성인지 식약처 확인 필요”를 해야 할 일에 넣는다.

### 5.4 파싱 규칙 (`answer_format.py`, 순수 함수)

| 함수 | 입력 → 출력 |
|---|---|
| `buildContext(lawHits, materialHits)` | 검색 결과 → (Context 문자열, `{번호: 결과}` 표) |
| `buildPrompt(foodType, usage, context, query)` | → 프롬프트 문자열 |
| `parseAnswer(raw)` | LLM 원문 → `{verdict, verdict_reason, actions, basis_refs[(번호, 요약)], out_of_scope_reason, food_type_mismatch}` 또는 파싱 실패 표시 |
| `resolveBasis(basisRefs, refTable)` | 번호 → 근거 항목 목록. 표에 없는 번호는 버린다 |
| `buildResponse(parsed, basis, refTable)` | → 응답 dict (수집 기준일·고정 문구 포함) |

- `[판단]` 값 매핑: 큼 → `high`, 낮음 → `low`, 어려움 → `unsure`, 범위밖 → `out_of_scope`.
- `[판단]` 태그가 없거나 값이 넷 중 하나가 아니면 파싱 실패: `verdict="unsure"`, `raw_fallback=원문`, `basis=[]`.
- `fixByteFallbackTokens()`는 에스테틱 코드를 그대로 쓴다.
- 범위 밖이면 `basis`는 비우고 `actions`는 서버 고정 문구로 채운다.
  - `topic`: “이 챗봇은 식품·건강기능식품의 표시·광고 문구만 점검합니다.” + “영업 신고·인허가는 관할 시·군·구청, 제품 심사·신고는 식품의약품안전처에 문의하세요.”
  - `no_basis`: “근거 조문을 찾지 못했습니다.” + “관할 시·군·구청 식품 담당 부서나 식품의약품안전처에 문의하세요.”
- 범위 안인데 `basis`가 비면 그대로 응답한다(거절하지 않음). 이 경우는 평가의 근거 표기율에서 드러난다.

### 5.5 응답

```json
{
  "success": true,
  "verdict": "high",
  "verdict_reason": "일반식품에서 질병 예방·치료 효과를 나타내는 표현은 부당한 표시·광고에 해당할 수 있습니다.",
  "actions": ["질병이나 치료를 암시하는 표현을 뺍니다.", "..."],
  "basis": [
    {"type": "law", "law_name": "식품 등의 표시·광고에 관한 법률", "article": "제8조 1항", "summary": "...", "effective_date": "20250101"},
    {"type": "material", "material": "홍삼", "recog_no": "2024-20", "claim": "혈당 조절에 도움을 줄 수 있음", "summary": "..."}
  ],
  "out_of_scope_reason": null,
  "food_type_mismatch": false,
  "collected_at": "2026-10-16",
  "disclaimer": "법령 정보 안내이며 법률 자문이 아닙니다. 확신이 없으면 관할 기관이나 전문가에게 확인하세요.",
  "raw_fallback": ""
}
```

- `verdict`: `high` | `low` | `unsure` | `out_of_scope`.
- `out_of_scope_reason`: `topic` | `no_basis` | `null`.
- `article`: `제{article_no}조` + (`clause_no`가 `0`이 아니면 ` {clause_no}항`). 별표는 `article_no` 그대로(`별표 1`).
- `collected_at`: `basis` 문서의 `collected_at` 중 가장 최근 값. `basis`가 비면 Context 문서 기준, 그것도 없으면 `food-law-articles` 전체의 최근 값.
- `disclaimer`는 항상 붙는다.
- 서버 오류(OpenSearch·Ollama 연결 실패 등)는 HTTP 500 `{"detail": "..."}`. 화면은 “잠시 후 다시 시도해 주세요”를 보여준다.

`GET /rag/health`, `GET /rag/status`(두 인덱스의 문서 수와 임베딩된 수)는 에스테틱과 같은 방식으로 둔다.

## 6. 화면 (`web/index.html`)

데모 화면 HTML/CSS를 옮기고 다음만 바꾼다.

- 식품 종류 드롭다운 → 두 칸 토글 `[ 일반식품 | 건강기능식품 ]` (`role="radiogroup"`, 사용처 버튼과 같은 모양). 선택 전 입력창·점검 버튼 비활성.
- 사용처 버튼(메뉴판/상세페이지/SNS)은 데모와 같음: 선택 사항, 다시 누르면 해제, 문구 속 단어로 자동 선택.
- 예시 칩: 일반식품의 “식품 표시사항에 꼭 넣어야 하는 항목이 뭔가요?”를 “‘천연 무첨가’라고 써도 되나요?”로 바꾼다. 범위 밖 예시 칩은 그대로.
- 미리 써 둔 답변(`classify`, `ans*` 함수)을 지우고 `fetch('/rag/query', {method:'POST', ...})`로 바꾼다. 응답 대기 중에는 기존 입력 중 표시를 쓴다.
- 답변 카드:
  - 상태 표시 4가지: `high` 위반 소지 큼(빨강) / `low` 위반 소지 낮음(초록) / `unsure` 판단 어려움(노랑) / `out_of_scope` 범위 밖(회색).
  - 판단 한 줄: 상태 표시 + `verdict_reason`.
  - 해야 할 일: `actions` 번호 목록.
  - 근거: 법령은 `법령명 · 제n조 n항 · 요약`, 인정 문구는 `원료명 · 제2024-20호 · 인정 문구 · 요약`.
  - 하단: `수집 기준일 {collected_at} · {disclaimer}`.
  - `raw_fallback`이 있으면 상태 표시 아래 원문을 그대로 보여준다.
  - `food_type_mismatch`면 “‘(다른 종류)’로 바꾸고 다시 점검” 버튼.
- 상단 “데모” 띠와 “데모 화면 · 답변은 미리 써 둔 예시” 문구를 지운다.
- 수집 법령 목록 카드에 「건강기능식품의 기준 및 규격」(고시)을 추가하고, 식약처 인정 기능성 데이터 항목을 추가한다.

`rag_server.py`는 `StaticFiles(directory="web", html=True)`를 `/`에 마운트한다(API 라우트 등록 후). 같은 출처라 CORS 설정은 필요 없다. 포트 5000.

## 7. 캐시

`qa_cache.py`는 인덱스 이름을 `food-qa-cache`, Redis 키 접두어를 `foodqa:`로 바꾸고(같은 OpenSearch·Redis를 쓰는 에스테틱 챗봇과 겹치지 않게) 호출만 바꾼다: `docType="food"`, `scope="{food_type}:{usage or '_'}"`. `warm_cache.py`의 FAQ는 개요서 05장 대표 입력과 데모 예시 칩으로 바꾸고 각 항목에 `food_type`, `usage`를 넣는다. 응답 형식이 바뀌므로 에스테틱 때 만든 `qa-cache` 인덱스·Redis 키는 쓰지 않는다(새 환경에서 시작).

## 8. 평가 (`eval/`)

### 8.1 문구 세트 `eval/questions.jsonl` (약 38개)

```json
{"id": "g01", "query": "SNS에 “면역력 강화에 좋아요”라고 올려도 되나요?", "food_type": "general", "usage": "sns",
 "category": "in_scope", "expected_verdict": "high",
 "gold_basis": ["식품 등의 표시·광고에 관한 법률 제8조"], "gold_recog_no": []}
```

| category | 개수 | 내용 |
|---|---|---|
| `in_scope` | 13 | 개요서 05장 대표 입력 5개 + 추가(질병 예방·치료, 기능성, 과장·단정 표현, 사용처 고루) |
| `variant` | 13 | `in_scope` 문구마다 말투·표현만 바꿈. 정답은 원문과 같음 |
| `out_of_scope` | 7 | 표시사항 항목 질문 2개 + 영업 신고, 위생 기준, 세금, 화장품·의약품 광고 등. `expected_verdict="out_of_scope"` |
| `no_basis` | 5 | 수집한 법령·고시로 답할 수 없는 질문. `expected_verdict="out_of_scope"` |

`gold_basis`는 `"법령명 제n조"`(항은 무시) 형식이고 법령 수집 후 A가 확정한다. 건강기능식품 문구는 `gold_recog_no`에 인정번호를 넣는다.

### 8.2 검색 평가 `eval/eval_retrieval.py`

`in_scope`·`variant` 문구로 BM25만 / kNN만 / 하이브리드 세 방식을 돌려, 상위 5개 안에 `gold_basis`(법령명+조 번호 일치)가 하나라도 들어온 비율(hit@5)을 표로 낸다. `searchLaw()`에 `mode="bm25" | "knn" | "hybrid"` 인자를 둔다.

### 8.3 답변 평가 `eval/eval_answers.py`

실행 중인 서버의 `/rag/query`를 호출해 계산한다.

| 지표 | 계산 | 대상 |
|---|---|---|
| 근거 표기율 | `basis`에 `type=law` 항목이 1개 이상인 비율 | in_scope, variant |
| 거절 정확도 | `verdict == "out_of_scope"`인 비율 | out_of_scope, no_basis |
| 인용 일치율 | `basis`의 `법령명 제n조` 중 하나라도 `gold_basis`에 있는 비율 | in_scope, variant |
| 단정 회피율 | `verdict_reason`·`actions`에 `위법입니다\|불법입니다\|위반입니다` 패턴이 없는 비율 | in_scope, variant |
| 판단 일치율 | `verdict == expected_verdict`인 비율 | 전체 |
| 인정 문구 대조 정확도 | `verdict == expected_verdict`이고 `gold_recog_no`가 `basis`의 `recog_no`에 있는 비율 | `food_type=health`이고 `gold_recog_no`가 있는 문구 |

결과(지표 표 + 문구별 결과)는 `eval/report_answers.md`, 검색 방식 비교는 `eval/report_retrieval.md`에 저장한다. 목표 수치는 첫 평가 후 팀이 정한다(근거 표기율 목표 100%).

## 9. 테스트

`tests/`에 pytest로 순수 함수만 테스트한다. OpenSearch·Ollama·Redis가 필요한 부분은 8장 평가 스크립트와 `/rag/health`로 확인한다.

| 대상 | 확인 내용 |
|---|---|
| `parseAnswer` | 정상 출력, 판단 값 4종 매핑, `[판단]` 누락·잘못된 값 → 파싱 실패, 범위밖 사유 2종, 식품종류 불일치 |
| `resolveBasis` | 번호 → 법령/인정 문구 항목 변환, 없는 번호 버림, 중복 번호 한 번만 |
| `buildResponse` | 범위 밖이면 basis 비움·고정 안내, `collected_at` 선택 규칙, disclaimer 항상 포함, 조문 표기(`제8조 1항`, 항 `0`이면 `제8조`) |
| `buildContext` | 법령 → 인정 문구 순 번호 부여, 인정 문구 없을 때 섹션 생략 |
| `parseClauses` | 저장한 법제처 JSON 샘플(`tests/fixtures/`)로 항·호·목 이어붙이기, `articles` 필터 |
| `build_materials` | `norm_id`, `split_claims`, `clean_material` 예시 값 |

## 10. 역할별 1일차 산출물 (인터페이스 합의)

| 담당 | 1일차에 고정할 것 |
|---|---|
| A 수집 | `resolved_ids.json`의 ID 10개, 식품위생법 `articles` 목록, `data/law/` 원본 |
| B 검색 | 4.4의 두 인덱스 매핑, `searchLaw()`/`searchMaterials()` 반환 형식 |
| C 답변 | 5.3 프롬프트 초안, 5.4 함수 시그니처, 5.5 응답 형식 |
| D 화면·평가 | `web/index.html`이 5.5 응답을 그리도록 목업 JSON으로 연결, `questions.jsonl` 초안 |

## 11. 범위 밖

Neo4j 조문 인용 그래프, 멀티턴 대화, PostgreSQL, Spring 화면, 판례·행정처분 사례, 회수·판매중지(I0490)·품목제조 신고(I0030), 점수 임계값 기반 근거 검사, 스트리밍 응답, 로그인.
