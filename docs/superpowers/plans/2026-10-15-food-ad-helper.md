# 식품 표시·광고 도우미 챗봇 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 메뉴판·상세페이지·SNS 광고 문구를 넣으면 위반 소지(큼/낮음/판단 어려움/범위 밖)와 근거 조문·인정 기능성 문구를 돌려주는 RAG 챗봇(수집 → 인덱스 → API → 웹 화면 → 평가)을 만든다.

**Architecture:** 법제처 법령 8개·고시 2개를 조문·별표 단위로 `food-law-articles`에, 식약처 인정 기능성 731건을 `food-materials`에 넣고 BGE-M3로 임베딩한다. FastAPI `/rag/query`가 캐시 확인 → 하이브리드 검색(식품 종류 필터) → Gemma 1회 생성 → 태그 형식 파싱(근거는 Context 번호만 받고 서버가 법령명·조문을 채움) 순서로 답하고, 같은 서버가 `web/index.html`을 제공한다. 에스테틱 챗봇(https://github.com/junhyuk0114/Aesthetic_chatbot)의 구조와 함수 이름 규칙을 따른다.

**Tech Stack:** Python 3.11, FastAPI, OpenSearch(neural-search hybrid, knn), Ollama(bge-m3, gemma4:e4b), Redis, requests, pytest, 순수 HTML/JS.

**Spec:** `docs/superpowers/specs/2026-10-15-food-ad-helper-design.md`

## Global Constraints

- 모든 명령은 저장소 루트(`food-ad-helper/`)에서 실행한다. Python 3.11.
- 인덱스·리소스 이름: `food-law-articles`, `food-materials`, `food-qa-cache`, 검색 파이프라인 `food-hybrid-pipeline`, Redis 키 접두어 `foodqa:`.
- 하이브리드 가중치 BM25 0.3 + kNN 0.7 (min_max 정규화, arithmetic_mean). 임베딩 `bge-m3` 1024차원, LLM `gemma4:e4b`, temperature 0.1, num_ctx 8192.
- API `food_type` 값 `general` | `health` ↔ 인덱스 `일반식품` | `건강기능식품`, 공통 법령은 `공통`.
- `verdict` 값 `high` | `low` | `unsure` | `out_of_scope`, 화면 표시 `위반 소지 큼` / `위반 소지 낮음` / `판단 어려움` / `범위 밖`.
- 고정 문구(글자 그대로): `법령 정보 안내이며 법률 자문이 아닙니다. 확신이 없으면 관할 기관이나 전문가에게 확인하세요.`
- PostgreSQL·Spring을 쓰지 않는다. 수집 이력은 `food_common.appendLog()`로만 기록한다.
- 함수 이름은 camelCase(에스테틱 규칙), 파일 맨 위에 모듈 설명 docstring, 구역은 `# ====` 구분선. 단 `scripts/collect/build_materials.py`, `fetch_foodsafety.py`는 기존 snake_case를 유지한다.
- 비밀값은 `.env`에만 둔다. 코드에 비밀번호 기본값을 넣지 않는다.
- git 커밋 메시지에 `Co-Authored-By` 등 Claude 표기 줄을 넣지 않는다.

## Review Focus

1. **LLM이 형식을 조금 다르게 쓰는 경우** (`**[판단]** 위반 소지 큼`, `【판단】`, `[근거] 2, 4`) → 정상 파싱되어야 한다. Task 8 테스트에 포함.
2. **LLM 출력·법령 본문에 HTML 문자(`<script>` 등)가 들어간 경우** → 화면은 글자로만 보여야 한다(`textContent`만 사용). Task 10 점검 단계에 포함.
3. **빈 문구, 2,000자 넘는 붙여넣기, 잘못된 food_type** → 400/422와 알아볼 수 있는 메시지. Task 11 테스트에 포함.
4. **OpenSearch·Ollama·Redis 중 하나가 꺼진 경우** → Redis/캐시 장애는 답변에 영향 없음, 검색·LLM 장애는 500 + 화면 오류 안내(무한 대기 없음, 200초 타임아웃). Task 9·11 테스트, Task 10 타임아웃에 포함.
5. **수집을 두 번 연속 실행한 경우** → 문서 중복·임베딩 삭제 없이 `collected_at`만 갱신. Task 2 `planChanges` 테스트에 포함.

## 파일 구조

| 파일 | 책임 |
|---|---|
| `requirements.txt`, `pytest.ini`, `tests/conftest.py` | 의존성, 테스트 경로 설정 |
| `scripts/common/food_common.py` | 설정 로드, 재시도 GET, OpenSearch 클라이언트, `appendLog`, 식품 종류 상수 |
| `scripts/collect/law_parse.py` | 법제처 JSON → 문서 (순수 함수), 변경 계획 `planChanges`, 이름 매칭 `pickTarget` |
| `scripts/collect/law_store.py` | `food-law-articles` 매핑·조회·적용 (OpenSearch) |
| `scripts/collect/law_map.py` | 수집 대상 10개 표 |
| `scripts/collect/collect_law.py`, `collect_admrul.py` | API 호출·원본 저장·문서화·저장 실행 |
| `scripts/collect/index_materials.py` | `materials.jsonl` → `food-materials` |
| `scripts/collect/fetch_foodsafety.py`, `build_materials.py` | 기존 스크립트(이동) |
| `scripts/rag/embed_index.py` | 두 인덱스 임베딩 |
| `scripts/rag/search_hybrid.py` | `searchLaw`, `searchMaterials`, 쿼리 생성 |
| `scripts/rag/answer_format.py` | Context·프롬프트·파싱·응답 조립 (순수 함수) |
| `scripts/rag/qa_cache.py` | 시맨틱 캐시 |
| `scripts/rag/rag_pipeline.py` | `runFoodRag`, `generateAnswer` |
| `scripts/rag/rag_server.py` | FastAPI + 정적 화면 |
| `scripts/rag/warm_cache.py`, `scripts/run_monthly.py` | 캐시 워밍, 월 1회 갱신 |
| `web/index.html` | 화면 |
| `eval/metrics.py`, `eval/questions.jsonl`, `eval/eval_retrieval.py`, `eval/eval_answers.py` | 평가 |

## 사전 준비 (Task 3 이후 필요)

- `.env`에 `LAW_OC`, `OS_HOST`, `OS_USER`, `OS_PASSWORD`, `REDIS_*` 입력
- OpenSearch 실행(neural-search 플러그인 포함), Ollama에 `bge-m3`, `gemma4:e4b` 받아 두기(`ollama pull bge-m3`, `ollama pull gemma4:e4b`), Redis 실행

---

### Task 1: 프로젝트 뼈대와 공통 모듈

**Files:**
- Create: `requirements.txt`, `pytest.ini`, `tests/conftest.py`, `scripts/common/food_common.py`, `tests/test_food_common.py`, `tests/test_build_materials.py`, `data/foodsafety/COLLECTED_AT`
- Move: `src/fetch_foodsafety.py` → `scripts/collect/fetch_foodsafety.py`, `src/build_materials.py` → `scripts/collect/build_materials.py`
- Modify: `scripts/collect/build_materials.py` (`clean_material` 정규식), `.env.example`, `.gitignore`, `data/foodsafety/materials.jsonl`(재생성)

**Interfaces:**
- Produces: `food_common.ROOT: Path`, `FOOD_TYPE_MAP = {"general": "일반식품", "health": "건강기능식품"}`, `COMMON = "공통"`, `loadConfig() -> dict`(키: `osHost, osUser, osPassword, ollamaHost, embedModel, llmModel, redisHost, redisPort, redisDb, redisPassword, qaCacheThreshold, qaCacheTtlSec, lawApiKey, foodsafetyKey`), `retryGet(url, params, maxRetry=5, sleepSec=2) -> requests.Response`, `getOsClient(cfg) -> OpenSearch`, `appendLog(kind: str, record: dict, logDir=None) -> None`

- [ ] **Step 1: 의존성과 테스트 설정 파일 만들기**

`requirements.txt`:
```
requests>=2.32
python-dotenv>=1.0
opensearch-py>=2.7
redis>=5.0
fastapi>=0.115
uvicorn>=0.30
pydantic>=2.9
httpx>=0.27
pytest>=8.3
```

`pytest.ini`:
```ini
[pytest]
testpaths = tests
```

`tests/conftest.py`:
```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for sub in ("scripts/common", "scripts/collect", "scripts/rag", "eval"):
    sys.path.insert(0, str(ROOT / sub))
```

Run: `pip install -r requirements.txt`
Expected: 오류 없이 설치(이미 있는 패키지는 `Requirement already satisfied`).

- [ ] **Step 2: 기존 스크립트를 옮긴다**

```bash
mkdir -p scripts/common scripts/collect scripts/rag tests/fixtures web
git mv src/fetch_foodsafety.py scripts/collect/fetch_foodsafety.py
git mv src/build_materials.py scripts/collect/build_materials.py
```
Expected: `src/` 폴더가 비고 사라진다(`ls src` → No such file).

- [ ] **Step 3: 실패하는 테스트 작성**

`tests/test_food_common.py`:
```python
import json

import pytest

from food_common import COMMON, FOOD_TYPE_MAP, appendLog, loadConfig


def test_appendLog_writes_one_json_line_per_call(tmp_path):
    appendLog("collect", {"source": "law_1", "status": "success"}, logDir=tmp_path)
    appendLog("collect", {"source": "law_2", "status": "failed"}, logDir=tmp_path)
    lines = (tmp_path / "collect.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["source"] for line in lines] == ["law_1", "law_2"]
    assert "logged_at" in json.loads(lines[0])


def test_appendLog_keeps_korean_readable(tmp_path):
    appendLog("law_history", {"law_name": "식품위생법"}, logDir=tmp_path)
    assert "식품위생법" in (tmp_path / "law_history.jsonl").read_text(encoding="utf-8")


def test_appendLog_rejects_unknown_kind(tmp_path):
    with pytest.raises(ValueError):
        appendLog("other", {}, logDir=tmp_path)


def test_loadConfig_reads_law_oc(monkeypatch):
    monkeypatch.setenv("LAW_OC", "my-oc")
    assert loadConfig()["lawApiKey"] == "my-oc"


def test_food_type_constants():
    assert FOOD_TYPE_MAP == {"general": "일반식품", "health": "건강기능식품"}
    assert COMMON == "공통"
```

`tests/test_build_materials.py`:
```python
from build_materials import clean_material, norm_id, split_claims


def test_norm_id_unifies_formats():
    assert norm_id("제2006-11호") == "2006-11"
    assert norm_id("New제2007-13호") == "2007-13"
    assert norm_id("2006-11") == "2006-11"


def test_clean_material_strips_recognition_suffix():
    assert clean_material("두충우슬추출복합물(KGC08EA)(제2023-40호)") == "두충우슬추출복합물(KGC08EA)"
    assert clean_material("바이오게르마늄 효모(기능성원료인정제2006-11호)") == "바이오게르마늄 효모"


def test_clean_material_strips_new_prefixed_suffix():
    assert clean_material("차조기등복합추출물(기능성원료인정New제2007-13호)") == "차조기등복합추출물"


def test_split_claims_keeps_korean_only_and_drops_grade_mark():
    assert split_claims("(국문) 관절 건강에 도움을 줄 수 있음(기타기능II) (영문) May help") == ["관절 건강에 도움을 줄 수 있음"]


def test_split_claims_reads_quoted_sentences():
    text = '"장내 유익균의 증식과 유해균의 억제에 도움을 줄 수 있습니다." “배변활동을 원활히 하는데 도움을 줄 수 있습니다.” (기타기능II)'
    assert split_claims(text) == ["장내 유익균의 증식과 유해균의 억제에 도움을 줄 수 있습니다",
                                  "배변활동을 원활히 하는데 도움을 줄 수 있습니다"]


def test_split_claims_empty_marker_gives_empty_list():
    assert split_claims(".") == []
```

- [ ] **Step 4: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_food_common.py tests/test_build_materials.py -v`
Expected: `test_food_common.py`는 `ModuleNotFoundError: No module named 'food_common'`으로 수집 실패, `test_clean_material_strips_new_prefixed_suffix`는 FAIL(`'차조기등복합추출물(기능성원료인정New제2007-13호)' != '차조기등복합추출물'`).

- [ ] **Step 5: `food_common.py` 작성**

`scripts/common/food_common.py`:
```python
# -*- coding: utf-8 -*-
"""
food_common.py
식품 표시·광고 도우미 챗봇 — 공통 유틸리티
(에스테틱 챗봇 mazel_common.py 에서 PostgreSQL 부분을 빼고 파일 로그로 바꿈)

포함 함수:
- loadConfig  : .env 로드 → 설정 딕셔너리 반환
- retryGet    : GET 요청 실패 시 최대 N회 재시도 (선형 백오프)
- getOsClient : OpenSearch 클라이언트 반환
- appendLog   : 수집 이력을 logs/<kind>.jsonl 에 한 줄씩 기록
                (나중에 OpenSearch collect-log 인덱스로 옮길 때는 이 함수 안쪽만 바꾼다)
"""

# ============================================================
# 라이브러리 임포트
# ============================================================

import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from opensearchpy import OpenSearch


# ============================================================
# 상수 정의
# ============================================================

ROOT          = Path(__file__).resolve().parents[2]
LOG_DIR       = ROOT / "logs"
LOG_KINDS     = ("collect", "law_history")
FOOD_TYPE_MAP = {"general": "일반식품", "health": "건강기능식품"}
COMMON        = "공통"


# ============================================================
# 설정 로드
# ============================================================

def loadConfig():
    """
    프로젝트 루트의 .env 파일을 로드하고 설정값을 딕셔너리로 반환.
    이미 환경변수로 들어 있는 값이 있으면 그 값을 우선한다.
    """
    load_dotenv(ROOT / ".env")

    cfg = {
        # OpenSearch
        'osHost':     os.getenv("OS_HOST",     "https://localhost:9200"),
        'osUser':     os.getenv("OS_USER",     "admin"),
        'osPassword': os.getenv("OS_PASSWORD", ""),

        # Ollama
        'ollamaHost': os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        'embedModel': os.getenv("EMBED_MODEL", "bge-m3"),
        'llmModel':   os.getenv("LLM_MODEL",   "gemma4:e4b"),

        # Redis (질문-답변 시맨틱 캐시)
        'redisHost':        os.getenv("REDIS_HOST",     "localhost"),
        'redisPort':        int(os.getenv("REDIS_PORT", 6379)),
        'redisDb':          int(os.getenv("REDIS_DB",   0)),
        'redisPassword':    os.getenv("REDIS_PASSWORD", ""),
        'qaCacheThreshold': float(os.getenv("QA_CACHE_THRESHOLD", 0.95)),
        'qaCacheTtlSec':    int(os.getenv("QA_CACHE_TTL_SEC", 60 * 60 * 24 * 7)),

        # 공공데이터 API
        'lawApiKey':     os.getenv("LAW_OC",         ""),
        'foodsafetyKey': os.getenv("FOODSAFETY_KEY", ""),
    }
    return cfg


# ============================================================
# API 재시도 유틸
# ============================================================

def retryGet(url, params, maxRetry=5, sleepSec=2):
    """
    GET 요청 실패 시 최대 maxRetry회 재시도 (선형 백오프: 2s, 4s, 6s...).
    - ConnectionError / Timeout / 429 → 재시도
    - 그 외 HTTPError (4xx/5xx)       → 즉시 raise
    """
    lastErr = None
    for attempt in range(0, maxRetry):
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                waitSec = sleepSec * (attempt + 2)
                print(f"  [retry {attempt+1}/{maxRetry}] Rate limit, {waitSec}s 대기")
                time.sleep(waitSec)
                lastErr = requests.exceptions.HTTPError("429 Too Many Requests")
                continue
            resp.raise_for_status()
            return resp
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.ChunkedEncodingError) as e:
            lastErr = e
            if attempt < maxRetry - 1:
                waitSec = sleepSec * (attempt + 1)
                print(f"  [retry {attempt+1}/{maxRetry}] {type(e).__name__}, {waitSec}s 대기")
                time.sleep(waitSec)
    raise lastErr or RuntimeError("retryGet 최대 재시도 초과")


# ============================================================
# OpenSearch 클라이언트
# ============================================================

def getOsClient(cfg):
    """
    OpenSearch 클라이언트 객체 반환.
    개발 환경 데모 인증서 사용으로 SSL 검증 비활성화.
    """
    stripped = cfg['osHost'].replace("https://", "").replace("http://", "")
    useSSL   = cfg['osHost'].startswith("https")
    if ":" in stripped:
        rawHost, rawPort = stripped.rsplit(":", 1)
        rawPort = int(rawPort)
    else:
        rawHost = stripped
        rawPort = 9200

    return OpenSearch(
        hosts=[{"host": rawHost, "port": rawPort}],
        http_auth=(cfg['osUser'], cfg['osPassword']),
        use_ssl=useSSL,
        verify_certs=False,
        ssl_show_warn=False,
    )


# ============================================================
# 수집 이력 기록
# ============================================================

def appendLog(kind, record, logDir=None):
    """
    수집 이력을 logs/<kind>.jsonl 에 한 줄(JSON)로 덧붙인다.
    kind   : "collect"(수집 실행 결과) | "law_history"(조문 변경 이력)
    record : 기록할 dict. logged_at(기록 시각)은 자동으로 붙는다.
    """
    if kind not in LOG_KINDS:
        raise ValueError(f"알 수 없는 로그 종류: {kind}")
    targetDir = Path(logDir) if logDir else LOG_DIR
    targetDir.mkdir(parents=True, exist_ok=True)
    row = {"logged_at": datetime.now().isoformat(timespec="seconds")}
    row.update(record)
    with open(targetDir / f"{kind}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
```

- [ ] **Step 6: `clean_material` 정규식 수정**

`scripts/collect/build_materials.py`의 `clean_material` 함수를 다음으로 바꾼다:
```python
def clean_material(name: str) -> str:
    """원료명 끝의 인정번호 표기 제거: (기능성원료인정제2006-11호), (기능성원료인정New제2007-13호), (제2023-40호)"""
    return re.sub(r"\((?:기능성원료인정)?\s*(?:New)?\s*제?\d{4}-\d+호?\)\s*$", "", clean(name)).strip()
```

- [ ] **Step 7: 테스트 통과 확인**

Run: `python -m pytest tests/test_food_common.py tests/test_build_materials.py -v`
Expected: 11 passed.

- [ ] **Step 8: `materials.jsonl` 재생성과 수집일 파일**

Run: `python scripts/collect/build_materials.py`
Expected 출력:
```
I-0040 779건 + I-0050 454건 → 인정번호 기준 786건 (겹친 447건 합침)
기능성 문구가 비어 있는 55건 제외 → 최종 731건
저장: data/foodsafety/materials.jsonl
```
Run: `grep -c "New제" data/foodsafety/materials.jsonl`
Expected: `0`

`data/foodsafety/COLLECTED_AT` (한 줄, 식품안전나라 원본 수집일):
```
2026-10-15
```

- [ ] **Step 9: `.env.example`, `.gitignore` 갱신**

`.env.example`:
```
# 복사해서 .env 로 만들고 실제 값을 넣으세요 (.env 는 git에 올리지 않습니다)
LAW_OC=
FOODSAFETY_KEY=

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

`.gitignore` 끝에 `.pytest_cache/`를 추가한다(`logs/`는 이미 있음).

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "프로젝트 뼈대와 공통 모듈 추가, 원료명 New 인정번호 표기 제거"
```

---

### Task 2: 법령 파서 (`law_parse.py`)

**Files:**
- Create: `scripts/collect/law_parse.py`, `tests/test_law_parse.py`, `tests/fixtures/law_sample.json`, `tests/fixtures/admrul_sample.json`

**Interfaces:**
- Consumes: 없음 (순수 함수, 표준 라이브러리만)
- Produces:
  - `INDEX_NAME = "food-law-articles"`
  - `asList(v) -> list`, `flattenText(v) -> list[str]`, `chunkText(lines, maxLen=1200) -> list[str]`, `hashContent(s) -> str`, `parseDate(raw) -> str | None`(`"20250101"` 형식)
  - `meta` dict 형식: `{"info": {"name", "kind", "food_type", "articles"?: list[str] | None, "annexes"?: list[str] | None}, "lawId": str, "sourceKey": str, "effectiveDate": str | None, "collectedAt": "YYYY-MM-DD"}`
  - 문서 형식: `{"_index": INDEX_NAME, "_id": str, "_source": {"law_name","law_id","source_key","kind","food_type","article_no","clause_no","title","content","content_hash","effective_date","collected_at"}}`
  - `parseClauses(lawData, meta) -> list[doc]`, `parseAnnexes(annexUnits, meta) -> list[doc]`, `parseAdmrulArticles(lines, meta) -> list[doc]`
  - `normalizeName(s) -> str`, `pickTarget(candidates, name, nameKey) -> dict` (실패 시 `LookupError`)
  - `planChanges(docs, existing) -> {"toIndex": list[doc], "unchangedIds": list[str], "removedIds": list[str], "history": list[dict]}`

- [ ] **Step 1: 테스트용 원본 샘플 만들기**

법제처 응답 구조(에스테틱 `collect_law.py`가 실제로 처리한 키: `법령/기본정보/조문/조문단위/항/호/목`)를 줄인 샘플이다. Task 3에서 실제 응답을 받아 비교한다.

`tests/fixtures/law_sample.json`:
```json
{"법령": {
  "기본정보": {"법령명_한글": "식품 등의 표시·광고에 관한 법률", "시행일자": "20250101"},
  "조문": {"조문단위": [
    {"조문키": "0001000", "조문번호": "1", "조문여부": "전문", "조문내용": "제1장 총칙"},
    {"조문키": "0001001", "조문번호": "1", "조문여부": "조문", "조문제목": "목적",
     "조문내용": "제1조(목적) 이 법은 식품등에 관하여 올바른 표시ㆍ광고를 하도록 한다."},
    {"조문키": "0008001", "조문번호": "8", "조문여부": "조문", "조문제목": "부당한 표시 또는 광고행위의 금지",
     "조문내용": "제8조(부당한 표시 또는 광고행위의 금지)",
     "항": [
       {"항번호": "①", "항내용": "① 누구든지 식품등의 명칭ㆍ제조방법ㆍ성분 등에 관하여 다음 각 호의 어느 하나에 해당하는 표시 또는 광고를 하여서는 아니 된다.",
        "호": [
          {"호번호": "1.", "호내용": "1. 질병의 예방ㆍ치료에 효능이 있는 것으로 인식할 우려가 있는 표시 또는 광고"},
          {"호번호": "2.", "호내용": "2. 식품등을 의약품으로 인식할 우려가 있는 표시 또는 광고",
           "목": [{"목번호": "가.", "목내용": "가. 예시 목 내용"}]}
        ]},
       {"항번호": "②", "항내용": "② 제1항 각 호의 구체적인 내용은 대통령령으로 정한다."}
     ]},
    {"조문키": "0008002", "조문번호": "8", "조문가지번호": "2", "조문여부": "조문", "조문제목": "가지 조문",
     "항": {"항번호": "①", "항내용": "① 항이 하나뿐이면 dict로 온다."}}
  ]},
  "별표": {"별표단위": [
    {"별표번호": "0001", "별표가지번호": "00", "별표구분": "별표", "별표제목": "부당한 표시 또는 광고의 내용",
     "별표내용": [["1. 질병의 예방ㆍ치료에 효능이 있는 것으로 인식할 우려가 있는 표시 또는 광고",
                   "가. 질병 또는 질병군의 발생을 예방한다는 내용의 표시ㆍ광고"]]},
    {"별표번호": "0002", "별표가지번호": "00", "별표구분": "서식", "별표제목": "신고서", "별표내용": "서식 내용"}
  ]}
}}
```

`tests/fixtures/admrul_sample.json`:
```json
{"AdmRulService": {
  "행정규칙기본정보": {"행정규칙명": "식품등의 부당한 표시 또는 광고의 내용 기준", "시행일자": "20240101"},
  "조문내용": [
    "제1장 총칙",
    "제1조(목적) 이 고시는 부당한 표시 또는 광고의 내용 기준을 정함을 목적으로 한다.",
    "제2조(정의) 이 고시에서 사용하는 용어의 뜻은 다음과 같다.\n1. \"질병\"이란 신체의 이상 상태를 말한다.",
    "2. 두 번째 정의",
    "제3조의2(특례) 가지 조문 내용"
  ],
  "별표": {"별표단위": [
    {"별표번호": "0001", "별표가지번호": "00", "별표제목": "질병 표현 예시", "별표내용": "1. 당뇨\n2. 고혈압"}
  ]}
}}
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_law_parse.py`:
```python
import json
from pathlib import Path

import pytest

from law_parse import (INDEX_NAME, chunkText, flattenText, hashContent, parseAdmrulArticles,
                       parseAnnexes, parseClauses, parseDate, pickTarget, planChanges)

FIX = Path(__file__).parent / "fixtures"
LAW = json.loads((FIX / "law_sample.json").read_text(encoding="utf-8"))
ADM = json.loads((FIX / "admrul_sample.json").read_text(encoding="utf-8"))


def makeMeta(articles=None, annexes=None, sourceKey="law_100"):
    info = {"name": "식품 등의 표시·광고에 관한 법률", "kind": "법률", "food_type": "공통"}
    if articles is not None:
        info["articles"] = articles
    if annexes is not None:
        info["annexes"] = annexes
    return {"info": info, "lawId": "100", "sourceKey": sourceKey,
            "effectiveDate": "20250101", "collectedAt": "2026-10-16"}


def annexUnits(data):
    return data["법령"]["별표"]["별표단위"]


# ---------- 기본 유틸 ----------

def test_flattenText_flattens_nested_lists_and_newlines():
    assert flattenText([["a", "b\nc"], "d", None]) == ["a", "b", "c", "d"]


def test_chunkText_splits_by_length_without_breaking_lines():
    lines = ["가" * 500, "나" * 500, "다" * 500]
    chunks = chunkText(lines, maxLen=1200)
    assert len(chunks) == 2
    assert chunks[0] == "가" * 500 + "\n" + "나" * 500
    assert chunks[1] == "다" * 500


def test_parseDate_normalizes_or_returns_none():
    assert parseDate("2025-01-01") == "20250101"
    assert parseDate("2025.01.01") == "20250101"
    assert parseDate("") is None


# ---------- 법령 조문 ----------

def test_parseClauses_builds_clause_docs_and_skips_headings():
    docs = parseClauses(LAW, makeMeta())
    ids = [d["_id"] for d in docs]
    assert ids == ["law_100_0001001_0", "law_100_0008001_1", "law_100_0008001_2", "law_100_0008002_1"]
    assert all(d["_index"] == INDEX_NAME for d in docs)


def test_parseClauses_joins_items_and_subitems_into_clause():
    doc = parseClauses(LAW, makeMeta())[1]["_source"]
    assert doc["article_no"] == "8" and doc["clause_no"] == "1"
    assert doc["content"].startswith("제8조(부당한 표시 또는 광고행위의 금지) 1항\n")
    assert "1. 질병의 예방ㆍ치료에 효능" in doc["content"]
    assert "가. 예시 목 내용" in doc["content"]
    assert doc["content_hash"] == hashContent(doc["content"])
    assert doc["food_type"] == "공통" and doc["collected_at"] == "2026-10-16"
    assert doc["source_key"] == "law_100" and doc["law_id"] == "100"


def test_parseClauses_handles_branch_article_and_single_clause_dict():
    doc = parseClauses(LAW, makeMeta())[3]["_source"]
    assert doc["article_no"] == "8의2"
    assert "항이 하나뿐이면" in doc["content"]


def test_parseClauses_article_filter():
    docs = parseClauses(LAW, makeMeta(articles=["8"]))
    assert [d["_source"]["article_no"] for d in docs] == ["8", "8"]


# ---------- 별표 ----------

def test_parseAnnexes_keeps_annex_and_skips_forms():
    docs = parseAnnexes(annexUnits(LAW), makeMeta())
    assert [d["_id"] for d in docs] == ["law_100_annex1_p1"]
    src = docs[0]["_source"]
    assert src["article_no"] == "별표 1" and src["clause_no"] == "0"
    assert src["content"].startswith("[별표 1] 부당한 표시 또는 광고의 내용\n")
    assert "질병 또는 질병군의 발생을 예방" in src["content"]


def test_parseAnnexes_filter_and_empty_filter():
    assert parseAnnexes(annexUnits(LAW), makeMeta(annexes=["2"])) == []
    assert parseAnnexes(annexUnits(LAW), makeMeta(annexes=[])) == []


def test_parseAnnexes_reads_six_digit_number_with_branch():
    units = [{"별표번호": "000102", "별표제목": "가지 별표", "별표내용": "내용"}]
    docs = parseAnnexes(units, makeMeta())
    assert docs[0]["_source"]["article_no"] == "별표 1의2"


def test_parseAnnexes_splits_long_annex_into_parts():
    units = [{"별표번호": "0003", "별표제목": "긴 별표", "별표내용": ["가" * 700, "나" * 700]}]
    docs = parseAnnexes(units, makeMeta())
    assert [d["_id"] for d in docs] == ["law_100_annex3_p1", "law_100_annex3_p2"]


# ---------- 행정규칙(고시) ----------

def test_parseAdmrulArticles_groups_lines_by_article():
    meta = makeMeta(sourceKey="admrul_200")
    lines = flattenText(ADM["AdmRulService"]["조문내용"])
    docs = parseAdmrulArticles(lines, meta)
    assert [d["_id"] for d in docs] == ["admrul_200_1", "admrul_200_2", "admrul_200_3의2"]
    second = docs[1]["_source"]
    assert second["title"] == "정의"
    assert "2. 두 번째 정의" in second["content"]
    assert docs[2]["_source"]["article_no"] == "3의2"


def test_parseAdmrulArticles_keeps_first_when_number_repeats():
    meta = makeMeta(sourceKey="admrul_200")
    docs = parseAdmrulArticles(["제1조(목적) 본문", "제1조(시행일) 부칙"], meta)
    assert len(docs) == 1 and "본문" in docs[0]["_source"]["content"]


# ---------- 이름 매칭 ----------

def test_pickTarget_prefers_exact_name_over_longer_names():
    cands = [{"법령명한글": "식품 등의 표시ㆍ광고에 관한 법률 시행령"},
             {"법령명한글": "식품 등의 표시ㆍ광고에 관한 법률"},
             {"법령명한글": "식품 등의 표시ㆍ광고에 관한 법률 시행규칙"}]
    found = pickTarget(cands, "식품 등의 표시·광고에 관한 법률", "법령명한글")
    assert found["법령명한글"] == "식품 등의 표시ㆍ광고에 관한 법률"


def test_pickTarget_accepts_single_partial_match_and_dict_candidate():
    cand = {"행정규칙명": "식품등의 부당한 표시 또는 광고의 내용 기준"}
    assert pickTarget(cand, "부당한 표시 또는 광고의 내용 기준", "행정규칙명") == cand


def test_pickTarget_raises_when_ambiguous_or_missing():
    cands = [{"n": "가 기준 A"}, {"n": "가 기준 B"}]
    with pytest.raises(LookupError):
        pickTarget(cands, "가 기준", "n")
    with pytest.raises(LookupError):
        pickTarget([], "없는 법", "n")


# ---------- 변경 계획 ----------

def doc(docId, content):
    return {"_index": INDEX_NAME, "_id": docId,
            "_source": {"law_name": "법", "source_key": "law_100", "article_no": "1", "clause_no": "0",
                        "content": content, "content_hash": hashContent(content)}}


def test_planChanges_classifies_added_modified_unchanged_removed():
    existing = {
        "a": {"content": "같음", "content_hash": hashContent("같음"), "article_no": "1", "clause_no": "0", "law_name": "법"},
        "b": {"content": "예전", "content_hash": hashContent("예전"), "article_no": "2", "clause_no": "0", "law_name": "법"},
        "gone": {"content": "삭제됨", "content_hash": hashContent("삭제됨"), "article_no": "9", "clause_no": "0", "law_name": "법"},
    }
    plan = planChanges([doc("a", "같음"), doc("b", "새로움"), doc("c", "추가")], existing)
    assert [d["_id"] for d in plan["toIndex"]] == ["b", "c"]
    assert plan["unchangedIds"] == ["a"]
    assert plan["removedIds"] == ["gone"]
    assert sorted(h["change_type"] for h in plan["history"]) == ["added", "modified", "removed"]


def test_planChanges_rerun_with_same_docs_changes_nothing():
    docs = [doc("a", "같음"), doc("b", "둘")]
    existing = {d["_id"]: dict(d["_source"]) for d in docs}
    plan = planChanges(docs, existing)
    assert plan["toIndex"] == [] and plan["removedIds"] == [] and plan["history"] == []
    assert plan["unchangedIds"] == ["a", "b"]
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_law_parse.py -v`
Expected: `ModuleNotFoundError: No module named 'law_parse'`

- [ ] **Step 4: `law_parse.py` 작성**

`scripts/collect/law_parse.py`:
```python
# -*- coding: utf-8 -*-
"""
law_parse.py
법제처 법령·행정규칙(고시) JSON을 OpenSearch food-law-articles 문서로 바꾸는 순수 함수 모음.
collect_law.py / collect_admrul.py 가 함께 사용한다. (네트워크·OpenSearch 접근 없음)

- parseClauses        : 법령 조문 → 항 단위 문서 (호·목 내용 이어붙임, 에스테틱 collect_law.py 방식)
- parseAnnexes        : 별표 → 1,200자 안팎으로 나눈 문서 (서식은 제외)
- parseAdmrulArticles : 고시 조문내용(줄 목록) → 조 단위 문서
- pickTarget          : 목록 조회 결과에서 수집 대상 하나 고르기
- planChanges         : 기존 문서와 비교해 추가·변경·유지·삭제 계획 세우기
"""

# ============================================================
# 라이브러리 임포트
# ============================================================

import hashlib
import re


# ============================================================
# 상수 정의
# ============================================================

INDEX_NAME   = "food-law-articles"
ANNEX_CHUNK  = 1200    # 별표 문서 하나의 최대 글자 수 (줄 단위로 자름)

_ARTICLE_HEAD_RE = re.compile(r"^\s*제(\d+)조(?:의(\d+))?\s*(?:\(([^)]*)\))?")
_CHAPTER_RE      = re.compile(r"^\s*제\d+(?:편|장|절|관)\s")
_NAME_STRIP_RE   = re.compile(r"[\s·ㆍ∙]")


# ============================================================
# 기본 유틸
# ============================================================

def asList(v):
    """API가 항목이 하나면 dict, 여러 개면 list로 주는 경우를 list로 통일."""
    if v is None or v == "":
        return []
    if isinstance(v, list):
        return v
    return [v]


def flattenText(v):
    """문자열·리스트·dict가 섞인 값을 빈 줄 없는 줄 목록으로 펼친다."""
    if v is None:
        return []
    if isinstance(v, str):
        return [line.rstrip() for line in v.split("\n") if line.strip()]
    if isinstance(v, list):
        out = []
        for x in v:
            out += flattenText(x)
        return out
    if isinstance(v, dict):
        out = []
        for x in v.values():
            out += flattenText(x)
        return out
    return [str(v)]


def chunkText(lines, maxLen=ANNEX_CHUNK):
    """줄을 자르지 않고 maxLen 안팎으로 묶는다. 한 줄이 maxLen보다 길면 그 줄만 한 덩어리."""
    chunks = []
    cur    = ""
    for line in lines:
        if cur and len(cur) + 1 + len(line) > maxLen:
            chunks.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        chunks.append(cur)
    return chunks


def hashContent(content):
    """content 문자열의 SHA-256 해시(hex). 재수집 시 변경 여부 비교용."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def parseDate(rawDate):
    """날짜를 yyyyMMdd로 정규화. 형식이 맞지 않으면 None."""
    cleaned = str(rawDate or "").strip().replace("-", "").replace(".", "")
    if len(cleaned) == 8 and cleaned.isdigit():
        return cleaned
    return None


def makeDoc(meta, docId, articleNo, clauseNo, title, content):
    """food-law-articles 문서 하나를 만든다."""
    info = meta["info"]
    return {
        "_index": INDEX_NAME,
        "_id":    docId,
        "_source": {
            "law_name":       info["name"],
            "law_id":         meta["lawId"],
            "source_key":     meta["sourceKey"],
            "kind":           info["kind"],
            "food_type":      info["food_type"],
            "article_no":     articleNo,
            "clause_no":      clauseNo,
            "title":          title,
            "content":        content,
            "content_hash":   hashContent(content),
            "effective_date": meta["effectiveDate"],
            "collected_at":   meta["collectedAt"],
        },
    }


# ============================================================
# 법령 조문
# ============================================================

def displayArticleNo(art):
    """조문번호 표시: 제3조의2 → "3의2"."""
    articleNo = str(art.get("조문번호", "")).strip()
    branchNo  = str(art.get("조문가지번호", "")).strip()
    return f"{articleNo}의{branchNo}" if branchNo else articleNo


def parseClauses(lawData, meta):
    """
    법령 JSON의 조문단위를 항 단위 문서로 만든다.
    - 조문여부가 "전문"(장·절 제목)인 항목은 건너뛴다.
    - 항이 없는 조문은 조문 전체를 문서 하나로(clause_no="0").
    - 항 아래 호·목 내용을 이어붙인다(안 하면 "다음 각 호" 도입부만 남아 근거로 못 씀).
    - meta.info.articles 가 있으면 그 조문번호만 남긴다.
    """
    articles = meta["info"].get("articles")
    docs     = []
    for art in asList(lawData.get("법령", {}).get("조문", {}).get("조문단위")):
        if str(art.get("조문여부", "")).strip() == "전문":
            continue
        displayNo = displayArticleNo(art)
        if articles is not None and displayNo not in articles:
            continue
        artKey  = str(art.get("조문키", "")).strip()
        title   = str(art.get("조문제목", "")).strip()
        clauses = asList(art.get("항"))

        if not clauses:
            body = "\n".join(flattenText(art.get("조문내용")))
            if not body:
                continue
            content = f"제{displayNo}조({title})\n{body}"
            docs.append(makeDoc(meta, f"{meta['sourceKey']}_{artKey}_0", displayNo, "0", title, content))
            continue

        for j, clause in enumerate(clauses, start=1):
            parts = flattenText(clause.get("항내용"))
            for item in asList(clause.get("호")):
                parts += flattenText(item.get("호내용"))
                for mok in asList(item.get("목")):
                    parts += flattenText(mok.get("목내용"))
            if not parts:
                continue
            content = f"제{displayNo}조({title}) {j}항\n" + "\n".join(parts)
            docs.append(makeDoc(meta, f"{meta['sourceKey']}_{artKey}_{j}", displayNo, str(j), title, content))
    return docs


# ============================================================
# 별표
# ============================================================

def annexNo(unit):
    """별표번호 표시: "0001"/"00" → "1", "0001"/"02" → "1의2", "000102" → "1의2"."""
    raw    = re.sub(r"\D", "", str(unit.get("별표번호", "")))
    branch = re.sub(r"\D", "", str(unit.get("별표가지번호", "")))
    if len(raw) == 6:
        raw, branch = raw[:4], (branch or raw[4:])
    number    = str(int(raw)) if raw else "0"
    branchNum = int(branch) if branch else 0
    return f"{number}의{branchNum}" if branchNum else number


def parseAnnexes(annexUnits, meta):
    """
    별표단위 목록을 문서로 만든다. 별표구분이 "서식"인 것은 뺀다.
    본문은 chunkText로 나눠 _id 끝에 _p1, _p2 ... 를 붙인다.
    meta.info.annexes 가 있으면 그 별표번호만 남긴다(빈 리스트면 하나도 넣지 않음).
    """
    wanted = meta["info"].get("annexes")
    docs   = []
    for unit in asList(annexUnits):
        if str(unit.get("별표구분", "별표")).strip() == "서식":
            continue
        number = annexNo(unit)
        if wanted is not None and number not in wanted:
            continue
        title = str(unit.get("별표제목", "")).strip()
        lines = flattenText(unit.get("별표내용"))
        if not lines:
            continue
        for p, chunk in enumerate(chunkText(lines), start=1):
            content = f"[별표 {number}] {title}\n{chunk}"
            docs.append(makeDoc(meta, f"{meta['sourceKey']}_annex{number}_p{p}",
                                f"별표 {number}", "0", title, content))
    return docs


# ============================================================
# 행정규칙(고시) 조문
# ============================================================

def parseAdmrulArticles(lines, meta):
    """
    고시 조문내용(줄 목록)을 "제n조(제목)" 머리줄 기준으로 묶어 조 단위 문서를 만든다.
    장·절 제목 줄은 건너뛰고, 같은 조번호가 다시 나오면(부칙 등) 처음 것만 남긴다.
    """
    articles = meta["info"].get("articles")
    groups   = []
    for line in lines:
        if _CHAPTER_RE.match(line):
            continue
        m = _ARTICLE_HEAD_RE.match(line)
        if m:
            number = f"{m.group(1)}의{m.group(2)}" if m.group(2) else m.group(1)
            groups.append({"no": number, "title": (m.group(3) or "").strip(), "lines": [line.strip()]})
        elif groups:
            groups[-1]["lines"].append(line.strip())

    docs = []
    seen = set()
    for g in groups:
        if g["no"] in seen:
            continue
        seen.add(g["no"])
        if articles is not None and g["no"] not in articles:
            continue
        content = "\n".join(g["lines"])
        docs.append(makeDoc(meta, f"{meta['sourceKey']}_{g['no']}", g["no"], "0", g["title"], content))
    return docs


# ============================================================
# 수집 대상 이름 매칭
# ============================================================

def normalizeName(s):
    """비교용 이름: 공백과 가운뎃점(·ㆍ∙) 제거."""
    return _NAME_STRIP_RE.sub("", str(s or ""))


def pickTarget(candidates, name, nameKey):
    """
    목록 조회 결과에서 이름이 같은 후보를 고른다.
    같은 이름이 없으면 이름을 포함하는 후보가 정확히 하나일 때만 고른다.
    고를 수 없으면 후보 이름을 담아 LookupError.
    """
    want  = normalizeName(name)
    cands = asList(candidates)
    exact = [c for c in cands if normalizeName(c.get(nameKey)) == want]
    if exact:
        return exact[0]
    partial = [c for c in cands if want in normalizeName(c.get(nameKey))]
    if len(partial) == 1:
        return partial[0]
    names = [c.get(nameKey) for c in cands]
    raise LookupError(f"'{name}' 수집 대상을 하나로 정할 수 없습니다. 후보: {names}")


# ============================================================
# 변경 계획
# ============================================================

def historyRow(src, changeType, oldContent, newContent):
    return {
        "source_key":  src.get("source_key"),
        "law_name":    src.get("law_name"),
        "article_no":  src.get("article_no"),
        "clause_no":   src.get("clause_no"),
        "change_type": changeType,
        "old_content": oldContent,
        "new_content": newContent,
    }


def planChanges(docs, existing):
    """
    docs     : 이번에 파싱한 문서 리스트
    existing : 같은 source_key로 이미 인덱스에 있는 문서 {_id: _source}
    반환     : toIndex(새로 넣을 문서), unchangedIds(그대로인 문서 id),
               removedIds(이번에 사라진 문서 id), history(law_history 로그 행)
    """
    toIndex   = []
    unchanged = []
    history   = []
    newIds    = set()
    for d in docs:
        newIds.add(d["_id"])
        src = d["_source"]
        old = existing.get(d["_id"])
        if old is None:
            toIndex.append(d)
            history.append(historyRow(src, "added", None, src["content"]))
        elif old.get("content_hash") != src["content_hash"]:
            toIndex.append(d)
            history.append(historyRow(src, "modified", old.get("content"), src["content"]))
        else:
            unchanged.append(d["_id"])

    removed = [docId for docId in existing if docId not in newIds]
    for docId in removed:
        old = dict(existing[docId])
        history.append(historyRow(old, "removed", old.get("content"), ""))
    return {"toIndex": toIndex, "unchangedIds": unchanged, "removedIds": removed, "history": history}
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_law_parse.py -v`
Expected: 18 passed.

- [ ] **Step 6: Commit**

```bash
git add scripts/collect/law_parse.py tests/test_law_parse.py tests/fixtures
git commit -m "법령·고시 JSON 파서와 변경 계획 함수 추가"
```

---

### Task 3: 법령·고시 수집 (`law_map`, `law_store`, `collect_law`, `collect_admrul`)

**Files:**
- Create: `scripts/collect/law_map.py`, `scripts/collect/law_store.py`, `scripts/collect/collect_law.py`, `scripts/collect/collect_admrul.py`, `tests/test_collect.py`
- Create (실행 결과): `data/law/law_<ID>.json` 8개, `data/law/admrul_<ID>.json` 2개, `data/law/resolved_ids.json`

**Interfaces:**
- Consumes: Task 1 `ROOT, loadConfig, retryGet, getOsClient, appendLog`; Task 2 전체
- Produces:
  - `law_map.LAW_TARGETS: list[dict]`, `law_map.ADMRUL_TARGETS: list[dict]` (키: `name, kind, food_type`, 선택 `articles, annexes`)
  - `law_store.ensureLawIndex(osClient)`, `law_store.storeDocs(osClient, sourceKey, docs, collectedAt) -> {"fetched","indexed","unchanged","removed"}`
  - `collect_law.buildLawDocs(lawData, lawId, info, collectedAt) -> list[doc]`
  - `collect_admrul.buildAdmrulDocs(admData, admId, info, collectedAt) -> list[doc]`
  - CLI: `python scripts/collect/collect_law.py [--offline] [--only 이름]`, `python scripts/collect/collect_admrul.py [--offline] [--only 이름]`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_collect.py`:
```python
import json
from pathlib import Path

from collect_admrul import buildAdmrulDocs
from collect_law import buildLawDocs
from law_map import ADMRUL_TARGETS, LAW_TARGETS

FIX = Path(__file__).parent / "fixtures"
KINDS = {"법률", "시행령", "시행규칙", "고시"}
FOOD_TYPES = {"공통", "일반식품", "건강기능식품"}


def test_targets_cover_checklist_1_to_10():
    assert len(LAW_TARGETS) == 8
    assert len(ADMRUL_TARGETS) == 2
    for t in LAW_TARGETS + ADMRUL_TARGETS:
        assert t["kind"] in KINDS and t["food_type"] in FOOD_TYPES and t["name"]


def test_food_sanitation_law_is_filtered():
    byName = {t["name"]: t for t in LAW_TARGETS}
    assert byName["식품위생법"]["food_type"] == "일반식품"
    assert byName["식품위생법"]["articles"]
    assert "articles" in byName["식품위생법 시행규칙"]


def test_buildLawDocs_combines_clauses_and_annexes():
    data = json.loads((FIX / "law_sample.json").read_text(encoding="utf-8"))
    info = {"name": "식품 등의 표시·광고에 관한 법률", "kind": "법률", "food_type": "공통"}
    docs = buildLawDocs(data, "100", info, "2026-10-16")
    assert len(docs) == 5
    assert docs[0]["_source"]["effective_date"] == "20250101"
    assert docs[-1]["_id"] == "law_100_annex1_p1"


def test_buildAdmrulDocs_combines_articles_and_annexes():
    data = json.loads((FIX / "admrul_sample.json").read_text(encoding="utf-8"))
    info = {"name": "부당한 표시 또는 광고의 내용 기준", "kind": "고시", "food_type": "공통"}
    docs = buildAdmrulDocs(data, "200", info, "2026-10-16")
    assert [d["_id"] for d in docs] == ["admrul_200_1", "admrul_200_2", "admrul_200_3의2", "admrul_200_annex1_p1"]
    assert docs[0]["_source"]["kind"] == "고시"
    assert docs[0]["_source"]["effective_date"] == "20240101"
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_collect.py -v`
Expected: `ModuleNotFoundError: No module named 'collect_admrul'`

- [ ] **Step 3: `law_map.py` 작성**

식품위생법은 영업자 준수사항(법 제44조)과 식품접객영업자 준수사항(시행규칙 제57조와 별표 17)만 넣는다. Step 8에서 원본을 보고 조문 번호를 확인한다.

`scripts/collect/law_map.py`:
```python
# -*- coding: utf-8 -*-
"""
law_map.py
수집 대상 표 (개요서 03장 체크리스트 1~10번).
법제처 ID는 이름으로 목록 조회해 자동으로 찾고 data/law/resolved_ids.json 에 저장한다.

키:
- name      : 법제처 현행 명칭 (목록 조회에 사용)
- kind      : 법률 / 시행령 / 시행규칙 / 고시
- food_type : 공통 / 일반식품 / 건강기능식품 (검색 필터)
- articles  : (선택) 넣을 조문 번호 목록. 없으면 전체
- annexes   : (선택) 넣을 별표 번호 목록. 없으면 전체, 빈 리스트면 별표 없음
"""

LAW_TARGETS = [
    {"name": "식품 등의 표시·광고에 관한 법률",          "kind": "법률",     "food_type": "공통"},
    {"name": "식품 등의 표시·광고에 관한 법률 시행령",   "kind": "시행령",   "food_type": "공통"},
    {"name": "식품 등의 표시·광고에 관한 법률 시행규칙", "kind": "시행규칙", "food_type": "공통"},
    {"name": "건강기능식품에 관한 법률",                 "kind": "법률",     "food_type": "건강기능식품"},
    {"name": "건강기능식품에 관한 법률 시행령",          "kind": "시행령",   "food_type": "건강기능식품"},
    {"name": "건강기능식품에 관한 법률 시행규칙",        "kind": "시행규칙", "food_type": "건강기능식품"},
    {"name": "식품위생법",          "kind": "법률",     "food_type": "일반식품", "articles": ["44"], "annexes": []},
    {"name": "식품위생법 시행규칙", "kind": "시행규칙", "food_type": "일반식품", "articles": ["57"], "annexes": ["17"]},
]

ADMRUL_TARGETS = [
    {"name": "부당한 표시 또는 광고의 내용 기준", "kind": "고시", "food_type": "공통"},
    {"name": "건강기능식품의 기준 및 규격",       "kind": "고시", "food_type": "건강기능식품"},
]
```

- [ ] **Step 4: `law_store.py` 작성**

`scripts/collect/law_store.py`:
```python
# -*- coding: utf-8 -*-
"""
law_store.py
food-law-articles 인덱스 생성·조회·변경 적용 (OpenSearch).
바뀐 문서만 다시 넣어 knn_vector를 보존하고, 그대로인 문서는 collected_at만 갱신한다.
"""

# ============================================================
# 라이브러리 임포트
# ============================================================

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from food_common import appendLog
from law_parse import INDEX_NAME, planChanges
from opensearchpy import NotFoundError, helpers


# ============================================================
# 인덱스 매핑
# ============================================================

MAPPING = {
    "settings": {
        "number_of_shards":   1,
        "number_of_replicas": 0,
        "index.knn":          True,
    },
    "mappings": {
        "properties": {
            "law_name":       {"type": "keyword"},
            "law_id":         {"type": "keyword"},
            "source_key":     {"type": "keyword"},
            "kind":           {"type": "keyword"},
            "food_type":      {"type": "keyword"},
            "article_no":     {"type": "keyword"},
            "clause_no":      {"type": "keyword"},
            "title":          {"type": "text", "analyzer": "standard"},
            "content":        {"type": "text", "analyzer": "standard"},
            "content_hash":   {"type": "keyword"},
            "effective_date": {"type": "date", "format": "yyyyMMdd||yyyy-MM-dd"},
            "collected_at":   {"type": "date", "format": "yyyy-MM-dd"},
            "knn_vector": {
                "type":      "knn_vector",
                "dimension": 1024,
                "method": {"name": "hnsw", "space_type": "cosinesimil", "engine": "lucene"},
            },
        }
    },
}


def ensureLawIndex(osClient):
    """food-law-articles 인덱스가 없으면 생성."""
    if not osClient.indices.exists(index=INDEX_NAME):
        osClient.indices.create(index=INDEX_NAME, body=MAPPING)
        print(f"[INFO] 인덱스 생성 완료: {INDEX_NAME}")


# ============================================================
# 조회 / 적용
# ============================================================

def fetchExisting(osClient, sourceKey):
    """같은 source_key 문서를 {_id: _source} 로 반환 (변경 비교에 필요한 필드만)."""
    resp = osClient.search(
        index=INDEX_NAME,
        body={
            "size":    10000,
            "_source": ["law_name", "source_key", "article_no", "clause_no", "content", "content_hash"],
            "query":   {"term": {"source_key": sourceKey}},
        },
    )
    return {hit["_id"]: hit["_source"] for hit in resp["hits"]["hits"]}


def applyChanges(osClient, plan, collectedAt):
    """변경 계획을 인덱스에 적용하고 이력을 기록. 반환: 새로 넣은 문서 수."""
    indexed = 0
    if plan["toIndex"]:
        indexed, errors = helpers.bulk(osClient, plan["toIndex"], raise_on_error=False)
        if errors:
            print(f"  [WARN] 인덱싱 오류 {len(errors)}건: {errors[0]}")
    if plan["unchangedIds"]:
        actions = [{"_op_type": "update", "_index": INDEX_NAME, "_id": docId,
                    "doc": {"collected_at": collectedAt}} for docId in plan["unchangedIds"]]
        helpers.bulk(osClient, actions, raise_on_error=False)
    for docId in plan["removedIds"]:
        try:
            osClient.delete(index=INDEX_NAME, id=docId)
        except NotFoundError:
            pass
    for row in plan["history"]:
        appendLog("law_history", row)
    osClient.indices.refresh(index=INDEX_NAME)
    return indexed


def storeDocs(osClient, sourceKey, docs, collectedAt):
    """한 법령의 문서를 기존 인덱스와 비교해 저장. 반환: 건수 요약."""
    plan    = planChanges(docs, fetchExisting(osClient, sourceKey))
    indexed = applyChanges(osClient, plan, collectedAt)
    return {
        "fetched":   len(docs),
        "indexed":   indexed,
        "unchanged": len(plan["unchangedIds"]),
        "removed":   len(plan["removedIds"]),
    }
```

- [ ] **Step 5: `collect_law.py` 작성**

`scripts/collect/collect_law.py`:
```python
# -*- coding: utf-8 -*-
"""
collect_law.py
법제처 API에서 법률·시행령·시행규칙 8개를 받아 food-law-articles 인덱스에 적재.
원본 JSON은 data/law/law_<법령ID>.json 에 저장하고, --offline 이면 API 대신 저장본을 읽는다.

사용법:
  python scripts/collect/collect_law.py                 # 8개 전체
  python scripts/collect/collect_law.py --only 식품위생법
  python scripts/collect/collect_law.py --offline       # 저장된 원본으로 다시 적재
"""

# ============================================================
# 라이브러리 임포트
# ============================================================

import argparse
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from food_common import ROOT, appendLog, getOsClient, loadConfig, retryGet
from law_map import LAW_TARGETS
from law_parse import parseAnnexes, parseClauses, parseDate, pickTarget
from law_store import ensureLawIndex, storeDocs


# ============================================================
# 상수 정의
# ============================================================

LAW_SEARCH_URL  = "https://www.law.go.kr/DRF/lawSearch.do"
LAW_SERVICE_URL = "https://www.law.go.kr/DRF/lawService.do"
RAW_DIR         = ROOT / "data" / "law"
ID_CACHE        = RAW_DIR / "resolved_ids.json"


# ============================================================
# 법령 ID 확인 (이름 → 법령ID)
# ============================================================

def loadIdCache():
    if ID_CACHE.exists():
        return json.loads(ID_CACHE.read_text(encoding="utf-8"))
    return {}


def saveIdCache(cache):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ID_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def resolveLawId(cfg, name, cache, offline):
    """법령명으로 목록 조회해 법령ID를 찾는다. 찾은 값은 cache에 저장."""
    key = f"law:{name}"
    if key in cache:
        return cache[key]
    if offline:
        raise LookupError(f"{name}: resolved_ids.json 에 ID가 없어 --offline 으로 진행할 수 없습니다.")
    params = {"OC": cfg['lawApiKey'], "target": "law", "type": "JSON", "query": name, "display": 100}
    found  = pickTarget(retryGet(LAW_SEARCH_URL, params).json().get("LawSearch", {}).get("law"),
                        name, "법령명한글")
    cache[key] = str(found["법령ID"])
    return cache[key]


# ============================================================
# 수집 / 문서화
# ============================================================

def fetchLaw(cfg, lawId, offline):
    """법령 본문 JSON. 온라인이면 받아서 저장, 오프라인이면 저장본을 읽는다."""
    path = RAW_DIR / f"law_{lawId}.json"
    if offline:
        return json.loads(path.read_text(encoding="utf-8"))
    params = {"OC": cfg['lawApiKey'], "target": "law", "ID": lawId, "type": "JSON"}
    data   = retryGet(LAW_SERVICE_URL, params).json()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def buildLawDocs(lawData, lawId, info, collectedAt):
    """법령 JSON → 조문(항 단위) 문서 + 별표 문서."""
    lawBlock = lawData.get("법령", {})
    meta = {
        "info":          info,
        "lawId":         lawId,
        "sourceKey":     f"law_{lawId}",
        "effectiveDate": parseDate(lawBlock.get("기본정보", {}).get("시행일자")),
        "collectedAt":   collectedAt,
    }
    annexBlock = lawBlock.get("별표")
    annexUnits = annexBlock.get("별표단위") if isinstance(annexBlock, dict) else annexBlock
    return parseClauses(lawData, meta) + parseAnnexes(annexUnits, meta)


def collectOne(cfg, osClient, info, cache, offline, collectedAt):
    """법령 하나 수집 → 문서화 → 저장 → collect 로그."""
    name = info["name"]
    print(f"\n[{name}] 수집 시작")
    try:
        lawId   = resolveLawId(cfg, name, cache, offline)
        docs    = buildLawDocs(fetchLaw(cfg, lawId, offline), lawId, info, collectedAt)
        if not docs:
            raise ValueError("파싱된 조문 없음 - data/law 원본의 응답 구조 확인 필요")
        summary = storeDocs(osClient, f"law_{lawId}", docs, collectedAt)
        appendLog("collect", {"source": f"law_{lawId}", "name": name, "status": "success", **summary})
        print(f"  {summary}")
    except Exception as e:
        appendLog("collect", {"source": name, "name": name, "status": "failed", "error": str(e)})
        print({"success": False, "message": f"{name} 수집 실패: {e}"})


# ============================================================
# 메인
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="법제처 법령 수집 → food-law-articles")
    parser.add_argument("--offline", action="store_true", help="API 대신 data/law 저장본 사용")
    parser.add_argument("--only",    default=None,        help="이 이름의 법령만 수집")
    args = parser.parse_args()

    cfg = loadConfig()
    if not args.offline and not cfg['lawApiKey']:
        print({"success": False, "message": ".env에 LAW_OC 가 없습니다."})
        sys.exit(1)

    osClient = getOsClient(cfg)
    ensureLawIndex(osClient)
    cache       = loadIdCache()
    collectedAt = date.today().isoformat()
    targets     = [t for t in LAW_TARGETS if args.only in (None, t["name"])]
    for info in targets:
        collectOne(cfg, osClient, info, cache, args.offline, collectedAt)
    saveIdCache(cache)
    print("\n[완료] 결과는 logs/collect.jsonl 참고")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: `collect_admrul.py` 작성**

`scripts/collect/collect_admrul.py`:
```python
# -*- coding: utf-8 -*-
"""
collect_admrul.py
법제처 API에서 식약처 고시 2개(행정규칙)를 받아 food-law-articles 인덱스에 적재.
원본 JSON은 data/law/admrul_<행정규칙일련번호>.json 에 저장.

사용법:
  python scripts/collect/collect_admrul.py
  python scripts/collect/collect_admrul.py --only "건강기능식품의 기준 및 규격"
  python scripts/collect/collect_admrul.py --offline
"""

# ============================================================
# 라이브러리 임포트
# ============================================================

import argparse
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from collect_law import LAW_SEARCH_URL, LAW_SERVICE_URL, RAW_DIR, loadIdCache, saveIdCache
from food_common import appendLog, getOsClient, loadConfig, retryGet
from law_map import ADMRUL_TARGETS
from law_parse import flattenText, parseAdmrulArticles, parseAnnexes, parseDate, pickTarget
from law_store import ensureLawIndex, storeDocs


# ============================================================
# 행정규칙 ID 확인 / 수집
# ============================================================

def resolveAdmrulId(cfg, name, cache, offline):
    """행정규칙명으로 목록 조회해 행정규칙일련번호를 찾는다."""
    key = f"admrul:{name}"
    if key in cache:
        return cache[key]
    if offline:
        raise LookupError(f"{name}: resolved_ids.json 에 ID가 없어 --offline 으로 진행할 수 없습니다.")
    params = {"OC": cfg['lawApiKey'], "target": "admrul", "type": "JSON", "query": name, "display": 100}
    found  = pickTarget(retryGet(LAW_SEARCH_URL, params).json().get("AdmRulSearch", {}).get("admrul"),
                        name, "행정규칙명")
    cache[key] = str(found["행정규칙일련번호"])
    return cache[key]


def fetchAdmrul(cfg, admId, offline):
    path = RAW_DIR / f"admrul_{admId}.json"
    if offline:
        return json.loads(path.read_text(encoding="utf-8"))
    params = {"OC": cfg['lawApiKey'], "target": "admrul", "ID": admId, "type": "JSON"}
    data   = retryGet(LAW_SERVICE_URL, params).json()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def buildAdmrulDocs(admData, admId, info, collectedAt):
    """고시 JSON → 조 단위 문서 + 별표 문서."""
    body = admData.get("AdmRulService", admData)
    meta = {
        "info":          info,
        "lawId":         admId,
        "sourceKey":     f"admrul_{admId}",
        "effectiveDate": parseDate(body.get("행정규칙기본정보", {}).get("시행일자")),
        "collectedAt":   collectedAt,
    }
    annexBlock = body.get("별표")
    annexUnits = annexBlock.get("별표단위") if isinstance(annexBlock, dict) else annexBlock
    return parseAdmrulArticles(flattenText(body.get("조문내용")), meta) + parseAnnexes(annexUnits, meta)


def collectOne(cfg, osClient, info, cache, offline, collectedAt):
    name = info["name"]
    print(f"\n[{name}] 수집 시작")
    try:
        admId   = resolveAdmrulId(cfg, name, cache, offline)
        docs    = buildAdmrulDocs(fetchAdmrul(cfg, admId, offline), admId, info, collectedAt)
        if not docs:
            raise ValueError("파싱된 조문 없음 - data/law 원본의 응답 구조 확인 필요")
        summary = storeDocs(osClient, f"admrul_{admId}", docs, collectedAt)
        appendLog("collect", {"source": f"admrul_{admId}", "name": name, "status": "success", **summary})
        print(f"  {summary}")
    except Exception as e:
        appendLog("collect", {"source": name, "name": name, "status": "failed", "error": str(e)})
        print({"success": False, "message": f"{name} 수집 실패: {e}"})


# ============================================================
# 메인
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="법제처 행정규칙(고시) 수집 → food-law-articles")
    parser.add_argument("--offline", action="store_true", help="API 대신 data/law 저장본 사용")
    parser.add_argument("--only",    default=None,        help="이 이름의 고시만 수집")
    args = parser.parse_args()

    cfg = loadConfig()
    if not args.offline and not cfg['lawApiKey']:
        print({"success": False, "message": ".env에 LAW_OC 가 없습니다."})
        sys.exit(1)

    osClient = getOsClient(cfg)
    ensureLawIndex(osClient)
    cache       = loadIdCache()
    collectedAt = date.today().isoformat()
    for info in [t for t in ADMRUL_TARGETS if args.only in (None, t["name"])]:
        collectOne(cfg, osClient, info, cache, args.offline, collectedAt)
    saveIdCache(cache)
    print("\n[완료] 결과는 logs/collect.jsonl 참고")


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: 단위 테스트 통과 확인**

Run: `python -m pytest tests/test_collect.py tests/test_law_parse.py -v`
Expected: 22 passed.

- [ ] **Step 8: 실제 API로 수집하고 응답 구조 확인** (`.env`의 `LAW_OC`, OpenSearch 필요)

Run: `python scripts/collect/collect_law.py`
Expected: 법령마다 `{'fetched': N, 'indexed': N, 'unchanged': 0, 'removed': 0}`(N>0) 출력, `data/law/law_*.json` 8개 생성.

Run: `python scripts/collect/collect_admrul.py`
Expected: 고시마다 요약 출력, `data/law/admrul_*.json` 2개 생성.

한 건이라도 `수집 실패`가 나오면 원본 구조를 확인한다:
```bash
python -X utf8 -c "import json,glob; [print(p, list(json.load(open(p,encoding='utf-8')).keys()), list(next(iter(json.load(open(p,encoding='utf-8')).values())).keys())[:15]) for p in sorted(glob.glob('data/law/*.json')) if 'resolved' not in p]"
```
- `LookupError ... 후보: [...]`이면 `law_map.py`의 `name`을 후보 중 정확한 명칭으로 고친다.
- 키 이름이 Task 2 fixture와 다르면(예: 별표가 `별표` 아래 다른 키) 실제 원본에서 해당 부분을 잘라 `tests/fixtures/*.json`을 실제 구조로 바꾸고, 테스트가 다시 통과하도록 `law_parse.py`/`buildAdmrulDocs`를 고친다.
- 식품위생법: 아래 명령으로 조문 제목 목록을 보고 `articles`가 영업자 준수사항 조문을 가리키는지 확인한다.
```bash
python -X utf8 -c "
import json,sys; sys.path.insert(0,'scripts/collect')
from law_parse import asList, displayArticleNo
ids=json.load(open('data/law/resolved_ids.json',encoding='utf-8'))
for name in ['식품위생법','식품위생법 시행규칙']:
    d=json.load(open(f\"data/law/law_{ids['law:'+name]}.json\",encoding='utf-8'))
    print(name,[(displayArticleNo(a),a.get('조문제목')) for a in asList(d['법령']['조문']['조문단위']) if '준수' in str(a.get('조문제목'))])
"
```
Expected: 식품위생법 `('44', '영업자 등의 준수사항')`, 시행규칙 `('57', ...준수사항...)`. 번호가 다르면 `law_map.py`를 실제 번호로 고친다.

- [ ] **Step 9: 문서 수 확인과 재실행 확인**

Run: `curl -sk -u "$OS_USER:$OS_PASSWORD" "https://localhost:9200/food-law-articles/_count"` (PowerShell이면 `.env` 값을 직접 넣는다)
Expected: `{"count": N, ...}` N>0

Run: `python scripts/collect/collect_law.py --offline`
Expected: 모든 법령이 `'indexed': 0, 'unchanged': N, 'removed': 0` (두 번 실행해도 중복·삭제 없음).

- [ ] **Step 10: Commit**

```bash
git add scripts/collect/law_map.py scripts/collect/law_store.py scripts/collect/collect_law.py scripts/collect/collect_admrul.py tests data/law
git commit -m "법제처 법령 8개·고시 2개 수집과 food-law-articles 적재"
```

---

### Task 4: 식약처 인정 기능성 적재 (`index_materials.py`)

**Files:**
- Create: `scripts/collect/index_materials.py`, `tests/test_index_materials.py`

**Interfaces:**
- Consumes: Task 1 `ROOT, loadConfig, getOsClient, appendLog`; `data/foodsafety/materials.jsonl`, `data/foodsafety/COLLECTED_AT`
- Produces: `MATERIAL_INDEX = "food-materials"`, `loadMaterials(path) -> list[dict]`, `buildActions(materials, collectedAt) -> list[dict]`, `selectChanged(actions, existingTextById) -> list[dict]`; CLI `python scripts/collect/index_materials.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_index_materials.py`:
```python
from pathlib import Path

from index_materials import MATERIAL_INDEX, buildActions, loadMaterials, selectChanged

ROOT = Path(__file__).resolve().parents[1]


def test_loadMaterials_reads_all_731():
    mats = loadMaterials(ROOT / "data" / "foodsafety" / "materials.jsonl")
    assert len(mats) == 731
    assert any(m["_id"] == "2024-20" and m["material"] == "홍삼" for m in mats)


def test_buildActions_moves_id_out_of_source_and_adds_date():
    mats = [{"_id": "2024-20", "material": "홍삼", "claims": ["혈당 조절에 도움을 줄 수 있음"], "text": "t"}]
    action = buildActions(mats, "2026-10-15")[0]
    assert action["_index"] == MATERIAL_INDEX and action["_id"] == "2024-20"
    assert "_id" not in action["_source"]
    assert action["_source"]["collected_at"] == "2026-10-15"
    assert action["_source"]["claims"] == ["혈당 조절에 도움을 줄 수 있음"]


def test_selectChanged_skips_docs_with_same_text():
    actions = buildActions([{"_id": "a", "text": "같음"}, {"_id": "b", "text": "새것"}, {"_id": "c", "text": "추가"}],
                           "2026-10-15")
    changed = selectChanged(actions, {"a": "같음", "b": "옛것"})
    assert [a["_id"] for a in changed] == ["b", "c"]
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_index_materials.py -v`
Expected: `ModuleNotFoundError: No module named 'index_materials'`

- [ ] **Step 3: `index_materials.py` 작성**

`scripts/collect/index_materials.py`:
```python
# -*- coding: utf-8 -*-
"""
index_materials.py
식약처 건강기능식품 인정 기능성(materials.jsonl, 731건)을 food-materials 인덱스에 적재.
text가 바뀐 문서만 다시 넣어 knn_vector를 보존한다.
수집 기준일은 data/foodsafety/COLLECTED_AT 파일 값(식품안전나라 원본 수집일)을 쓴다.

사용법:
  python scripts/collect/index_materials.py
"""

# ============================================================
# 라이브러리 임포트
# ============================================================

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from food_common import ROOT, appendLog, getOsClient, loadConfig
from opensearchpy import helpers


# ============================================================
# 상수 정의
# ============================================================

MATERIAL_INDEX = "food-materials"
DATA_DIR       = ROOT / "data" / "foodsafety"
MATERIALS_PATH = DATA_DIR / "materials.jsonl"
COLLECTED_PATH = DATA_DIR / "COLLECTED_AT"
MGET_BATCH     = 500

MAPPING = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0, "index.knn": True},
    "mappings": {
        "properties": {
            "material":     {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "claims":       {"type": "text"},
            "daily_intake": {"type": "text"},
            "caution":      {"type": "text"},
            "approved":     {"type": "keyword"},
            "text":         {"type": "text", "analyzer": "standard"},
            "source":       {"type": "keyword"},
            "sector":       {"type": "keyword"},
            "datasets":     {"type": "keyword"},
            "collected_at": {"type": "date", "format": "yyyy-MM-dd"},
            "knn_vector": {
                "type":      "knn_vector",
                "dimension": 1024,
                "method": {"name": "hnsw", "space_type": "cosinesimil", "engine": "lucene"},
            },
        }
    },
}


# ============================================================
# 문서 만들기
# ============================================================

def loadMaterials(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def buildActions(materials, collectedAt):
    """materials.jsonl 행 → bulk 액션. _id 는 인정번호."""
    actions = []
    for m in materials:
        src = {k: v for k, v in m.items() if k != "_id"}
        src["collected_at"] = collectedAt
        actions.append({"_index": MATERIAL_INDEX, "_id": m["_id"], "_source": src})
    return actions


def selectChanged(actions, existingTextById):
    """인덱스에 없거나 text가 달라진 문서만 고른다."""
    return [a for a in actions if existingTextById.get(a["_id"]) != a["_source"].get("text")]


# ============================================================
# OpenSearch
# ============================================================

def ensureMaterialIndex(osClient):
    if not osClient.indices.exists(index=MATERIAL_INDEX):
        osClient.indices.create(index=MATERIAL_INDEX, body=MAPPING)
        print(f"[INFO] 인덱스 생성 완료: {MATERIAL_INDEX}")


def fetchExistingText(osClient, ids):
    found = {}
    for i in range(0, len(ids), MGET_BATCH):
        resp = osClient.mget(index=MATERIAL_INDEX, body={"ids": ids[i:i + MGET_BATCH]}, _source=["text"])
        for doc in resp.get("docs", []):
            if doc.get("found"):
                found[doc["_id"]] = doc["_source"].get("text")
    return found


# ============================================================
# 메인
# ============================================================

def main():
    cfg         = loadConfig()
    osClient    = getOsClient(cfg)
    collectedAt = COLLECTED_PATH.read_text(encoding="utf-8").strip()

    ensureMaterialIndex(osClient)
    actions = buildActions(loadMaterials(MATERIALS_PATH), collectedAt)
    changed = selectChanged(actions, fetchExistingText(osClient, [a["_id"] for a in actions]))
    indexed = 0
    if changed:
        indexed, errors = helpers.bulk(osClient, changed, raise_on_error=False)
        if errors:
            print(f"  [WARN] 인덱싱 오류 {len(errors)}건: {errors[0]}")
    osClient.indices.refresh(index=MATERIAL_INDEX)
    summary = {"fetched": len(actions), "indexed": indexed, "unchanged": len(actions) - len(changed)}
    appendLog("collect", {"source": "foodsafety_materials", "name": MATERIAL_INDEX, "status": "success", **summary})
    print(f"[완료] {summary}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_index_materials.py -v`
Expected: 3 passed.

- [ ] **Step 5: 실제 적재와 재실행 확인** (OpenSearch 필요)

Run: `python scripts/collect/index_materials.py`
Expected: `[완료] {'fetched': 731, 'indexed': 731, 'unchanged': 0}`
Run: `python scripts/collect/index_materials.py`
Expected: `[완료] {'fetched': 731, 'indexed': 0, 'unchanged': 731}`

- [ ] **Step 6: Commit**

```bash
git add scripts/collect/index_materials.py tests/test_index_materials.py
git commit -m "식약처 인정 기능성 food-materials 인덱스 적재"
```

---

### Task 5: 임베딩 (`embed_index.py`)

**Files:**
- Create: `scripts/rag/embed_index.py`, `tests/test_embed_index.py`

**Interfaces:**
- Consumes: Task 1 `loadConfig, getOsClient`
- Produces: `EMBED_FIELD = {"food-law-articles": "content", "food-materials": "text"}`, `embedFieldFor(indexName) -> str`(모르는 인덱스면 `ValueError`), `getEmbedding(ollamaHost, model, textList) -> list[list[float]]`; CLI `python scripts/rag/embed_index.py [--index food-law-articles|food-materials|all]`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_embed_index.py`:
```python
import pytest

from embed_index import EMBED_FIELD, embedFieldFor


def test_embed_field_per_index():
    assert embedFieldFor("food-law-articles") == "content"
    assert embedFieldFor("food-materials") == "text"
    assert set(EMBED_FIELD) == {"food-law-articles", "food-materials"}


def test_embed_field_rejects_unknown_index():
    with pytest.raises(ValueError):
        embedFieldFor("law-articles")
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_embed_index.py -v`
Expected: `ModuleNotFoundError: No module named 'embed_index'`

- [ ] **Step 3: `embed_index.py` 작성**

`scripts/rag/embed_index.py`:
```python
# -*- coding: utf-8 -*-
"""
embed_index.py
OpenSearch 문서의 본문 필드를 BGE-M3로 임베딩해 knn_vector 필드를 채운다.
knn_vector가 없는 문서만 대상이라, 바뀐 문서만 다시 임베딩된다.

대상 인덱스와 필드:
- food-law-articles : content
- food-materials    : text

사용법:
  python scripts/rag/embed_index.py                         # 두 인덱스 모두
  python scripts/rag/embed_index.py --index food-materials  # 하나만
"""

# ============================================================
# 라이브러리 임포트
# ============================================================

import argparse
import os
import sys
import time

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from food_common import getOsClient, loadConfig


# ============================================================
# 상수 정의
# ============================================================

EMBED_API_PATH = "/api/embed"
BATCH_SIZE     = 16
SCROLL_SIZE    = 200
SCROLL_TTL     = "5m"
EMBED_FIELD    = {"food-law-articles": "content", "food-materials": "text"}


def embedFieldFor(indexName):
    if indexName not in EMBED_FIELD:
        raise ValueError(f"임베딩 대상이 아닌 인덱스: {indexName}")
    return EMBED_FIELD[indexName]


# ============================================================
# Ollama 임베딩 생성
# ============================================================

def getEmbedding(ollamaHost, model, textList, maxRetry=5, sleepSec=2):
    """Ollama embed API로 텍스트 리스트의 임베딩 벡터를 생성."""
    url     = ollamaHost.rstrip("/") + EMBED_API_PATH
    payload = {"model": model, "input": textList}
    lastErr = None
    for attempt in range(0, maxRetry):
        try:
            resp = requests.post(url, json=payload, timeout=120)
            resp.raise_for_status()
            return resp.json().get("embeddings", [])
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            lastErr = e
            if attempt < maxRetry - 1:
                waitSec = sleepSec * (attempt + 1)
                print(f"  [retry {attempt+1}/{maxRetry}] Ollama 연결 실패, {waitSec}s 대기")
                time.sleep(waitSec)
    raise lastErr or RuntimeError("Ollama 임베딩 최대 재시도 초과")


# ============================================================
# OpenSearch scroll / 업데이트
# ============================================================

def scrollDocs(osClient, indexName, field):
    """knn_vector가 없는 문서를 (_id, 본문) 으로 순회."""
    query = {
        "query":   {"bool": {"must_not": [{"exists": {"field": "knn_vector"}}]}},
        "_source": [field],
        "size":    SCROLL_SIZE,
    }
    resp     = osClient.search(index=indexName, body=query, scroll=SCROLL_TTL)
    scrollId = resp["_scroll_id"]
    hits     = resp["hits"]["hits"]
    while hits:
        for hit in hits:
            yield hit["_id"], hit["_source"].get(field, "")
        resp     = osClient.scroll(scroll_id=scrollId, scroll=SCROLL_TTL)
        scrollId = resp["_scroll_id"]
        hits     = resp["hits"]["hits"]
    try:
        osClient.clear_scroll(scroll_id=scrollId)
    except Exception:
        pass


def bulkUpdateVectors(osClient, indexName, idList, vectorList):
    """bulk API로 knn_vector 필드 일괄 업데이트. 반환: 성공 건수."""
    bodyLines = []
    for i in range(0, len(idList)):
        bodyLines.append({"update": {"_index": indexName, "_id": idList[i]}})
        bodyLines.append({"doc": {"knn_vector": vectorList[i]}})
    result = osClient.bulk(body=bodyLines, refresh=False)
    return sum(1 for item in result.get("items", []) if item.get("update", {}).get("status") in (200, 201))


def embedIndex(cfg, osClient, indexName):
    """한 인덱스의 임베딩 생성 및 업데이트. 반환: 성공 건수."""
    field = embedFieldFor(indexName)
    print(f"\n[{indexName}] 임베딩 시작 (field={field}, model={cfg['embedModel']}, batch={BATCH_SIZE})")
    # scroll 도중 문서를 고치면 결과가 흔들리므로 대상 목록을 먼저 다 모은다
    pending = list(scrollDocs(osClient, indexName, field))
    total   = 0
    for i in range(0, len(pending), BATCH_SIZE):
        batch = pending[i:i + BATCH_SIZE]
        try:
            vectors = getEmbedding(cfg['ollamaHost'], cfg['embedModel'], [text for _, text in batch])
        except Exception as e:
            print({"success": False, "message": f"임베딩 생성 실패 (건너뜀): {e}"})
            continue
        total += bulkUpdateVectors(osClient, indexName, [docId for docId, _ in batch], vectors)
        print(f"  [{min(i + BATCH_SIZE, len(pending))}/{len(pending)}건 처리]")
    osClient.indices.refresh(index=indexName)
    return total


# ============================================================
# 메인
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="BGE-M3 임베딩 생성 → knn_vector 업데이트")
    parser.add_argument("--index", default="all", choices=["all", *EMBED_FIELD.keys()])
    args = parser.parse_args()

    cfg      = loadConfig()
    osClient = getOsClient(cfg)
    try:
        requests.get(cfg['ollamaHost'].rstrip("/") + "/api/tags", timeout=5).raise_for_status()
    except Exception as e:
        print({"success": False, "message": f"Ollama 연결 실패: {e}"})
        sys.exit(1)

    targets = list(EMBED_FIELD) if args.index == "all" else [args.index]
    for indexName in targets:
        print(f"[완료] {indexName}: knn_vector {embedIndex(cfg, osClient, indexName)}건 업데이트")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_embed_index.py -v`
Expected: 2 passed.

- [ ] **Step 5: 실제 임베딩** (OpenSearch, Ollama `bge-m3` 필요)

Run: `python scripts/rag/embed_index.py`
Expected: 두 인덱스 모두 `[완료] ...: knn_vector N건 업데이트`. 다시 실행하면 둘 다 `0건`.

- [ ] **Step 6: Commit**

```bash
git add scripts/rag/embed_index.py tests/test_embed_index.py
git commit -m "두 인덱스 BGE-M3 임베딩 스크립트 추가"
```

---

### Task 6: 하이브리드 검색 (`search_hybrid.py`)

**Files:**
- Create: `scripts/rag/search_hybrid.py`, `tests/test_search_hybrid.py`

**Interfaces:**
- Consumes: Task 1 `FOOD_TYPE_MAP, COMMON, loadConfig, getOsClient`
- Produces:
  - `LAW_INDEX = "food-law-articles"`, `MATERIAL_INDEX = "food-materials"`, `PIPELINE_ID = "food-hybrid-pipeline"`, `MODES = ("bm25", "knn", "hybrid")`
  - `ensurePipeline(osClient)`, `embedQuery(cfg, queryText) -> list[float]`
  - `buildLawQuery(queryText, queryVector, foodType, topK, mode) -> dict`, `buildMaterialQuery(queryText, queryVector, topK) -> dict`
  - `toLawHit(hit, rank) -> dict` 키: `rank, score, doc_id, law_name, kind, food_type, article_no, clause_no, title, content, effective_date, collected_at`
  - `toMaterialHit(hit, rank) -> dict` 키: `rank, score, recog_no, material, claims(list), daily_intake, caution, collected_at`
  - `searchLaw(osClient, cfg, queryText, foodType, topK=5, mode="hybrid", queryVector=None) -> list[LawHit]`
  - `searchMaterials(osClient, cfg, queryText, topK=3, queryVector=None) -> list[MaterialHit]`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_search_hybrid.py`:
```python
import pytest

from search_hybrid import (buildLawQuery, buildMaterialQuery, searchLaw, searchMaterials, toLawHit,
                           toMaterialHit)

VEC = [0.1, 0.2]
FILTER = {"terms": {"food_type": ["일반식품", "공통"]}}


def test_bm25_query_filters_food_type_and_common():
    body = buildLawQuery("혈당 관리", None, "general", 5, "bm25")
    assert body["size"] == 5
    assert body["query"]["bool"]["filter"] == [FILTER]
    assert body["query"]["bool"]["must"][0]["match"]["content"]["query"] == "혈당 관리"
    assert "knn_vector" not in body["_source"]


def test_knn_query_uses_vector_and_filter():
    body = buildLawQuery("혈당 관리", VEC, "health", 5, "knn")
    knn = body["query"]["knn"]["knn_vector"]
    assert knn["vector"] == VEC and knn["k"] == 5
    assert knn["filter"] == {"terms": {"food_type": ["건강기능식품", "공통"]}}


def test_hybrid_query_combines_bm25_and_knn():
    body = buildLawQuery("혈당 관리", VEC, "general", 5, "hybrid")
    bm25, knn = body["query"]["hybrid"]["queries"]
    assert bm25["bool"]["filter"] == [FILTER]
    assert knn["knn"]["knn_vector"]["k"] == 10


def test_buildLawQuery_rejects_bad_mode_and_food_type():
    with pytest.raises(ValueError):
        buildLawQuery("q", VEC, "general", 5, "fuzzy")
    with pytest.raises(ValueError):
        buildLawQuery("q", VEC, "cosmetic", 5, "hybrid")


def test_material_query_is_hybrid_on_text():
    body = buildMaterialQuery("혈당", VEC, 3)
    bm25, knn = body["query"]["hybrid"]["queries"]
    assert bm25["match"]["text"]["query"] == "혈당"
    assert knn["knn"]["knn_vector"]["k"] == 6


def test_hit_converters():
    lawHit = toLawHit({"_id": "law_1_0008001_1", "_score": 0.87654,
                       "_source": {"law_name": "법", "article_no": "8", "clause_no": "1", "content": "본문",
                                   "collected_at": "2026-10-16"}}, 1)
    assert lawHit["doc_id"] == "law_1_0008001_1" and lawHit["score"] == 0.8765 and lawHit["rank"] == 1
    assert lawHit["title"] == "" and lawHit["collected_at"] == "2026-10-16"
    mat = toMaterialHit({"_id": "2024-20", "_score": 1.0, "_source": {"material": "홍삼",
                         "claims": ["혈당 조절에 도움을 줄 수 있음"]}}, 1)
    assert mat["recog_no"] == "2024-20" and mat["claims"] == ["혈당 조절에 도움을 줄 수 있음"]


class FakeOs:
    def __init__(self):
        self.calls = []

    def search(self, index, body, params=None):
        self.calls.append({"index": index, "body": body, "params": params or {}})
        return {"hits": {"hits": [{"_id": "x", "_score": 1.0, "_source": {"law_name": "법", "material": "홍삼"}}]}}


def test_searchLaw_bm25_does_not_embed_or_use_pipeline(monkeypatch):
    import search_hybrid
    monkeypatch.setattr(search_hybrid, "embedQuery", lambda cfg, q: pytest.fail("embed called"))
    fake = FakeOs()
    hits = searchLaw(fake, {}, "혈당", "general", topK=5, mode="bm25")
    assert len(hits) == 1 and fake.calls[0]["index"] == "food-law-articles"
    assert fake.calls[0]["params"] == {}


def test_searchLaw_hybrid_uses_pipeline_and_given_vector(monkeypatch):
    import search_hybrid
    monkeypatch.setattr(search_hybrid, "embedQuery", lambda cfg, q: pytest.fail("embed called"))
    fake = FakeOs()
    searchLaw(fake, {}, "혈당", "general", queryVector=VEC)
    assert fake.calls[0]["params"] == {"search_pipeline": "food-hybrid-pipeline"}


def test_searchMaterials_targets_material_index():
    fake = FakeOs()
    hits = searchMaterials(fake, {}, "혈당", queryVector=VEC)
    assert fake.calls[0]["index"] == "food-materials" and hits[0]["recog_no"] == "x"
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_search_hybrid.py -v`
Expected: `ModuleNotFoundError: No module named 'search_hybrid'`

- [ ] **Step 3: `search_hybrid.py` 작성**

`scripts/rag/search_hybrid.py`:
```python
# -*- coding: utf-8 -*-
"""
search_hybrid.py
BM25 + kNN 하이브리드 검색 (OpenSearch neural-search hybrid 쿼리 + normalization-processor).

- searchLaw       : food-law-articles 검색. 선택한 식품 종류 + 공통 법령만. 평가용 mode(bm25/knn/hybrid)
- searchMaterials : food-materials(식약처 인정 기능성) 검색

사용법 (CLI 테스트):
  python scripts/rag/search_hybrid.py "혈당 관리 샐러드" --food-type general
  python scripts/rag/search_hybrid.py "혈당 조절" --food-type health --materials
"""

# ============================================================
# 라이브러리 임포트
# ============================================================

import argparse
import os
import sys

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from food_common import COMMON, FOOD_TYPE_MAP, getOsClient, loadConfig


# ============================================================
# 상수 정의
# ============================================================

LAW_INDEX       = "food-law-articles"
MATERIAL_INDEX  = "food-materials"
PIPELINE_ID     = "food-hybrid-pipeline"
EMBED_API_PATH  = "/api/embed"
MODES           = ("bm25", "knn", "hybrid")
WEIGHT_BM25     = 0.3
WEIGHT_KNN      = 0.7
LAW_SOURCE      = ["law_name", "kind", "food_type", "article_no", "clause_no", "title",
                   "content", "effective_date", "collected_at"]
MATERIAL_SOURCE = ["material", "claims", "daily_intake", "caution", "collected_at"]


# ============================================================
# 검색 파이프라인 / 임베딩
# ============================================================

def ensurePipeline(osClient):
    """BM25(0.3)와 kNN(0.7) 점수를 min_max 정규화 후 가중 평균하는 파이프라인 생성."""
    try:
        osClient.transport.perform_request("GET", f"/_search/pipeline/{PIPELINE_ID}")
        return
    except Exception:
        pass
    pipeline = {
        "description": "식품 표시·광고 하이브리드 검색 파이프라인",
        "phase_results_processors": [{
            "normalization-processor": {
                "normalization": {"technique": "min_max"},
                "combination":   {"technique": "arithmetic_mean",
                                  "parameters": {"weights": [WEIGHT_BM25, WEIGHT_KNN]}},
            }
        }],
    }
    osClient.transport.perform_request("PUT", f"/_search/pipeline/{PIPELINE_ID}", body=pipeline)
    print(f"[INFO] 검색 파이프라인 생성: {PIPELINE_ID}")


def embedQuery(cfg, queryText):
    """Ollama BGE-M3 로 질의 임베딩."""
    url  = cfg['ollamaHost'].rstrip("/") + EMBED_API_PATH
    resp = requests.post(url, json={"model": cfg['embedModel'], "input": [queryText]}, timeout=30)
    resp.raise_for_status()
    embeddings = resp.json().get("embeddings", [])
    if not embeddings:
        raise ValueError("Ollama 임베딩 응답이 비어 있습니다.")
    return embeddings[0]


# ============================================================
# 쿼리 만들기
# ============================================================

def lawFilter(foodType):
    if foodType not in FOOD_TYPE_MAP:
        raise ValueError(f"알 수 없는 food_type: {foodType}")
    return {"terms": {"food_type": [FOOD_TYPE_MAP[foodType], COMMON]}}


def buildLawQuery(queryText, queryVector, foodType, topK, mode):
    """mode: bm25 / knn / hybrid. 세 방식 모두 같은 식품 종류 필터를 쓴다."""
    if mode not in MODES:
        raise ValueError(f"알 수 없는 검색 방식: {mode}")
    flt  = lawFilter(foodType)
    bm25 = {"bool": {"must": [{"match": {"content": {"query": queryText}}}], "filter": [flt]}}
    if mode == "bm25":
        query = bm25
    else:
        k   = topK * 2 if mode == "hybrid" else topK    # 하이브리드는 후보를 넉넉히 받아 재정렬
        knn = {"knn": {"knn_vector": {"vector": queryVector, "k": k, "filter": flt}}}
        query = knn if mode == "knn" else {"hybrid": {"queries": [bm25, knn]}}
    return {"size": topK, "_source": LAW_SOURCE, "query": query}


def buildMaterialQuery(queryText, queryVector, topK):
    bm25 = {"match": {"text": {"query": queryText}}}
    knn  = {"knn": {"knn_vector": {"vector": queryVector, "k": topK * 2}}}
    return {"size": topK, "_source": MATERIAL_SOURCE, "query": {"hybrid": {"queries": [bm25, knn]}}}


# ============================================================
# 결과 변환
# ============================================================

def toLawHit(hit, rank):
    src = hit.get("_source", {})
    out = {"rank": rank, "score": round(hit.get("_score") or 0, 4), "doc_id": hit["_id"]}
    for key in LAW_SOURCE:
        out[key] = src.get(key) if key == "effective_date" else src.get(key, "")
    return out


def toMaterialHit(hit, rank):
    src = hit.get("_source", {})
    return {
        "rank":         rank,
        "score":        round(hit.get("_score") or 0, 4),
        "recog_no":     hit["_id"],
        "material":     src.get("material", ""),
        "claims":       src.get("claims") or [],
        "daily_intake": src.get("daily_intake", ""),
        "caution":      src.get("caution", ""),
        "collected_at": src.get("collected_at", ""),
    }


# ============================================================
# 검색 실행
# ============================================================

def searchLaw(osClient, cfg, queryText, foodType, topK=5, mode="hybrid", queryVector=None):
    """법령·고시 검색. bm25 모드는 임베딩을 만들지 않는다."""
    if mode != "bm25" and queryVector is None:
        queryVector = embedQuery(cfg, queryText)
    body   = buildLawQuery(queryText, queryVector, foodType, topK, mode)
    params = {"search_pipeline": PIPELINE_ID} if mode == "hybrid" else {}
    resp   = osClient.search(index=LAW_INDEX, body=body, params=params)
    return [toLawHit(h, i + 1) for i, h in enumerate(resp["hits"]["hits"])]


def searchMaterials(osClient, cfg, queryText, topK=3, queryVector=None):
    """식약처 인정 기능성 검색 (하이브리드)."""
    if queryVector is None:
        queryVector = embedQuery(cfg, queryText)
    body = buildMaterialQuery(queryText, queryVector, topK)
    resp = osClient.search(index=MATERIAL_INDEX, body=body, params={"search_pipeline": PIPELINE_ID})
    return [toMaterialHit(h, i + 1) for i, h in enumerate(resp["hits"]["hits"])]


# ============================================================
# 메인 (CLI 테스트)
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="식품 법령·인정 기능성 하이브리드 검색 테스트")
    parser.add_argument("query")
    parser.add_argument("--food-type", default="general", choices=list(FOOD_TYPE_MAP))
    parser.add_argument("--mode",      default="hybrid",  choices=list(MODES))
    parser.add_argument("--topk",      default=5, type=int)
    parser.add_argument("--materials", action="store_true", help="인정 기능성도 검색")
    args = parser.parse_args()

    cfg      = loadConfig()
    osClient = getOsClient(cfg)
    ensurePipeline(osClient)
    for h in searchLaw(osClient, cfg, args.query, args.food_type, topK=args.topk, mode=args.mode):
        print(f"[{h['rank']}] {h['score']} | {h['law_name']} {h['article_no']}조 {h['clause_no']}항 "
              f"[{h['food_type']}] {h['content'][:80]}")
    if args.materials:
        for m in searchMaterials(osClient, cfg, args.query):
            print(f"[인정 {m['rank']}] {m['score']} | {m['material']} ({m['recog_no']}) {m['claims']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_search_hybrid.py -v`
Expected: 9 passed.

- [ ] **Step 5: 실제 검색 확인** (Task 3~5 완료 상태)

Run: `python scripts/rag/search_hybrid.py "먹으면 혈당이 내려갑니다" --food-type general`
Expected: 5건 출력, 모두 `[일반식품]` 또는 `[공통]`, 식품 등의 표시·광고에 관한 법률(또는 시행령 별표)이 상위에 포함.
Run: `python scripts/rag/search_hybrid.py "혈당 조절에 도움" --food-type health --materials`
Expected: `[인정 n]` 줄에 혈당 관련 원료(예: `홍삼 (2024-20)` 또는 `바나바주정추출물 (2005-3)`)가 나온다.

- [ ] **Step 6: Commit**

```bash
git add scripts/rag/search_hybrid.py tests/test_search_hybrid.py
git commit -m "식품 종류 필터 하이브리드 검색과 인정 기능성 검색 추가"
```

---

### Task 7: Context·프롬프트 (`answer_format.py` 1부)

**Files:**
- Create: `scripts/rag/answer_format.py`, `tests/test_answer_format_prompt.py`

**Interfaces:**
- Consumes: Task 1 `FOOD_TYPE_MAP`; Task 6 hit 형식(`toLawHit`, `toMaterialHit` 키)
- Produces:
  - `DISCLAIMER: str`, `USAGE_HINT: dict`, `SYSTEM_PROMPT: str`
  - `formatArticle(articleNo, clauseNo) -> str` (`"8","1"` → `제8조 1항`, `"8","0"` → `제8조`, `"별표 1","0"` → `별표 1`)
  - `buildContext(lawHits, materialHits) -> (context: str, refTable: dict[int, dict])` — refTable 값은 hit dict에 `"type": "law" | "material"`을 더한 것
  - `buildPrompt(foodType, usage, context, query) -> str`
  - `fixByteFallbackTokens(text) -> str`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_answer_format_prompt.py`:
```python
from answer_format import (DISCLAIMER, SYSTEM_PROMPT, buildContext, buildPrompt, fixByteFallbackTokens,
                           formatArticle)

LAW1 = {"law_name": "식품 등의 표시·광고에 관한 법률", "article_no": "8", "clause_no": "1",
        "title": "부당한 표시 또는 광고행위의 금지", "content": "제8조(...) 1항\n본문", "collected_at": "2026-10-16"}
ANNEX = {"law_name": "식품 등의 표시·광고에 관한 법률 시행령", "article_no": "별표 1", "clause_no": "0",
         "title": "부당한 표시 또는 광고의 내용", "content": "[별표 1] ...", "collected_at": "2026-10-16"}
MAT = {"recog_no": "2024-20", "material": "홍삼", "claims": ["혈당 조절에 도움을 줄 수 있음"],
       "collected_at": "2026-10-15"}


def test_formatArticle():
    assert formatArticle("8", "1") == "제8조 1항"
    assert formatArticle("8", "0") == "제8조"
    assert formatArticle("3의2", "") == "제3조의2"
    assert formatArticle("별표 1", "0") == "별표 1"


def test_buildContext_numbers_laws_then_materials():
    context, refs = buildContext([LAW1, ANNEX], [MAT])
    assert sorted(refs) == [1, 2, 3]
    assert refs[1]["type"] == "law" and refs[3]["type"] == "material"
    assert "[법령 조문]" in context
    assert "[1] 식품 등의 표시·광고에 관한 법률 제8조 1항 (부당한 표시 또는 광고행위의 금지)" in context
    assert "[2] 식품 등의 표시·광고에 관한 법률 시행령 별표 1 (부당한 표시 또는 광고의 내용)" in context
    assert "[인정 기능성 문구]" in context
    assert "[3] 원료: 홍삼 (인정번호 2024-20) / 인정 문구: 혈당 조절에 도움을 줄 수 있음" in context


def test_buildContext_omits_material_section_when_empty():
    context, refs = buildContext([LAW1], [])
    assert "[인정 기능성 문구]" not in context and list(refs) == [1]


def test_buildPrompt_includes_conditions_context_and_query():
    prompt = buildPrompt("health", "sns", "CTX", "혈당 관리에 최고!")
    assert prompt.startswith(SYSTEM_PROMPT)
    assert "식품 종류: 건강기능식품" in prompt
    assert "해시태그" in prompt
    assert "CTX" in prompt and prompt.rstrip().endswith("[답변]")
    assert "[질문]\n혈당 관리에 최고!" in prompt


def test_buildPrompt_without_usage():
    assert "사용처: 지정 안 함" in buildPrompt("general", None, "CTX", "q")


def test_system_prompt_demands_tag_format_and_number_citations():
    for tag in ("[판단]", "[판단이유]", "[해야할일]", "[근거]", "[범위밖사유]", "[식품종류]"):
        assert tag in SYSTEM_PROMPT
    assert "번호로만" in SYSTEM_PROMPT


def test_disclaimer_text_is_exact():
    assert DISCLAIMER == "법령 정보 안내이며 법률 자문이 아닙니다. 확신이 없으면 관할 기관이나 전문가에게 확인하세요."


def test_fixByteFallbackTokens_restores_hangul():
    assert fixByteFallbackTokens("그래<0xEB><0x89><0xBC>") == "그래뉼"
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_answer_format_prompt.py -v`
Expected: `ModuleNotFoundError: No module named 'answer_format'`

- [ ] **Step 3: `answer_format.py` 1부 작성**

`scripts/rag/answer_format.py`:
```python
# -*- coding: utf-8 -*-
"""
answer_format.py
검색 결과 → Context·프롬프트, LLM 출력 → 응답 dict 로 바꾸는 순수 함수 모음.

근거 표기 방식: LLM은 Context의 [번호]만 적고, 법령명·조문 번호·인정번호는 서버가
검색 결과(refTable)에서 채운다. LLM이 없는 번호를 적으면 버린다.
"""

# ============================================================
# 라이브러리 임포트
# ============================================================

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from food_common import FOOD_TYPE_MAP


# ============================================================
# 상수 정의
# ============================================================

DISCLAIMER = "법령 정보 안내이며 법률 자문이 아닙니다. 확신이 없으면 관할 기관이나 전문가에게 확인하세요."

USAGE_HINT = {
    "menu": "메뉴판 — 메뉴 이름과 메뉴 설명에도 같은 기준이 적용됩니다.",
    "page": "상세페이지 — 제품명, 이미지 속 글자, 후기 문구에도 같은 기준이 적용됩니다.",
    "sns":  "SNS 홍보 문구 — 게시글 본문, 해시태그, 이미지 속 글자에도 같은 기준이 적용됩니다.",
}

SYSTEM_PROMPT = """당신은 카페·음식점·반찬가게 운영자와 온라인 식품 판매자를 돕는 식품 표시·광고 점검 도우미입니다.
사용자가 쓰려는 광고 문구가 부당한 표시·광고에 해당할 소지가 있는지, 아래 [법령 조문]과 [인정 기능성 문구]만 근거로 판단합니다.

규칙:
1. Context에 있는 내용만 근거로 사용하고 추측하지 않습니다.
2. 근거는 Context의 대괄호 번호로만 적습니다. 법령명이나 조문 번호를 직접 쓰지 않습니다.
3. "위법입니다", "불법입니다", "위반입니다"처럼 단정하지 않습니다. 판단은 큼, 낮음, 어려움 중 하나입니다.
4. 질문이 식품·건강기능식품의 표시·광고 문구 점검이 아니면 [판단] 범위밖, [범위밖사유] 주제 로 답합니다.
   (예: 표시사항에 넣어야 하는 항목 안내, 영업 신고·인허가, 시설·위생 기준, 세금, 화장품·의약품 광고, 행정처분 결과 예측, 소송)
5. Context의 조문이 질문과 관련이 없으면 [판단] 범위밖, [범위밖사유] 근거없음 으로 답합니다.
6. "위법인가요?", "처벌받나요?"처럼 단정을 요구하면 위반 소지 수준과 근거만 답하고, 해야 할 일에 관할 기관이나 전문가 확인을 넣습니다.
7. 질문 내용이 선택한 식품 종류와 다르면(예: 일반식품을 골랐는데 "건강기능식품인데"라고 함) [식품종류] 불일치, 아니면 일치로 답합니다.
8. 건강기능식품은 [인정 기능성 문구]와 같은 범위의 표현만 쓸 수 있습니다. 인정 문구를 넘어서는 표현이나 질병 예방·치료 표현은 큼입니다.
   맞는 인정 문구를 찾지 못하면 어려움으로 하고, 해야 할 일에 "인정된 기능성인지 식약처 확인 필요"를 넣습니다.
9. 일반식품이 질병 예방·치료 효과나 건강기능식품으로 오인될 기능성을 표방하면 큼입니다.
10. "최고", "100%", "무첨가" 같은 단정·과장 표현은 근거 자료에 따라 달라지므로 보통 어려움이고, 해야 할 일에 근거 자료 확인을 넣습니다.

반드시 아래 형식 그대로 답합니다. 형식 밖의 말은 쓰지 않습니다.
[판단] 큼 또는 낮음 또는 어려움 또는 범위밖
[판단이유] 판단의 이유를 한두 문장으로
[해야할일]
1. 할 일
2. 할 일
[근거]
번호 | 이 근거가 문구와 어떻게 관련되는지 한 문장
[범위밖사유] 주제 또는 근거없음 (범위밖일 때만)
[식품종류] 일치 또는 불일치"""


# ============================================================
# Context / 프롬프트
# ============================================================

def formatArticle(articleNo, clauseNo):
    """화면·근거 표시용 조문 표기. 별표는 그대로, 항 번호가 0이거나 없으면 생략."""
    articleNo = str(articleNo or "")
    if articleNo.startswith("별표"):
        return articleNo
    text = f"제{articleNo}조"
    if clauseNo and str(clauseNo) != "0":
        text += f" {clauseNo}항"
    return text


def buildContext(lawHits, materialHits):
    """
    법령 결과에 [1]~, 인정 문구에 이어지는 번호를 붙인 Context 문자열과
    {번호: 검색 결과 + type} 표를 만든다.
    """
    lines    = []
    refTable = {}
    n        = 0
    if lawHits:
        lines.append("[법령 조문]")
        for hit in lawHits:
            n += 1
            refTable[n] = dict(hit, type="law")
            lines.append(f"[{n}] {hit['law_name']} {formatArticle(hit['article_no'], hit['clause_no'])} "
                         f"({hit.get('title', '')})\n{hit.get('content', '')}")
    if materialHits:
        lines.append("\n[인정 기능성 문구]")
        for hit in materialHits:
            n += 1
            refTable[n] = dict(hit, type="material")
            claims = " / ".join(hit.get("claims") or [])
            lines.append(f"[{n}] 원료: {hit['material']} (인정번호 {hit['recog_no']}) / 인정 문구: {claims}")
    return "\n".join(lines), refTable


def buildPrompt(foodType, usage, context, query):
    """시스템 프롬프트 + 점검 조건(식품 종류·사용처) + Context + 질문."""
    usageLine = USAGE_HINT.get(usage, "지정 안 함")
    return f"""{SYSTEM_PROMPT}

[점검 조건]
식품 종류: {FOOD_TYPE_MAP[foodType]}
사용처: {usageLine}

{context}

[질문]
{query}

[답변]"""


# ============================================================
# LLM 출력 보정
# ============================================================

_BYTE_TOKEN_RE = re.compile(r'(?:<0x[0-9A-Fa-f]{2}>)+')


def fixByteFallbackTokens(text):
    """
    Ollama/llama.cpp가 병합하지 못한 byte-fallback 토큰(예: <0xEB><0x89><0xBC>)을
    UTF-8 문자로 복원한다. (에스테틱 rag_pipeline.py 에서 가져옴)
    """
    def repl(m):
        raw = bytes(int(h, 16) for h in re.findall(r'0x([0-9A-Fa-f]{2})', m.group(0)))
        return raw.decode("utf-8", errors="replace")
    return _BYTE_TOKEN_RE.sub(repl, text)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_answer_format_prompt.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/rag/answer_format.py tests/test_answer_format_prompt.py
git commit -m "Context 번호 부여와 식품 표시·광고 프롬프트 추가"
```

---

### Task 8: 답변 파싱과 응답 조립 (`answer_format.py` 2부)

**Files:**
- Modify: `scripts/rag/answer_format.py` (파일 끝에 추가)
- Create: `tests/test_answer_format_parse.py`

**Interfaces:**
- Consumes: Task 7 `DISCLAIMER`, `formatArticle`, `buildContext`의 refTable
- Produces:
  - `VERDICT_MAP = {"큼": "high", "낮음": "low", "어려움": "unsure", "범위밖": "out_of_scope"}`
  - `OUT_OF_SCOPE_ACTIONS = {"topic": [...2개], "no_basis": [...2개]}`
  - `NO_BASIS_PARSED: dict` (검색 결과 0건일 때 쓰는 parsed 값)
  - `parseAnswer(raw) -> dict` 키: `ok, verdict, verdict_reason, actions, basis_refs(list[(int, str)]), out_of_scope_reason, food_type_mismatch` (`ok=False`면 나머지 기본값)
  - `resolveBasis(basisRefs, refTable) -> (items: list[dict], usedRefs: list[int])`
  - `latestCollectedAt(entries) -> str | None`
  - `buildResponse(parsed, refTable, raw, fallbackCollectedAt=None) -> dict` (spec 5.5 응답 형식)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_answer_format_parse.py`:
```python
from answer_format import (DISCLAIMER, NO_BASIS_PARSED, OUT_OF_SCOPE_ACTIONS, buildResponse, latestCollectedAt,
                           parseAnswer, resolveBasis)

REFS = {
    1: {"type": "law", "law_name": "식품 등의 표시·광고에 관한 법률", "article_no": "8", "clause_no": "1",
        "effective_date": "20250101", "collected_at": "2026-10-16"},
    2: {"type": "law", "law_name": "식품 등의 표시·광고에 관한 법률 시행령", "article_no": "별표 1", "clause_no": "0",
        "effective_date": None, "collected_at": "2026-10-17"},
    3: {"type": "material", "material": "홍삼", "recog_no": "2024-20", "claims": ["혈당 조절에 도움을 줄 수 있음"],
        "collected_at": "2026-10-15"},
}

NORMAL = """[판단] 큼
[판단이유] 일반식품에서 질병 치료 효과를 나타내는 표현은 부당한 표시·광고에 해당할 수 있습니다.
[해야할일]
1. 질병을 암시하는 표현을 뺍니다.
2) 확신이 없으면 관할 기관에 확인합니다.
[근거]
1 | 질병 예방·치료 표현 금지 조항입니다.
3 | 인정 문구는 혈당 조절까지입니다.
[식품종류] 일치"""


def test_parse_normal_answer():
    p = parseAnswer(NORMAL)
    assert p["ok"] and p["verdict"] == "high"
    assert p["verdict_reason"].startswith("일반식품에서")
    assert p["actions"] == ["질병을 암시하는 표현을 뺍니다.", "확신이 없으면 관할 기관에 확인합니다."]
    assert p["basis_refs"] == [(1, "질병 예방·치료 표현 금지 조항입니다."), (3, "인정 문구는 혈당 조절까지입니다.")]
    assert p["food_type_mismatch"] is False and p["out_of_scope_reason"] is None


def test_parse_all_verdict_words():
    for word, code in (("낮음", "low"), ("판단하기 어려움", "unsure"), ("위반 소지 큼", "high"), ("범위 밖", "out_of_scope")):
        assert parseAnswer(f"[판단] {word}\n[판단이유] 이유")["verdict"] == code


def test_parse_tolerates_bold_and_fullwidth_brackets_and_comma_refs():
    raw = "**[판단]** 어려움\n【판단이유】 근거 자료가 필요합니다.\n[근거] 2, 1\n[식품 종류] 불일치"
    p = parseAnswer(raw)
    assert p["verdict"] == "unsure" and p["verdict_reason"] == "근거 자료가 필요합니다."
    assert p["basis_refs"] == [(2, ""), (1, "")]
    assert p["food_type_mismatch"] is True


def test_parse_out_of_scope_reasons():
    assert parseAnswer("[판단] 범위밖\n[범위밖사유] 근거없음")["out_of_scope_reason"] == "no_basis"
    assert parseAnswer("[판단] 범위밖\n[범위밖사유] 주제")["out_of_scope_reason"] == "topic"
    assert parseAnswer("[판단] 범위밖")["out_of_scope_reason"] == "topic"


def test_parse_failure_when_verdict_missing_or_unknown():
    assert parseAnswer("그냥 설명만 했습니다.")["ok"] is False
    assert parseAnswer("[판단] 높음")["ok"] is False


def test_resolveBasis_maps_numbers_and_drops_unknown_or_duplicate():
    items, used = resolveBasis([(1, "요약1"), (9, "없는 번호"), (1, "중복"), (2, ""), (3, "인정")], REFS)
    assert used == [1, 2, 3]
    assert items[0] == {"type": "law", "law_name": "식품 등의 표시·광고에 관한 법률", "article": "제8조 1항",
                        "summary": "요약1", "effective_date": "20250101"}
    assert items[1]["article"] == "별표 1"
    assert items[2] == {"type": "material", "material": "홍삼", "recog_no": "2024-20",
                        "claim": "혈당 조절에 도움을 줄 수 있음", "summary": "인정"}


def test_latestCollectedAt_ignores_empty():
    assert latestCollectedAt([{"collected_at": "2026-10-15"}, {"collected_at": ""}, {"collected_at": "2026-10-17"}]) == "2026-10-17"
    assert latestCollectedAt([]) is None


def test_buildResponse_normal_uses_dates_of_cited_refs():
    resp = buildResponse(parseAnswer(NORMAL), REFS, NORMAL)
    assert resp["success"] is True and resp["verdict"] == "high"
    assert [b["type"] for b in resp["basis"]] == ["law", "material"]
    assert resp["collected_at"] == "2026-10-16"
    assert resp["disclaimer"] == DISCLAIMER and resp["raw_fallback"] == ""


def test_buildResponse_out_of_scope_clears_basis_and_uses_fixed_actions():
    raw = "[판단] 범위밖\n[판단이유] 영업 신고 질문입니다.\n[근거] 1\n[범위밖사유] 주제"
    resp = buildResponse(parseAnswer(raw), REFS, raw)
    assert resp["verdict"] == "out_of_scope" and resp["out_of_scope_reason"] == "topic"
    assert resp["basis"] == [] and resp["actions"] == OUT_OF_SCOPE_ACTIONS["topic"]
    assert resp["collected_at"] == "2026-10-17"


def test_buildResponse_parse_failure_keeps_raw():
    resp = buildResponse(parseAnswer("형식 없는 답"), REFS, "형식 없는 답")
    assert resp["verdict"] == "unsure" and resp["raw_fallback"] == "형식 없는 답" and resp["basis"] == []


def test_buildResponse_in_scope_without_valid_refs_is_not_refused():
    raw = "[판단] 어려움\n[판단이유] 이유\n[근거] 7"
    resp = buildResponse(parseAnswer(raw), REFS, raw)
    assert resp["verdict"] == "unsure" and resp["basis"] == []


def test_buildResponse_no_hits_uses_no_basis_and_fallback_date():
    resp = buildResponse(NO_BASIS_PARSED, {}, "", "2026-10-16")
    assert resp["verdict"] == "out_of_scope" and resp["out_of_scope_reason"] == "no_basis"
    assert resp["actions"] == OUT_OF_SCOPE_ACTIONS["no_basis"] and resp["collected_at"] == "2026-10-16"
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_answer_format_parse.py -v`
Expected: `ImportError: cannot import name 'NO_BASIS_PARSED' from 'answer_format'`

- [ ] **Step 3: `answer_format.py` 끝에 2부 추가**

```python


# ============================================================
# LLM 출력 파싱
# ============================================================

VERDICT_MAP = {"큼": "high", "낮음": "low", "어려움": "unsure", "범위밖": "out_of_scope"}
VERDICT_ORDER = ("범위밖", "어려움", "낮음", "큼")   # "판단하기 어려움"이 "큼"보다 먼저 걸리도록

OUT_OF_SCOPE_ACTIONS = {
    "topic": [
        "이 챗봇은 식품·건강기능식품의 표시·광고 문구만 점검합니다.",
        "영업 신고·인허가는 관할 시·군·구청, 제품 심사·신고는 식품의약품안전처에 문의하세요.",
    ],
    "no_basis": [
        "근거 조문을 찾지 못했습니다.",
        "관할 시·군·구청 식품 담당 부서나 식품의약품안전처에 문의하세요.",
    ],
}

NO_BASIS_PARSED = {
    "ok": True, "verdict": "out_of_scope", "verdict_reason": "", "actions": [], "basis_refs": [],
    "out_of_scope_reason": "no_basis", "food_type_mismatch": False,
}

_TAG_RE        = re.compile(r"\[\s*(판단\s*이유|판단|해야\s*할\s*일|근거|범위\s*밖\s*사유|식품\s*종류)\s*\]")
_LIST_MARK_RE  = re.compile(r"^\s*(?:\d+\s*[.)]|[-•·*])\s*")
_REF_LINE_RE   = re.compile(r"^\s*\[?(\d+)\]?\s*(?:[|:：\-–]\s*(.*))?$")
_REF_LIST_RE   = re.compile(r"^[\d\s,\[\]]+$")


def _squash(text):
    return re.sub(r"\s+", "", text or "")


def splitSections(raw):
    """[태그] 기준으로 나눈 {태그(공백 제거): 내용}. 같은 태그가 다시 나오면 처음 것만."""
    text    = (raw or "").replace("**", "").replace("【", "[").replace("】", "]")
    matches = list(_TAG_RE.finditer(text))
    out     = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        key = _squash(m.group(1))
        if key not in out:
            out[key] = text[m.end():end].strip()
    return out


def parseVerdict(value):
    squashed = _squash(value)
    for word in VERDICT_ORDER:
        if word in squashed:
            return VERDICT_MAP[word]
    return None


def parseActions(value):
    actions = []
    for line in (value or "").split("\n"):
        line = _LIST_MARK_RE.sub("", line).strip()
        if line:
            actions.append(line)
    return actions


def parseBasisRefs(value):
    refs = []
    for line in (value or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        if _REF_LIST_RE.match(line):
            refs += [(int(n), "") for n in re.findall(r"\d+", line)]
            continue
        m = _REF_LINE_RE.match(line)
        if m:
            refs.append((int(m.group(1)), (m.group(2) or "").strip()))
    return refs


def parseAnswer(raw):
    """LLM 원문을 구조화. [판단]이 없거나 값을 알 수 없으면 ok=False."""
    sections = splitSections(raw)
    verdict  = parseVerdict(sections.get("판단", ""))
    if verdict is None:
        return dict(NO_BASIS_PARSED, ok=False, verdict=None, out_of_scope_reason=None)
    outReason = None
    if verdict == "out_of_scope":
        outReason = "no_basis" if "근거없음" in _squash(sections.get("범위밖사유", "")) else "topic"
    return {
        "ok":                  True,
        "verdict":             verdict,
        "verdict_reason":      sections.get("판단이유", "").strip(),
        "actions":             parseActions(sections.get("해야할일", "")),
        "basis_refs":          parseBasisRefs(sections.get("근거", "")),
        "out_of_scope_reason": outReason,
        "food_type_mismatch":  "불일치" in _squash(sections.get("식품종류", "")),
    }


# ============================================================
# 근거 채우기 / 응답 조립
# ============================================================

def resolveBasis(basisRefs, refTable):
    """번호 → 근거 항목. refTable에 없는 번호와 중복 번호는 버린다."""
    items = []
    used  = []
    for n, summary in basisRefs:
        entry = refTable.get(n)
        if entry is None or n in used:
            continue
        used.append(n)
        if entry["type"] == "law":
            items.append({
                "type":           "law",
                "law_name":       entry["law_name"],
                "article":        formatArticle(entry["article_no"], entry["clause_no"]),
                "summary":        summary,
                "effective_date": entry.get("effective_date"),
            })
        else:
            items.append({
                "type":     "material",
                "material": entry["material"],
                "recog_no": entry["recog_no"],
                "claim":    " / ".join(entry.get("claims") or []),
                "summary":  summary,
            })
    return items, used


def latestCollectedAt(entries):
    dates = [e.get("collected_at") for e in entries if e.get("collected_at")]
    return max(dates) if dates else None


def buildResponse(parsed, refTable, raw, fallbackCollectedAt=None):
    """parsed + refTable → API 응답 dict (spec 5.5)."""
    contextDate = latestCollectedAt(list(refTable.values())) or fallbackCollectedAt
    resp = {
        "success":             True,
        "verdict":             "unsure",
        "verdict_reason":      "",
        "actions":             [],
        "basis":               [],
        "out_of_scope_reason": None,
        "food_type_mismatch":  False,
        "collected_at":        contextDate,
        "disclaimer":          DISCLAIMER,
        "raw_fallback":        "",
    }
    if not parsed["ok"]:
        resp["raw_fallback"] = (raw or "").strip()
        return resp

    resp["verdict_reason"]     = parsed["verdict_reason"]
    resp["food_type_mismatch"] = parsed["food_type_mismatch"]
    if parsed["verdict"] == "out_of_scope":
        reason = parsed["out_of_scope_reason"] or "topic"
        resp.update(verdict="out_of_scope", out_of_scope_reason=reason,
                    actions=list(OUT_OF_SCOPE_ACTIONS[reason]))
        return resp

    items, used = resolveBasis(parsed["basis_refs"], refTable)
    resp.update(verdict=parsed["verdict"], actions=parsed["actions"], basis=items,
                collected_at=latestCollectedAt([refTable[n] for n in used]) or contextDate)
    return resp
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_answer_format_parse.py tests/test_answer_format_prompt.py -v`
Expected: 20 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/rag/answer_format.py tests/test_answer_format_parse.py
git commit -m "LLM 답변 태그 파싱과 근거 번호 → 조문 채우기 추가"
```

---

### Task 9: 캐시와 RAG 파이프라인 (`qa_cache.py`, `rag_pipeline.py`)

**Files:**
- Create: `scripts/rag/qa_cache.py`, `scripts/rag/rag_pipeline.py`, `tests/test_qa_cache.py`, `tests/test_rag_pipeline.py`

**Interfaces:**
- Consumes: Task 6 `embedQuery, searchLaw, searchMaterials, LAW_INDEX`; Task 7·8 `buildContext, buildPrompt, parseAnswer, buildResponse, NO_BASIS_PARSED, fixByteFallbackTokens`
- Produces:
  - `qa_cache.CACHE_INDEX = "food-qa-cache"`, `REDIS_PREFIX = "foodqa:"`, `ensureCacheIndex(osClient)`, `getRedisClient(cfg)`, `lookupCache(osClient, redisClient, cfg, docType, queryText, scope=None) -> (dict | None, queryVector)`, `storeCache(osClient, redisClient, cfg, docType, queryText, ragResult, scope=None, queryVector=None)`
  - `rag_pipeline.runFoodRag(osClient, cfg, query, foodType, usage=None, queryVector=None) -> dict`(spec 5.5), `generateAnswer(cfg, prompt) -> str`, `latestIndexCollectedAt(osClient) -> str | None`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_qa_cache.py`:
```python
import json

import qa_cache
from qa_cache import CACHE_INDEX, REDIS_PREFIX, lookupCache, storeCache

CFG = {"qaCacheThreshold": 0.95, "qaCacheTtlSec": 60}


class FakeOs:
    def __init__(self, hits=None, exc=None):
        self.hits, self.exc, self.searched, self.indexed = hits or [], exc, [], []

    def search(self, index, body):
        if self.exc:
            raise self.exc
        self.searched.append((index, body))
        return {"hits": {"hits": self.hits}}

    def index(self, index, body):
        if self.exc:
            raise self.exc
        self.indexed.append((index, body))


class FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value


def patchEmbed(monkeypatch):
    monkeypatch.setattr(qa_cache, "embedQuery", lambda cfg, q: [0.5])


def test_lookup_miss_when_search_fails(monkeypatch):
    patchEmbed(monkeypatch)
    cached, vec = lookupCache(FakeOs(exc=RuntimeError("down")), FakeRedis(), CFG, "food", "q", scope="general:_")
    assert cached is None and vec == [0.5]


def test_lookup_filters_by_doc_type_and_scope(monkeypatch):
    patchEmbed(monkeypatch)
    fake = FakeOs()
    lookupCache(fake, FakeRedis(), CFG, "food", "q", scope="health:sns")
    index, body = fake.searched[0]
    filters = body["query"]["knn"]["knn_vector"]["filter"]["bool"]["filter"]
    assert index == CACHE_INDEX
    assert {"term": {"doc_type": "food"}} in filters and {"term": {"scope": "health:sns"}} in filters


def test_lookup_hit_reads_prefixed_redis_key(monkeypatch):
    patchEmbed(monkeypatch)
    redis = FakeRedis()
    redis.store[f"{REDIS_PREFIX}abc"] = json.dumps({"verdict": "high"})
    fake = FakeOs(hits=[{"_score": 0.99, "_source": {"answer_id": "abc"}}])
    cached, _ = lookupCache(fake, redis, CFG, "food", "q", scope="general:_")
    assert cached == {"verdict": "high"}


def test_lookup_below_threshold_is_miss(monkeypatch):
    patchEmbed(monkeypatch)
    fake = FakeOs(hits=[{"_score": 0.90, "_source": {"answer_id": "abc"}}])
    assert lookupCache(fake, FakeRedis(), CFG, "food", "q")[0] is None


def test_store_writes_redis_and_index_and_survives_failure():
    redis, fake = FakeRedis(), FakeOs()
    storeCache(fake, redis, CFG, "food", "q", {"verdict": "low"}, scope="general:menu", queryVector=[0.5])
    assert len(redis.store) == 1 and next(iter(redis.store)).startswith(REDIS_PREFIX)
    assert fake.indexed[0][1]["scope"] == "general:menu"
    storeCache(FakeOs(exc=RuntimeError("down")), FakeRedis(), CFG, "food", "q", {}, queryVector=[0.5])
```

`tests/test_rag_pipeline.py`:
```python
import pytest

import rag_pipeline

LAW_HIT = {"rank": 1, "score": 1.0, "doc_id": "d1", "law_name": "식품 등의 표시·광고에 관한 법률", "kind": "법률",
           "food_type": "공통", "article_no": "8", "clause_no": "1", "title": "부당한 표시 또는 광고행위의 금지",
           "content": "본문", "effective_date": "20250101", "collected_at": "2026-10-16"}
MAT_HIT = {"rank": 1, "score": 1.0, "recog_no": "2024-20", "material": "홍삼",
           "claims": ["혈당 조절에 도움을 줄 수 있음"], "daily_intake": "", "caution": "", "collected_at": "2026-10-15"}
LLM_OUT = "[판단] 큼\n[판단이유] 이유\n[해야할일]\n1. 뺍니다\n[근거]\n1 | 금지 조항\n2 | 인정 범위\n[식품종류] 일치"


@pytest.fixture
def calls(monkeypatch):
    log = {"materials": 0, "llm": [], "law": []}

    def fakeLaw(osClient, cfg, query, foodType, topK=5, mode="hybrid", queryVector=None):
        log["law"].append((foodType, queryVector))
        return [dict(LAW_HIT)]

    def fakeMat(osClient, cfg, query, topK=3, queryVector=None):
        log["materials"] += 1
        return [dict(MAT_HIT)]

    def fakeLlm(cfg, prompt):
        log["llm"].append(prompt)
        return LLM_OUT

    monkeypatch.setattr(rag_pipeline, "searchLaw", fakeLaw)
    monkeypatch.setattr(rag_pipeline, "searchMaterials", fakeMat)
    monkeypatch.setattr(rag_pipeline, "generateAnswer", fakeLlm)
    monkeypatch.setattr(rag_pipeline, "embedQuery", lambda cfg, q: [0.1])
    return log


def test_general_skips_material_search(calls):
    resp = rag_pipeline.runFoodRag(None, {}, "혈당 관리 샐러드", "general", usage="menu", queryVector=[0.2])
    assert calls["materials"] == 0 and calls["law"] == [("general", [0.2])]
    assert "식품 종류: 일반식품" in calls["llm"][0] and "메뉴판" in calls["llm"][0]
    assert resp["verdict"] == "high" and [b["type"] for b in resp["basis"]] == ["law"]


def test_health_includes_materials_in_basis(calls):
    resp = rag_pipeline.runFoodRag(None, {}, "혈당 관리에 최고", "health")
    assert calls["materials"] == 1
    assert [b["type"] for b in resp["basis"]] == ["law", "material"]
    assert resp["basis"][1]["recog_no"] == "2024-20"


def test_no_hits_skips_llm_and_returns_no_basis(monkeypatch, calls):
    monkeypatch.setattr(rag_pipeline, "searchLaw", lambda *a, **k: [])
    monkeypatch.setattr(rag_pipeline, "latestIndexCollectedAt", lambda osClient: "2026-10-16")
    resp = rag_pipeline.runFoodRag(None, {}, "아무 말", "general")
    assert calls["llm"] == []
    assert resp["verdict"] == "out_of_scope" and resp["out_of_scope_reason"] == "no_basis"
    assert resp["collected_at"] == "2026-10-16"
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_qa_cache.py tests/test_rag_pipeline.py -v`
Expected: `ModuleNotFoundError: No module named 'qa_cache'` / `'rag_pipeline'`

- [ ] **Step 3: `qa_cache.py` 작성**

`scripts/rag/qa_cache.py`:
```python
# -*- coding: utf-8 -*-
"""
qa_cache.py
질문-답변 시맨틱 캐시 (에스테틱 qa_cache.py 와 같은 방식, 이름만 식품용으로 분리).

BGE-M3 임베딩으로 과거 질문과의 코사인 유사도를 비교해, 임계값 이상이면 RAG를 다시 돌리지 않고
과거 답변을 그대로 반환한다. 식품 종류·사용처가 다르면 답이 달라지므로 scope("general:sns" 등)로 나눈다.

저장 위치:
- OpenSearch (food-qa-cache 인덱스): 질문 임베딩 + 메타 → 유사도 검색용
- Redis (foodqa:<answer_id>)        : 답변 payload(JSON)
"""

# ============================================================
# 라이브러리 임포트
# ============================================================

import json
import os
import sys
import time
import uuid

import redis

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from search_hybrid import embedQuery


# ============================================================
# 상수 정의
# ============================================================

CACHE_INDEX  = "food-qa-cache"
REDIS_PREFIX = "foodqa:"


# ============================================================
# 인덱스 / 클라이언트 초기화
# ============================================================

def ensureCacheIndex(osClient):
    """food-qa-cache 인덱스가 없으면 생성."""
    if osClient.indices.exists(index=CACHE_INDEX):
        return
    mapping = {
        "settings": {"number_of_shards": 1, "number_of_replicas": 0, "index.knn": True},
        "mappings": {
            "properties": {
                "doc_type":   {"type": "keyword"},
                "scope":      {"type": "keyword"},
                "query":      {"type": "text"},
                "answer_id":  {"type": "keyword"},
                "created_at": {"type": "date"},
                "knn_vector": {
                    "type":      "knn_vector",
                    "dimension": 1024,
                    "method": {"name": "hnsw", "space_type": "cosinesimil", "engine": "lucene"},
                },
            }
        },
    }
    osClient.indices.create(index=CACHE_INDEX, body=mapping)
    print(f"[INFO] 인덱스 생성 완료: {CACHE_INDEX}")


def getRedisClient(cfg):
    return redis.Redis(
        host=cfg['redisHost'],
        port=cfg['redisPort'],
        db=cfg['redisDb'],
        password=cfg['redisPassword'] or None,
        decode_responses=True,
    )


# ============================================================
# 캐시 조회 / 적재
# ============================================================

def lookupCache(osClient, redisClient, cfg, docType, queryText, scope=None):
    """
    가장 비슷한 과거 질문의 답변을 찾는다. 캐시 장애는 '캐시 없음'으로 처리한다.
    반환: (캐시된 답변 또는 None, queryVector) — queryVector는 검색·저장에 재사용
    """
    queryVector = embedQuery(cfg, queryText)
    try:
        filters = [
            {"term": {"doc_type": docType}},
            {"term": {"scope": scope or "_all"}},
        ]
        body = {
            "size":    1,
            "_source": ["answer_id"],
            "query": {"knn": {"knn_vector": {"vector": queryVector, "k": 1,
                                             "filter": {"bool": {"filter": filters}}}}},
        }
        hits = osClient.search(index=CACHE_INDEX, body=body)["hits"]["hits"]
        if not hits or hits[0]["_score"] < cfg['qaCacheThreshold']:
            return None, queryVector
        cached = redisClient.get(REDIS_PREFIX + hits[0]["_source"]["answer_id"])
        if not cached:
            return None, queryVector
        print(f"[CACHE HIT] score={hits[0]['_score']:.4f}")
        return json.loads(cached), queryVector
    except Exception as e:
        print(f"[WARN] 캐시 조회 실패, RAG 정상 실행으로 진행: {e}")
        return None, queryVector


def storeCache(osClient, redisClient, cfg, docType, queryText, ragResult, scope=None, queryVector=None):
    """새 질문-답변을 캐시에 적재. 실패해도 응답에는 영향 없음."""
    try:
        if queryVector is None:
            queryVector = embedQuery(cfg, queryText)
        answerId = uuid.uuid4().hex
        redisClient.setex(REDIS_PREFIX + answerId, cfg['qaCacheTtlSec'],
                          json.dumps(ragResult, ensure_ascii=False))
        osClient.index(
            index=CACHE_INDEX,
            body={
                "doc_type":   docType,
                "scope":      scope or "_all",
                "query":      queryText,
                "answer_id":  answerId,
                "created_at": int(time.time() * 1000),
                "knn_vector": queryVector,
            },
        )
    except Exception as e:
        print(f"[WARN] 캐시 저장 실패 (응답에는 영향 없음): {e}")
```

- [ ] **Step 4: `rag_pipeline.py` 작성**

`scripts/rag/rag_pipeline.py`:
```python
# -*- coding: utf-8 -*-
"""
rag_pipeline.py
광고 문구 점검 RAG: 법령 검색(+건강기능식품이면 인정 기능성 검색) → Context → Gemma 1회 → 파싱.

사용법 (CLI 테스트):
  python scripts/rag/rag_pipeline.py "우리 카페 홍삼차, 혈당 관리에 최고!" --food-type general --usage sns
"""

# ============================================================
# 라이브러리 임포트
# ============================================================

import argparse
import json
import os
import sys

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from answer_format import (NO_BASIS_PARSED, buildContext, buildPrompt, buildResponse, fixByteFallbackTokens,
                           parseAnswer)
from food_common import FOOD_TYPE_MAP, getOsClient, loadConfig
from search_hybrid import LAW_INDEX, embedQuery, ensurePipeline, searchLaw, searchMaterials


# ============================================================
# 상수 정의
# ============================================================

GENERATE_API_PATH = "/api/generate"
LAW_TOP_K         = 5
MATERIAL_TOP_K    = 3


# ============================================================
# LLM / 인덱스 보조
# ============================================================

def generateAnswer(cfg, prompt):
    """Ollama Gemma로 답변 생성 (스트리밍 없음)."""
    url     = cfg['ollamaHost'].rstrip("/") + GENERATE_API_PATH
    payload = {
        "model":   cfg['llmModel'],
        "prompt":  prompt,
        "stream":  False,
        "options": {"temperature": 0.1, "num_ctx": 8192},
    }
    resp = requests.post(url, json=payload, timeout=300)
    resp.raise_for_status()
    return fixByteFallbackTokens(resp.json().get("response", ""))


def latestIndexCollectedAt(osClient):
    """food-law-articles 전체에서 가장 최근 collected_at (검색 결과가 없을 때의 수집 기준일)."""
    try:
        resp = osClient.search(index=LAW_INDEX,
                               body={"size": 0, "aggs": {"latest": {"max": {"field": "collected_at"}}}})
        return resp["aggregations"]["latest"].get("value_as_string")
    except Exception:
        return None


# ============================================================
# RAG 실행
# ============================================================

def runFoodRag(osClient, cfg, query, foodType, usage=None, queryVector=None):
    """
    광고 문구 점검 전체 실행. 반환: API 응답 dict (spec 5.5).
    검색 결과가 하나도 없으면 LLM을 부르지 않고 '근거 조문을 찾지 못함'으로 답한다.
    """
    if queryVector is None:
        queryVector = embedQuery(cfg, query)

    lawHits      = searchLaw(osClient, cfg, query, foodType, topK=LAW_TOP_K, queryVector=queryVector)
    materialHits = []
    if foodType == "health":
        materialHits = searchMaterials(osClient, cfg, query, topK=MATERIAL_TOP_K, queryVector=queryVector)

    if not lawHits and not materialHits:
        return buildResponse(NO_BASIS_PARSED, {}, "", latestIndexCollectedAt(osClient))

    context, refTable = buildContext(lawHits, materialHits)
    raw = generateAnswer(cfg, buildPrompt(foodType, usage, context, query))
    return buildResponse(parseAnswer(raw), refTable, raw)


# ============================================================
# 메인 (CLI 테스트)
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="식품 표시·광고 점검 RAG 테스트")
    parser.add_argument("query")
    parser.add_argument("--food-type", default="general", choices=list(FOOD_TYPE_MAP))
    parser.add_argument("--usage",     default=None,      choices=["menu", "page", "sns"])
    args = parser.parse_args()

    cfg      = loadConfig()
    osClient = getOsClient(cfg)
    ensurePipeline(osClient)
    result = runFoodRag(osClient, cfg, args.query, args.food_type, usage=args.usage)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_qa_cache.py tests/test_rag_pipeline.py -v`
Expected: 8 passed.

- [ ] **Step 6: 실제 실행 확인** (OpenSearch, Ollama `gemma4:e4b` 필요)

Run: `python scripts/rag/rag_pipeline.py "우리 카페 홍삼차, 혈당 관리에 최고!" --food-type general --usage sns`
Expected: JSON 출력. `verdict`가 `high`, `basis`에 `type: "law"` 항목 1개 이상, `disclaimer`가 고정 문구, `raw_fallback`이 `""`. `raw_fallback`에 원문이 들어 있으면 Gemma가 형식을 안 지킨 것이므로 원문을 보고 Task 7 `SYSTEM_PROMPT` 또는 Task 8 파서를 고친다(고친 경우 해당 테스트에 그 원문 사례를 추가).

- [ ] **Step 7: Commit**

```bash
git add scripts/rag/qa_cache.py scripts/rag/rag_pipeline.py tests/test_qa_cache.py tests/test_rag_pipeline.py
git commit -m "식품용 시맨틱 캐시와 RAG 파이프라인 추가"
```

---

### Task 10: 웹 화면 (`web/index.html`)

**Files:**
- Create: `web/index.html`, `tests/test_web_page.py`

**Interfaces:**
- Consumes: `POST /rag/query` 요청 `{query, food_type, usage}`, 응답 spec 5.5 (Task 8 `buildResponse` 형식). 오류 응답 `{"detail": "..."}`.
- Produces: 요소 id `kind-general`, `kind-health`, `log`, `q`, `send`, `clear`. 같은 출처의 `/rag/query`만 호출.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_web_page.py`:
```python
import re
from pathlib import Path

PAGE = (Path(__file__).resolve().parents[1] / "web" / "index.html").read_text(encoding="utf-8")


def test_page_has_toggle_usage_and_composer():
    for elementId in ("kind-general", "kind-health", "log", "q", "send", "clear"):
        assert f'id="{elementId}"' in PAGE
    assert 'role="radiogroup"' in PAGE
    for use in ("menu", "page", "sns"):
        assert f'data-use="{use}"' in PAGE


def test_page_calls_api_and_has_four_verdict_labels():
    assert "fetch('/rag/query'" in PAGE
    for label in ("위반 소지 큼", "위반 소지 낮음", "판단 어려움", "범위 밖"):
        assert label in PAGE


def test_page_never_uses_innerHTML_for_answers():
    assert "innerHTML =" not in PAGE.replace("log.innerHTML = ''", "")


def test_demo_only_parts_removed():
    assert "미리 써 둔 예시" not in PAGE
    assert "식품 표시사항에 꼭 넣어야 하는 항목" not in PAGE
    assert re.search(r"function classify\(", PAGE) is None


def test_law_list_includes_health_functional_standard():
    assert "건강기능식품의 기준 및 규격" in PAGE
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_web_page.py -v`
Expected: `FileNotFoundError: ... web/index.html`

- [ ] **Step 3: `web/index.html` 작성**

`web/index.html`:
```html
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>식품 표시·광고 도우미</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&display=swap">
<style>
/* 데모 화면(claude.ai artifact) 디자인을 그대로 옮기고, 식품 종류 선택을 두 칸 토글로 바꿈 */
:root{
  --bg:#EEF1F6;--surface:#FFFFFF;--surface2:#F4F6FA;--ink:#15202E;--muted:#58677B;--line:#D8DFEA;
  --accent:#1F5FA8;--on-accent:#FFFFFF;--accent-bg:#E3EDFA;
  --bad:#A32A1F;--bad-bg:#FBE4E0;--ok:#2C6B3B;--ok-bg:#E1F1E5;--warn:#7A5200;--warn-bg:#FFF0C7;--none:#3B4A63;--none-bg:#E8ECF2;
  --f-body:"IBM Plex Sans KR","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#0E131B;--surface:#151C27;--surface2:#1B2431;--ink:#E7EDF5;--muted:#9DAEC4;--line:#273448;
  --accent:#7DB3F0;--on-accent:#0E131B;--accent-bg:#162A44;
  --bad:#FF9B8E;--bad-bg:#43201C;--ok:#8FD7A2;--ok-bg:#183222;--warn:#F0C25A;--warn-bg:#3A2D0E;--none:#B7C4DB;--none-bg:#232C3B;
  color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--f-body);font-size:15px;line-height:1.6;padding:0 16px}
h1,h2,h4,p{margin:0}
button,input{font:inherit;color:inherit}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.wrap{max-width:1080px;margin:0 auto}
.top{margin:0 -16px;padding:12px 16px;background:var(--surface);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
.brand{display:flex;align-items:center;gap:12px}
.mark{flex:none;width:38px;height:38px;border-radius:10px;background:var(--accent);display:grid;place-items:center}
.mark svg{stroke:var(--on-accent)}
.brand h1{font-size:18px;font-weight:700;line-height:1.25}
.brand small{display:block;font-size:12.5px;color:var(--muted)}
.layout{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(0,1fr);gap:16px;padding:24px 0 8px;align-items:start}
@media (max-width:860px){.layout{grid-template-columns:minmax(0,1fr)}}
.card{background:var(--surface);border:1px solid var(--line);border-radius:16px;min-width:0}
.chat{display:flex;flex-direction:column}
.row{display:flex;flex-wrap:wrap;align-items:center;gap:8px 10px;padding:12px 20px;border-bottom:1px solid var(--line)}
.row .lbl{font-size:13px;font-weight:600;color:var(--muted)}
.row small{font-size:12.5px;color:var(--muted)}
.seg{display:inline-flex;border:1.5px solid var(--line);border-radius:10px;overflow:hidden}
.seg.empty{border-color:var(--accent)}
.seg button{min-height:42px;padding:0 18px;border:0;background:var(--surface2);cursor:pointer;font-weight:600}
.seg button+button{border-left:1.5px solid var(--line)}
.seg button[aria-checked="true"]{background:var(--accent);color:var(--on-accent)}
.useb{min-height:36px;padding:0 14px;border-radius:999px;border:1.5px solid var(--line);background:var(--surface);cursor:pointer;font-size:14px}
.useb[aria-pressed="true"]{border-color:var(--accent);background:var(--accent-bg);color:var(--accent);font-weight:600}
.log{display:flex;flex-direction:column;gap:14px;padding:20px;height:clamp(380px,58vh,580px);overflow-y:auto;overscroll-behavior:contain}
.msg{display:flex;flex-direction:column;gap:8px;min-width:0}
.msg.user{align-self:flex-end;max-width:86%}
.bubble{padding:10px 14px;border-radius:14px;overflow-wrap:anywhere}
.msg.user .bubble{background:var(--accent);color:var(--on-accent);border-bottom-right-radius:4px}
.msg.bot .bubble{background:var(--surface2);border:1px solid var(--line);border-bottom-left-radius:4px;align-self:flex-start}
.divider{align-self:center;font-size:12.5px;color:var(--muted);background:var(--surface2);border:1px solid var(--line);padding:3px 12px;border-radius:999px}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chips-label{font-size:12.5px;color:var(--muted);font-weight:600}
.chip{min-height:40px;padding:6px 14px;border-radius:999px;border:1px solid var(--line);background:var(--surface);cursor:pointer;font-size:14px;text-align:left}
.chip:hover{border-color:var(--accent);background:var(--accent-bg)}
.chip.scope{border-style:dashed}
.chip.scope i{font-style:normal;font-size:12px;font-weight:600;color:var(--warn);margin-right:6px}
.typing{display:flex;gap:5px;padding:14px}
.typing i{width:7px;height:7px;border-radius:50%;background:var(--muted);animation:blink 1s infinite ease-in-out}
.typing i:nth-child(2){animation-delay:.15s}.typing i:nth-child(3){animation-delay:.3s}
@keyframes blink{0%,80%,100%{opacity:.25}40%{opacity:1}}
@media (prefers-reduced-motion:reduce){.typing i{animation:none;opacity:.6}}
.ans{background:var(--surface);border:1px solid var(--line);border-radius:14px;border-bottom-left-radius:4px;padding:16px 18px;display:flex;flex-direction:column;gap:12px;min-width:0}
.ans-head{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.tag{font-size:12.5px;font-weight:600;padding:2px 10px;border-radius:6px;background:var(--surface2);color:var(--muted);border:1px solid var(--line)}
.v{font-size:13px;font-weight:700;padding:3px 12px;border-radius:999px;display:inline-flex;align-items:center;gap:6px}
.v::before{content:"";width:8px;height:8px;border-radius:50%;background:currentColor}
.v-high{background:var(--bad-bg);color:var(--bad)}
.v-low{background:var(--ok-bg);color:var(--ok)}
.v-unsure{background:var(--warn-bg);color:var(--warn)}
.v-out_of_scope{background:var(--none-bg);color:var(--none)}
.concl{font-size:15.5px;font-weight:600;line-height:1.55;overflow-wrap:anywhere}
.raw{white-space:pre-wrap;font-size:14px;color:var(--muted);overflow-wrap:anywhere}
.ans h4{font-size:12.5px;font-weight:700;color:var(--muted)}
.ans ol,.ans ul{margin:4px 0 0;padding-left:20px;display:flex;flex-direction:column;gap:5px}
.ans ul.basis{list-style:none;padding:0;gap:8px}
.basis li{display:grid;grid-template-columns:auto minmax(0,1fr);gap:10px;align-items:start;font-size:14px}
.art{font-size:12px;font-weight:600;padding:2px 9px;border-radius:6px;background:var(--surface2);border:1px solid var(--line);white-space:nowrap;color:var(--muted)}
.foot{font-size:12.5px;color:var(--muted);border-top:1px solid var(--line);padding-top:10px}
.act{align-self:flex-start;min-height:40px;padding:0 14px;border-radius:8px;border:1px solid var(--accent);background:var(--accent-bg);color:var(--accent);font-weight:600;cursor:pointer}
.composer{display:flex;gap:8px;padding:14px 20px 4px;border-top:1px solid var(--line)}
.composer input{flex:1;min-width:0;min-height:46px;padding:0 14px;border-radius:10px;border:1.5px solid var(--line);background:var(--surface)}
.composer button{min-height:46px;padding:0 20px;border-radius:10px;border:0;background:var(--accent);color:var(--on-accent);font-weight:600;cursor:pointer}
.composer :disabled{opacity:.55;cursor:not-allowed}
.under{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:6px 20px 14px;font-size:12.5px;color:var(--muted)}
.linkbtn{border:0;background:none;color:var(--accent);font-weight:600;cursor:pointer;padding:0;text-decoration:underline;text-underline-offset:3px}
.side{display:flex;flex-direction:column;gap:16px}
.side .card{padding:18px 20px;display:flex;flex-direction:column;gap:10px}
.side h2{font-size:15px;font-weight:700}
.side ul{margin:0;padding-left:18px;display:flex;flex-direction:column;gap:4px;font-size:14px}
.side .out{color:var(--muted)}
.sub{font-size:12.5px;font-weight:700;color:var(--muted)}
.legend{display:flex;flex-direction:column;gap:8px;font-size:13.5px}
.legend div{display:flex;gap:10px;align-items:flex-start}
.legend .v{flex:none;font-size:12.5px;padding:2px 10px}
details summary{cursor:pointer;font-weight:600;font-size:14px}
.laws{display:grid;gap:3px;margin-top:6px;font-size:13.5px}
.laws span{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid var(--line);padding-block:4px}
.laws em{font-style:normal;color:var(--muted);font-size:12.5px;white-space:nowrap}
footer{margin-top:32px;border-top:1px solid var(--line);padding:20px 0 36px;font-size:12.5px;color:var(--muted)}
</style>
</head>
<body>
<header class="top">
  <div class="wrap brand">
    <span class="mark"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 3h6l1 4H8l1-4z"/><path d="M8 7h8v12a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2V7z"/><path d="M10 12h4M10 16h4"/></svg></span>
    <div><h1>식품 표시·광고 도우미 챗봇</h1><small>메뉴판·상세페이지·SNS 문구가 법에 걸릴 수 있는지 근거 조문과 함께 안내</small></div>
  </div>
</header>

<main class="wrap layout">
  <section class="card chat" aria-label="챗봇 대화">
    <div class="row">
      <span class="lbl" id="kind-label">식품 종류</span>
      <div class="seg empty" id="seg" role="radiogroup" aria-labelledby="kind-label">
        <button type="button" role="radio" aria-checked="false" id="kind-general" data-kind="general">일반식품</button>
        <button type="button" role="radio" aria-checked="false" id="kind-health" data-kind="health">건강기능식품</button>
      </div>
      <small id="kind-hint">먼저 식품 종류를 선택하세요</small>
    </div>
    <div class="row" role="group" aria-label="문구를 쓸 곳">
      <span class="lbl">사용처</span>
      <button type="button" class="useb" data-use="menu" aria-pressed="false">메뉴판</button>
      <button type="button" class="useb" data-use="page" aria-pressed="false">상세페이지</button>
      <button type="button" class="useb" data-use="sns" aria-pressed="false">SNS 홍보 문구</button>
      <small>선택 사항 · 다시 누르면 해제</small>
    </div>
    <div class="log" id="log" role="log" aria-live="polite" aria-label="대화 내용"></div>
    <form class="composer" id="form" autocomplete="off">
      <input type="text" id="q" maxlength="2000" disabled placeholder="먼저 식품 종류를 선택하세요" aria-label="광고 문구 또는 질문 입력">
      <button type="submit" id="send" disabled>점검</button>
    </form>
    <div class="under"><span id="hint">식품 종류를 선택하면 문구를 입력할 수 있어요.</span><button type="button" class="linkbtn" id="clear">대화 지우기</button></div>
  </section>

  <aside class="side" aria-label="안내">
    <div class="card">
      <h2>이런 분이 쓰세요</h2>
      <ul><li>카페·음식점·반찬가게 운영자 <span class="out">— 메뉴판, SNS</span></li><li>온라인 식품 판매자 <span class="out">— 상세페이지, SNS</span></li></ul>
      <p class="sub">예: “면역력 강화”, “다이어트 효과”, “혈당 관리”</p>
    </div>
    <div class="card">
      <h2>안내하는 범위</h2>
      <p class="sub">다루는 주제</p>
      <ul><li>광고 문구가 부당한 표시·광고에 해당할 수 있는지</li><li>건강기능식품 기능성 표현의 범위</li></ul>
      <p class="sub">범위 밖</p>
      <ul class="out"><li>표시사항 항목 안내</li><li>영업 신고·인허가, 위생 기준</li><li>세금, 사업자등록</li><li>화장품·의약품 광고</li><li>위법 단정, 행정처분 결과 예측</li></ul>
    </div>
    <div class="card">
      <h2>판단 단계</h2>
      <div class="legend">
        <div><span class="v v-high">위반 소지 큼</span><span>조문에 비추어 문제 될 가능성이 높음</span></div>
        <div><span class="v v-unsure">판단 어려움</span><span>맥락이나 제품 정보가 필요함</span></div>
        <div><span class="v v-low">위반 소지 낮음</span><span>사실에 맞는 표현이면 일반적으로 문제 적음</span></div>
        <div><span class="v v-out_of_scope">범위 밖</span><span>이 챗봇이 점검하지 않는 질문</span></div>
      </div>
      <p class="sub">“위법입니다”처럼 단정하지 않아요.</p>
    </div>
    <div class="card">
      <h2>근거 자료</h2>
      <details>
        <summary>목록 보기</summary>
        <div class="laws">
          <span>식품 등의 표시·광고에 관한 법률<em>법률</em></span><span>같은 법 시행령<em>시행령</em></span><span>같은 법 시행규칙<em>시행규칙</em></span>
          <span>건강기능식품에 관한 법률<em>법률</em></span><span>같은 법 시행령<em>시행령</em></span><span>같은 법 시행규칙<em>시행규칙</em></span>
          <span>식품위생법 (영업자 준수사항)<em>법률</em></span><span>식품위생법 시행규칙 (영업자 준수사항)<em>시행규칙</em></span>
          <span>식약처 고시: 부당한 표시 또는 광고의 내용 기준<em>행정규칙</em></span>
          <span>식약처 고시: 건강기능식품의 기준 및 규격<em>행정규칙</em></span>
          <span>식품안전나라 건강기능식품 인정 기능성 (I-0040, I-0050)<em>식약처</em></span>
        </div>
      </details>
    </div>
  </aside>
</main>

<footer><div class="wrap">식품 표시·광고 도우미 챗봇 · 법령 출처: 법제처 OpenAPI · 인정 기능성 출처: 식약처 식품안전나라</div></footer>

<script>
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var KIND = { general: '일반식품', health: '건강기능식품' };
  var USE = { menu: '메뉴판', page: '상세페이지', sns: 'SNS' };
  var VERDICT = { high: '위반 소지 큼', low: '위반 소지 낮음', unsure: '판단 어려움', out_of_scope: '범위 밖' };
  var CHIPS = {
    general: [
      { q: 'SNS에 “면역력 강화에 좋아요”라고 올려도 되나요?', u: 'sns' },
      { q: '상세페이지에 “다이어트 효과”라고 써도 되나요?', u: 'page' },
      { q: '메뉴판에 “혈당 관리 샐러드”라고 써도 되나요?', u: 'menu' },
      { q: '“천연 무첨가”라고 써도 되나요?', u: 'page' }
    ],
    health: [
      { q: '상세페이지에 “혈당 관리에 도움”이라고 써도 되나요?', u: 'page' },
      { q: 'SNS에 “체지방 감소에 도움을 줄 수 있음”이라고 써도 되나요?', u: 'sns' },
      { q: '인정된 기능성 표현만 써야 하나요?', u: 'sns' },
      { q: '“고혈압을 치료합니다”라고 써도 되나요?', u: 'page' }
    ]
  };
  var SCOPE_Q = '식품 제조업 영업신고는 어떻게 하나요?';
  var TIMEOUT_MS = 200000;

  var st = { sel: null, use: null, busy: false };
  var log = $('log'), inp = $('q'), send = $('send');

  /* 답변 내용은 모두 textContent 로만 넣는다 (LLM 출력·법령 본문에 HTML이 섞여도 글자로 보이게) */
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function toBottom() { log.scrollTop = log.scrollHeight; }
  function botBubble(text) { var m = el('div', 'msg bot'); m.appendChild(el('div', 'bubble', text)); log.appendChild(m); toBottom(); return m; }
  function userBubble(text) { var m = el('div', 'msg user'); m.appendChild(el('div', 'bubble', text)); log.appendChild(m); toBottom(); }

  function setBusy(b) {
    st.busy = b;
    inp.disabled = b || !st.sel;
    send.disabled = b || !st.sel;
  }

  function setUse(k) {
    st.use = k;
    Array.prototype.forEach.call(document.querySelectorAll('.useb'), function (x) {
      x.setAttribute('aria-pressed', String(x.getAttribute('data-use') === k));
    });
  }

  function detectUse(raw) {
    var s = raw.replace(/\s+/g, '').toLowerCase();
    if (/메뉴판|메뉴명|메뉴에/.test(s)) return 'menu';
    if (/상세페이지|상세설명|쇼핑몰|스마트스토어/.test(s)) return 'page';
    if (/sns|인스타|블로그|홍보문구|게시글|해시태그/.test(s)) return 'sns';
    return null;
  }

  function chipsFor(k) {
    var m = botBubble('‘' + KIND[k] + '’ 기준으로 점검할게요. 예시를 눌러 보거나 광고 문구를 직접 입력해 보세요.');
    m.appendChild(el('span', 'chips-label', '예시 문구·질문'));
    var wrap = el('div', 'chips');
    CHIPS[k].forEach(function (x) {
      var c = el('button', 'chip', x.q); c.type = 'button';
      c.addEventListener('click', function () { setUse(x.u); ask(x.q); });
      wrap.appendChild(c);
    });
    var sc = el('button', 'chip scope'); sc.type = 'button';
    sc.appendChild(el('i', null, '범위 밖 예시')); sc.appendChild(document.createTextNode(SCOPE_Q));
    sc.addEventListener('click', function () { ask(SCOPE_Q); });
    wrap.appendChild(sc);
    m.appendChild(wrap); toBottom();
  }

  function setKind(k) {
    var first = st.sel === null;
    st.sel = k;
    Array.prototype.forEach.call(document.querySelectorAll('#seg button'), function (b) {
      b.setAttribute('aria-checked', String(b.getAttribute('data-kind') === k));
    });
    $('seg').classList.remove('empty');
    $('kind-hint').textContent = '언제든 바꿀 수 있어요';
    inp.placeholder = '예: ' + CHIPS[k][0].q;
    $('hint').textContent = '선택한 식품 종류: ' + KIND[k];
    setBusy(st.busy);
    if (first) { chipsFor(k); inp.focus(); }
    else { log.appendChild(el('div', 'divider', '식품 종류를 ‘' + KIND[k] + '’(으)로 바꿨어요')); toBottom(); }
  }

  function renderAnswer(a, sel, use, q) {
    var m = el('div', 'msg bot');
    var box = el('article', 'ans');
    var head = el('div', 'ans-head');
    head.appendChild(el('span', 'v v-' + a.verdict, VERDICT[a.verdict] || a.verdict));
    if (a.verdict !== 'out_of_scope') {
      head.appendChild(el('span', 'tag', KIND[sel]));
      if (use) head.appendChild(el('span', 'tag', USE[use]));
    }
    box.appendChild(head);
    if (a.verdict_reason) box.appendChild(el('p', 'concl', a.verdict_reason));
    if (a.raw_fallback) box.appendChild(el('p', 'raw', a.raw_fallback));

    if (a.actions && a.actions.length) {
      var outScope = a.verdict === 'out_of_scope';
      box.appendChild(el('h4', null, outScope ? '안내' : '해야 할 일'));
      var list = el(outScope ? 'ul' : 'ol');
      a.actions.forEach(function (s) { list.appendChild(el('li', null, s)); });
      box.appendChild(list);
    }

    if (a.basis && a.basis.length) {
      box.appendChild(el('h4', null, '근거'));
      var ul = el('ul', 'basis');
      a.basis.forEach(function (b) {
        var li = el('li'), d = el('div');
        if (b.type === 'law') {
          li.appendChild(el('span', 'art', b.article));
          d.appendChild(el('b', null, b.law_name));
        } else {
          li.appendChild(el('span', 'art', '제' + b.recog_no + '호'));
          d.appendChild(el('b', null, b.material));
          d.appendChild(document.createTextNode(' · 인정 문구: ' + b.claim));
        }
        if (b.summary) d.appendChild(document.createTextNode(' · ' + b.summary));
        li.appendChild(d); ul.appendChild(li);
      });
      box.appendChild(ul);
    }

    if (a.food_type_mismatch) {
      var other = sel === 'general' ? 'health' : 'general';
      var act = el('button', 'act', '‘' + KIND[other] + '’으로 바꾸고 다시 점검'); act.type = 'button';
      act.addEventListener('click', function () {
        if (st.busy) return;
        setKind(other); userBubble(q); reply(q);
      });
      box.appendChild(act);
    }

    box.appendChild(el('p', 'foot', '수집 기준일 ' + (a.collected_at || '-') + ' · ' + a.disclaimer));
    m.appendChild(box); log.appendChild(m); toBottom();
  }

  function errorText(body, status) {
    var d = body && body.detail;
    if (typeof d === 'string') return d;
    if (status === 422) return '입력값을 확인해 주세요.';
    return 'HTTP ' + status;
  }

  function reply(q) {
    var sel = st.sel, use = st.use;
    var m = el('div', 'msg bot'); var t = el('div', 'bubble typing'); t.setAttribute('aria-label', '점검 중');
    t.appendChild(el('i')); t.appendChild(el('i')); t.appendChild(el('i')); m.appendChild(t);
    log.appendChild(m); toBottom();
    setBusy(true);
    var ctrl = new AbortController();
    var timer = setTimeout(function () { ctrl.abort(); }, TIMEOUT_MS);
    fetch('/rag/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: q, food_type: sel, usage: use }),
      signal: ctrl.signal
    })
      .then(function (r) {
        return r.text().then(function (text) {
          var body = {};
          try { body = JSON.parse(text); } catch (e) { body = {}; }
          if (!r.ok) throw new Error(errorText(body, r.status));
          return body;
        });
      })
      .then(function (a) { m.remove(); renderAnswer(a, sel, use, q); })
      .catch(function (e) {
        m.remove();
        botBubble('답변을 받지 못했어요. 잠시 후 다시 시도해 주세요. (' + (e.name === 'AbortError' ? '응답 시간이 초과됐어요' : e.message) + ')');
      })
      .finally(function () { clearTimeout(timer); setBusy(false); inp.focus(); });
  }

  function ask(q) {
    q = (q || '').trim();
    if (!q || !st.sel || st.busy) return;
    var d = detectUse(q); if (d) setUse(d);
    userBubble(q); reply(q);
  }

  Array.prototype.forEach.call(document.querySelectorAll('#seg button'), function (b) {
    b.addEventListener('click', function () {
      var k = b.getAttribute('data-kind');
      if (k !== st.sel && !st.busy) setKind(k);
    });
  });
  Array.prototype.forEach.call(document.querySelectorAll('.useb'), function (x) {
    x.addEventListener('click', function () { var k = x.getAttribute('data-use'); setUse(st.use === k ? null : k); });
  });
  $('form').addEventListener('submit', function (e) { e.preventDefault(); var v = inp.value; inp.value = ''; ask(v); });

  function intro() {
    log.innerHTML = '';
    botBubble('안녕하세요. 카페·음식점·반찬가게, 온라인 식품 판매자의 메뉴판·상세페이지·SNS 문구가 부당한 표시·광고에 해당할 수 있는지 법령 근거와 함께 안내해 드려요. 먼저 위에서 식품 종류를 선택해 주세요.');
    if (st.sel) chipsFor(st.sel);
  }
  $('clear').addEventListener('click', function () { if (!st.busy) intro(); });
  intro();
})();
</script>
</body>
</html>
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_web_page.py -v`
Expected: 5 passed.

- [ ] **Step 5: 화면 렌더링 점검 (서버 없이)**

Run: `python -m http.server 8000 --directory web` 후 브라우저에서 `http://localhost:8000`을 연다.
Expected:
- 입력창과 점검 버튼이 잠겨 있다. `건강기능식품`을 누르면 토글이 파란색으로 바뀌고 예시 칩 4개 + 범위 밖 칩 1개가 나온다. 다른 쪽을 누르면 “식품 종류를 ‘일반식품’(으)로 바꿨어요” 구분선이 나온다.
- 칩을 누르면 사용처 버튼이 자동 선택되고, 서버가 없으므로 “답변을 받지 못했어요 … (HTTP 404)” 말풍선이 나오며 입력창이 다시 열린다.
- 브라우저 개발자 도구 콘솔에서 아래를 실행해 `<b>`가 굵게 보이지 않고 글자 그대로 보이는지 확인한다(Review Focus 2):
  `document.querySelector('.msg.bot .bubble').textContent = '<b>태그</b>'`
  그리고 `renderAnswer`는 `textContent`만 쓰므로 같은 결과가 된다. (`grep -n "innerHTML" web/index.html` → `log.innerHTML = ''` 한 곳만 나와야 한다.)
- 창 너비를 400px로 줄여도 가로 스크롤 없이 한 칸으로 쌓인다.

`Ctrl+C`로 서버를 끈다.

- [ ] **Step 6: Commit**

```bash
git add web/index.html tests/test_web_page.py
git commit -m "데모 화면 기반 웹 화면 추가 (식품 종류 토글, API 연결)"
```

---

### Task 11: API 서버 (`rag_server.py`)

**Files:**
- Create: `scripts/rag/rag_server.py`, `tests/test_rag_server.py`

**Interfaces:**
- Consumes: Task 1 `ROOT, loadConfig, getOsClient`; Task 6 `LAW_INDEX, MATERIAL_INDEX, ensurePipeline`; Task 8 `DISCLAIMER`; Task 9 `runFoodRag, ensureCacheIndex, getRedisClient, lookupCache, storeCache`; Task 10 `web/`
- Produces: `app`(FastAPI), `POST /rag/query`, `GET /rag/health`, `GET /rag/status`, `GET /`(정적 화면). CLI `python scripts/rag/rag_server.py` (포트 5000)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_rag_server.py`:
```python
import pytest
from fastapi.testclient import TestClient

import rag_server
from answer_format import DISCLAIMER

SAMPLE = {"success": True, "verdict": "high", "verdict_reason": "이유", "actions": ["빼기"],
          "basis": [{"type": "law", "law_name": "식품 등의 표시·광고에 관한 법률", "article": "제8조 1항",
                     "summary": "요약", "effective_date": "20250101"}],
          "out_of_scope_reason": None, "food_type_mismatch": False, "collected_at": "2026-10-16",
          "disclaimer": DISCLAIMER, "raw_fallback": ""}


@pytest.fixture
def env(monkeypatch):
    calls = {"stored": 0, "rag": [], "cached": None, "result": dict(SAMPLE), "error": None}

    def fakeLookup(osClient, redisClient, cfg, docType, query, scope=None):
        calls["scope"] = scope
        return calls["cached"], [0.0]

    def fakeStore(*args, **kwargs):
        calls["stored"] += 1

    def fakeRag(osClient, cfg, query, foodType, usage=None, queryVector=None):
        if calls["error"]:
            raise calls["error"]
        calls["rag"].append((query, foodType, usage))
        return calls["result"]

    monkeypatch.setattr(rag_server, "lookupCache", fakeLookup)
    monkeypatch.setattr(rag_server, "storeCache", fakeStore)
    monkeypatch.setattr(rag_server, "runFoodRag", fakeRag)
    return TestClient(rag_server.app), calls


def post(client, **body):
    return client.post("/rag/query", json=body)


def test_query_runs_rag_and_stores_cache(env):
    client, calls = env
    r = post(client, query="  혈당 관리 샐러드  ", food_type="general", usage="menu")
    assert r.status_code == 200 and r.json()["verdict"] == "high"
    assert calls["rag"] == [("혈당 관리 샐러드", "general", "menu")]
    assert calls["scope"] == "general:menu" and calls["stored"] == 1


def test_scope_without_usage(env):
    client, calls = env
    post(client, query="문구", food_type="health")
    assert calls["scope"] == "health:_"


def test_blank_and_too_long_query_are_400(env):
    client, _ = env
    assert post(client, query="   ", food_type="general").status_code == 400
    r = post(client, query="가" * 2001, food_type="general")
    assert r.status_code == 400 and "2000자" in r.json()["detail"]


def test_bad_or_missing_food_type_is_422(env):
    client, _ = env
    assert post(client, query="문구", food_type="cosmetic").status_code == 422
    assert post(client, query="문구").status_code == 422
    assert post(client, query="문구", food_type="general", usage="tv").status_code == 422


def test_cache_hit_skips_rag(env):
    client, calls = env
    calls["cached"] = dict(SAMPLE, verdict="low")
    r = post(client, query="문구", food_type="general")
    assert r.json()["verdict"] == "low" and calls["rag"] == [] and calls["stored"] == 0


def test_parse_failure_result_is_not_cached(env):
    client, calls = env
    calls["result"] = dict(SAMPLE, verdict="unsure", basis=[], raw_fallback="형식 없는 답")
    r = post(client, query="문구", food_type="general")
    assert r.status_code == 200 and r.json()["raw_fallback"] == "형식 없는 답"
    assert calls["stored"] == 0


def test_backend_failure_is_500_with_detail(env):
    client, calls = env
    calls["error"] = ConnectionError("Ollama 연결 실패")
    r = post(client, query="문구", food_type="general")
    assert r.status_code == 500 and "Ollama 연결 실패" in r.json()["detail"]


def test_root_serves_web_page(env):
    client, _ = env
    r = client.get("/")
    assert r.status_code == 200 and 'id="kind-general"' in r.text


def test_health(env):
    client, _ = env
    assert client.get("/rag/health").json()["status"] == "ok"
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_rag_server.py -v`
Expected: `ModuleNotFoundError: No module named 'rag_server'`

- [ ] **Step 3: `rag_server.py` 작성**

`scripts/rag/rag_server.py`:
```python
# -*- coding: utf-8 -*-
"""
rag_server.py
FastAPI 서버 — 식품 표시·광고 점검 API와 웹 화면(web/index.html)을 함께 제공.
포트 5000. Swagger UI: http://localhost:5000/docs

엔드포인트:
  POST /rag/query  : 광고 문구 점검 (캐시 → 검색 → LLM 1회)
  GET  /rag/health : 서버 상태
  GET  /rag/status : 인덱스 문서 수·임베딩 수
  GET  /           : 웹 화면

사용법:
  python scripts/rag/rag_server.py
"""

# ============================================================
# 라이브러리 임포트
# ============================================================

import os
import sys
from contextlib import asynccontextmanager
from typing import Literal, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from food_common import ROOT, getOsClient, loadConfig
from qa_cache import ensureCacheIndex, getRedisClient, lookupCache, storeCache
from rag_pipeline import runFoodRag
from search_hybrid import LAW_INDEX, MATERIAL_INDEX, ensurePipeline


# ============================================================
# 상수 / 공유 클라이언트
# ============================================================

MAX_QUERY_LEN = 2000
state = {"cfg": None, "osClient": None, "redisClient": None}


@asynccontextmanager
async def lifespan(app):
    """서버 시작 시 OpenSearch/Redis 클라이언트, 검색 파이프라인, 캐시 인덱스 초기화."""
    state["cfg"]         = loadConfig()
    state["osClient"]    = getOsClient(state["cfg"])
    state["redisClient"] = getRedisClient(state["cfg"])
    ensurePipeline(state["osClient"])
    ensureCacheIndex(state["osClient"])
    print("[INFO] RAG 서버 초기화 완료 — http://localhost:5000")
    yield


app = FastAPI(
    title="식품 표시·광고 도우미 — RAG API",
    description="식품표시광고법·건강기능식품법·식품위생법·식약처 고시·인정 기능성 기반 광고 문구 점검",
    version="1.0.0",
    lifespan=lifespan,
)


# ============================================================
# 요청/응답 스키마
# ============================================================

class QueryRequest(BaseModel):
    query:     str
    food_type: Literal["general", "health"]
    usage:     Optional[Literal["menu", "page", "sns"]] = None


class BasisItem(BaseModel):
    type:           Literal["law", "material"]
    law_name:       Optional[str] = None
    article:        Optional[str] = None
    effective_date: Optional[str] = None
    material:       Optional[str] = None
    recog_no:       Optional[str] = None
    claim:          Optional[str] = None
    summary:        str = ""


class QueryResponse(BaseModel):
    success:             bool
    verdict:             Literal["high", "low", "unsure", "out_of_scope"]
    verdict_reason:      str = ""
    actions:             list[str] = []
    basis:               list[BasisItem] = []
    out_of_scope_reason: Optional[Literal["topic", "no_basis"]] = None
    food_type_mismatch:  bool = False
    collected_at:        Optional[str] = None
    disclaimer:          str
    raw_fallback:        str = ""


# ============================================================
# 엔드포인트
# ============================================================

@app.get("/rag/health", tags=["시스템"])
def health():
    cfg = state["cfg"]
    return {"status": "ok", "model": cfg['llmModel'] if cfg else "unknown"}


@app.get("/rag/status", tags=["시스템"])
def status():
    """두 인덱스의 문서 수와 임베딩된 문서 수."""
    try:
        out = {"success": True}
        for name in (LAW_INDEX, MATERIAL_INDEX):
            out[name] = {
                "docs":     state["osClient"].count(index=name)["count"],
                "embedded": state["osClient"].count(index=name, body={"query": {"exists": {"field": "knn_vector"}}})["count"],
            }
        return out
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/rag/query", response_model=QueryResponse, tags=["챗봇"])
def ragQuery(req: QueryRequest):
    """광고 문구를 받아 위반 소지·해야 할 일·근거를 반환."""
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="문구를 입력해 주세요.")
    if len(query) > MAX_QUERY_LEN:
        raise HTTPException(status_code=400, detail=f"문구는 {MAX_QUERY_LEN}자 이내로 입력해 주세요.")

    scope = f"{req.food_type}:{req.usage or '_'}"
    try:
        cached, queryVector = lookupCache(state["osClient"], state["redisClient"], state["cfg"],
                                          "food", query, scope=scope)
        if cached:
            return QueryResponse(**cached)
        result = runFoodRag(state["osClient"], state["cfg"], query, req.food_type,
                            usage=req.usage, queryVector=queryVector)
        if not result.get("raw_fallback"):    # 형식이 깨진 답변은 7일 동안 재사용되지 않게 저장하지 않음
            storeCache(state["osClient"], state["redisClient"], state["cfg"], "food", query, result,
                       scope=scope, queryVector=queryVector)
        return QueryResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"점검 중 오류가 발생했습니다: {e}")


# 정적 화면은 API 라우트 다음에 마운트해야 /rag/* 를 가리지 않는다
app.mount("/", StaticFiles(directory=str(ROOT / "web"), html=True), name="web")


# ============================================================
# 메인
# ============================================================

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_rag_server.py -v`
Expected: 9 passed.

- [ ] **Step 5: 전체 테스트**

Run: `python -m pytest -v`
Expected: 모든 테스트 통과(약 89개), 실패 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/rag/rag_server.py tests/test_rag_server.py
git commit -m "FastAPI 점검 API와 웹 화면 제공 서버 추가"
```

---

### Task 12: 캐시 워밍, 월 1회 갱신, README

**Files:**
- Create: `scripts/rag/warm_cache.py`, `scripts/run_monthly.py`, `tests/test_warm_cache.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: 실행 중인 `/rag/query`; Task 3~5 CLI
- Produces: `warm_cache.FAQS: list[dict]`(키 `query, food_type, usage`), `run_monthly.STEPS: list[list[str]]`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_warm_cache.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from run_monthly import STEPS  # noqa: E402
from warm_cache import FAQS  # noqa: E402


def test_faqs_are_valid_requests():
    assert len(FAQS) >= 10
    for f in FAQS:
        assert f["query"].strip()
        assert f["food_type"] in ("general", "health")
        assert f["usage"] in (None, "menu", "page", "sns")


def test_monthly_steps_order():
    names = [Path(step[0]).name for step in STEPS]
    assert names == ["collect_law.py", "collect_admrul.py", "index_materials.py", "embed_index.py"]
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_warm_cache.py -v`
Expected: `ModuleNotFoundError: No module named 'run_monthly'`

- [ ] **Step 3: `warm_cache.py` 작성**

`scripts/rag/warm_cache.py`:
```python
# -*- coding: utf-8 -*-
"""
warm_cache.py
자주 나올 문구(개요서 05장 대표 입력 + 화면 예시 칩)를 미리 /rag/query 에 보내 캐시를 채운다.
전제: rag_server.py 가 실행 중이어야 함 (포트 5000).

사용법:
  python scripts/rag/warm_cache.py
  python scripts/rag/warm_cache.py --base-url http://localhost:5000
"""

import argparse
import time

import requests

FAQS = [
    {"query": "SNS에 “면역력 강화에 좋아요”라고 올려도 되나요?",              "food_type": "general", "usage": "sns"},
    {"query": "상세페이지에 “다이어트 효과”라고 써도 되나요?",                 "food_type": "general", "usage": "page"},
    {"query": "메뉴판에 “혈당 관리 샐러드”라고 써도 되나요?",                  "food_type": "general", "usage": "menu"},
    {"query": "“천연 무첨가”라고 써도 되나요?",                               "food_type": "general", "usage": "page"},
    {"query": "우리 카페 홍삼차, 혈당 관리에 최고!",                           "food_type": "general", "usage": "sns"},
    {"query": "식품 제조업 영업신고는 어떻게 하나요?",                         "food_type": "general", "usage": None},
    {"query": "상세페이지에 “혈당 관리에 도움”이라고 써도 되나요?",            "food_type": "health",  "usage": "page"},
    {"query": "SNS에 “체지방 감소에 도움을 줄 수 있음”이라고 써도 되나요?",    "food_type": "health",  "usage": "sns"},
    {"query": "인정된 기능성 표현만 써야 하나요?",                             "food_type": "health",  "usage": "sns"},
    {"query": "“고혈압을 치료합니다”라고 써도 되나요?",                        "food_type": "health",  "usage": "page"},
    {"query": "우리 카페 홍삼차, 혈당 관리에 최고!",                           "food_type": "health",  "usage": "sns"},
    {"query": "식품 제조업 영업신고는 어떻게 하나요?",                         "food_type": "health",  "usage": None},
]


def warmFaqs(baseUrl):
    for i, item in enumerate(FAQS, start=1):
        start = time.time()
        try:
            resp = requests.post(f"{baseUrl}/rag/query", json=item, timeout=300)
            resp.raise_for_status()
            print(f"  [{i}/{len(FAQS)}] ({time.time() - start:5.1f}s) {resp.json()['verdict']:<12} {item['query']}")
        except Exception as e:
            print(f"  [{i}/{len(FAQS)}] 실패: {item['query']} — {e}")


def main():
    parser = argparse.ArgumentParser(description="FAQ 캐시 워밍업")
    parser.add_argument("--base-url", default="http://localhost:5000")
    warmFaqs(parser.parse_args().base_url)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: `run_monthly.py` 작성**

`scripts/run_monthly.py`:
```python
# -*- coding: utf-8 -*-
"""
run_monthly.py
월 1회 갱신: 법령 → 고시 → 인정 기능성 → 임베딩 순서로 실행. 바뀐 조문만 다시 인덱싱·임베딩된다.
한 단계가 실패(종료 코드 0이 아님)하면 멈춘다. 결과는 logs/collect.jsonl 에 남는다.

사용법:
  python scripts/run_monthly.py
Windows 작업 스케줄러에 등록할 때는 '시작 위치'를 저장소 루트로 지정한다.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

STEPS = [
    ["scripts/collect/collect_law.py"],
    ["scripts/collect/collect_admrul.py"],
    ["scripts/collect/index_materials.py"],
    ["scripts/rag/embed_index.py", "--index", "all"],
]


def main():
    for step in STEPS:
        print(f"\n===== {' '.join(step)} =====")
        code = subprocess.run([sys.executable, *step], cwd=ROOT).returncode
        if code != 0:
            print(f"[중단] {step[0]} 종료 코드 {code}")
            sys.exit(code)
    print("\n[완료] 월 1회 갱신 끝 — logs/collect.jsonl 확인")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_warm_cache.py -v`
Expected: 2 passed.

- [ ] **Step 6: README 갱신**

`README.md` 전체를 다음으로 바꾼다:
````markdown
# 식품 표시·광고 도우미 챗봇

소상공인(카페·음식점·반찬가게, 온라인 식품 판매자)을 위한 RAG 기반 식품 표시·광고 도우미 챗봇.
메뉴판·상세페이지·SNS 문구가 법에 걸릴 수 있는지 근거 조문과 함께 안내합니다.

- 개요: `식품 표시·광고 점검 챗봇 개요서.md`
- 설계: `docs/superpowers/specs/2026-10-15-food-ad-helper-design.md`
- 구현 계획: `docs/superpowers/plans/2026-10-15-food-ad-helper.md`

## 준비

1. `pip install -r requirements.txt`
2. `.env.example`을 `.env`로 복사하고 `LAW_OC`, OpenSearch·Redis 값을 넣습니다.
3. OpenSearch(neural-search 플러그인 포함), Redis, Ollama를 실행하고 모델을 받습니다.

       ollama pull bge-m3
       ollama pull gemma4:e4b

## 데이터 만들기 (처음 한 번, 이후 월 1회)

    python scripts/run_monthly.py

단계별로 실행하려면:

    python scripts/collect/collect_law.py        # 법률·시행령·시행규칙 8개 (--offline: data/law 저장본 사용)
    python scripts/collect/collect_admrul.py     # 식약처 고시 2개
    python scripts/collect/index_materials.py    # 식약처 인정 기능성 731건
    python scripts/rag/embed_index.py            # 두 인덱스 임베딩

식품안전나라 원본을 다시 받아야 할 때만: `FOODSAFETY_KEY`를 넣고 `python scripts/collect/fetch_foodsafety.py` → `python scripts/collect/build_materials.py`.

수집 이력: `logs/collect.jsonl`(실행 결과), `logs/law_history.jsonl`(조문 변경).

## 실행

    python scripts/rag/rag_server.py

- 화면: http://localhost:5000
- API 문서: http://localhost:5000/docs
- 캐시 미리 채우기(서버 실행 중): `python scripts/rag/warm_cache.py`

## 테스트와 평가

    python -m pytest                     # 단위 테스트 (OpenSearch·Ollama 없이)
    python eval/eval_retrieval.py        # 검색 방식별 hit@5 → eval/report_retrieval.md
    python eval/eval_answers.py          # 답변 지표 (서버 실행 중) → eval/report_answers.md

## 폴더

- `scripts/collect/` 수집·적재, `scripts/rag/` 검색·답변·서버, `scripts/common/` 공통
- `web/` 화면, `eval/` 평가 문구와 스크립트, `tests/` 단위 테스트
- `data/law/` 법제처 원본, `data/foodsafety/` 식품안전나라 원본과 정제본
````

- [ ] **Step 7: Commit**

```bash
git add scripts/rag/warm_cache.py scripts/run_monthly.py tests/test_warm_cache.py README.md
git commit -m "캐시 워밍, 월 1회 갱신 스크립트, README 실행 방법 추가"
```

---

### Task 13: 평가 (`eval/`)

**Files:**
- Create: `eval/metrics.py`, `eval/questions.jsonl`, `eval/eval_retrieval.py`, `eval/eval_answers.py`, `tests/test_metrics.py`

**Interfaces:**
- Consumes: Task 6 `searchLaw(..., mode=...)`, `ensurePipeline`; Task 7 `formatArticle`; 실행 중인 `/rag/query`
- Produces:
  - `metrics.articleKey(lawName, article) -> str` (`"법령명 제8조"`, `"법령명 별표 1"`)
  - `metrics.hitAtK(lawHits, gold) -> bool`, `metrics.scoreAnswer(question, resp) -> dict[str, bool | None]`, `metrics.summarize(rows) -> dict[str, (hit, total)]`, `metrics.METRIC_LABELS`
  - `questions.jsonl` 행 키: `id, query, food_type, usage, category(in_scope|variant|out_of_scope|no_basis), expected_verdict, gold_basis(list[str]), gold_recog_no(list[str])`
  - 보고서: `eval/report_retrieval.md`, `eval/report_answers.md`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_metrics.py`:
```python
from metrics import METRIC_LABELS, articleKey, hitAtK, scoreAnswer, summarize

LAW = "식품 등의 표시·광고에 관한 법률"


def test_articleKey_drops_clause():
    assert articleKey(LAW, "제8조 1항") == f"{LAW} 제8조"
    assert articleKey(LAW, "제3조의2") == f"{LAW} 제3조의2"
    assert articleKey(LAW, "별표 1") == f"{LAW} 별표 1"


def test_hitAtK_matches_on_article_level():
    hits = [{"law_name": LAW, "article_no": "8", "clause_no": "2"}]
    assert hitAtK(hits, [f"{LAW} 제8조"]) is True
    assert hitAtK(hits, [f"{LAW} 제9조"]) is False


def question(**kw):
    base = {"category": "in_scope", "food_type": "general", "expected_verdict": "high",
            "gold_basis": [f"{LAW} 제8조"], "gold_recog_no": []}
    base.update(kw)
    return base


def response(**kw):
    base = {"verdict": "high", "verdict_reason": "위반 소지가 큽니다.", "actions": ["표현을 뺍니다."],
            "basis": [{"type": "law", "law_name": LAW, "article": "제8조 1항"}]}
    base.update(kw)
    return base


def test_scoreAnswer_in_scope_all_good():
    s = scoreAnswer(question(), response())
    assert s == {"verdict_match": True, "basis_shown": True, "no_decisive": True, "citation_match": True}


def test_scoreAnswer_detects_decisive_wording_and_missing_basis():
    s = scoreAnswer(question(), response(verdict_reason="이 문구는 위법입니다.", basis=[]))
    assert s["no_decisive"] is False and s["basis_shown"] is False and s["citation_match"] is False


def test_scoreAnswer_citation_not_applicable_without_gold():
    assert scoreAnswer(question(gold_basis=[]), response())["citation_match"] is None


def test_scoreAnswer_refusal():
    s = scoreAnswer(question(category="out_of_scope", expected_verdict="out_of_scope"),
                    response(verdict="out_of_scope", basis=[]))
    assert s == {"verdict_match": True, "refusal_ok": True}


def test_scoreAnswer_material_match():
    q = question(food_type="health", gold_recog_no=["2024-20"])
    good = response(basis=[{"type": "material", "recog_no": "2024-20", "material": "홍삼"}])
    assert scoreAnswer(q, good)["material_match"] is True
    assert scoreAnswer(q, response())["material_match"] is False


def test_summarize_counts_only_applicable():
    rows = [{"verdict_match": True, "citation_match": None}, {"verdict_match": False, "citation_match": True}]
    assert summarize(rows) == {"verdict_match": (1, 2), "citation_match": (1, 1)}
    assert set(METRIC_LABELS) >= {"verdict_match", "basis_shown", "no_decisive", "citation_match",
                                  "refusal_ok", "material_match"}
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_metrics.py -v`
Expected: `ModuleNotFoundError: No module named 'metrics'`

- [ ] **Step 3: `metrics.py` 작성**

`eval/metrics.py`:
```python
# -*- coding: utf-8 -*-
"""
metrics.py
평가 지표 계산 (순수 함수). 정답 근거는 "법령명 제n조" / "법령명 별표 n" 단위로 비교한다(항은 무시).
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "common"))
from answer_format import formatArticle

DECISIVE_RE = re.compile(r"위법입니다|불법입니다|위반입니다")
ARTICLE_RE  = re.compile(r"(제\d+조(?:의\d+)?|별표\s*\d+(?:의\d+)?)")

METRIC_LABELS = {
    "hit_at_5":       "근거 검색 적중률 (hit@5)",
    "basis_shown":    "근거 표기율",
    "refusal_ok":     "거절 정확도",
    "citation_match": "인용 일치율",
    "no_decisive":    "단정 회피율",
    "verdict_match":  "판단 일치율",
    "material_match": "인정 문구 대조 정확도",
}


def articleKey(lawName, article):
    m = ARTICLE_RE.search(article or "")
    return f"{lawName} {m.group(1) if m else article}"


def hitAtK(lawHits, gold):
    keys = {articleKey(h["law_name"], formatArticle(h["article_no"], h["clause_no"])) for h in lawHits}
    return bool(keys & set(gold))


def basisKeys(basis):
    return {articleKey(b["law_name"], b["article"]) for b in basis if b.get("type") == "law"}


def recogNos(basis):
    return {b["recog_no"] for b in basis if b.get("type") == "material"}


def scoreAnswer(q, resp):
    """문구 하나의 지표별 결과. 해당 없는 지표는 넣지 않거나 None."""
    out = {"verdict_match": resp["verdict"] == q["expected_verdict"]}
    if q["category"] in ("in_scope", "variant"):
        text = (resp.get("verdict_reason") or "") + " " + " ".join(resp.get("actions") or [])
        out["basis_shown"]    = any(b.get("type") == "law" for b in resp.get("basis") or [])
        out["no_decisive"]    = DECISIVE_RE.search(text) is None
        out["citation_match"] = bool(basisKeys(resp.get("basis") or []) & set(q["gold_basis"])) if q["gold_basis"] else None
    else:
        out["refusal_ok"] = resp["verdict"] == "out_of_scope"
    if q["food_type"] == "health" and q.get("gold_recog_no"):
        out["material_match"] = out["verdict_match"] and bool(set(q["gold_recog_no"]) & recogNos(resp.get("basis") or []))
    return out


def summarize(rows):
    """{지표: (맞은 수, 대상 수)}. None은 대상에서 뺀다."""
    total = {}
    for row in rows:
        for key, value in row.items():
            if value is None:
                continue
            hit, n = total.get(key, (0, 0))
            total[key] = (hit + (1 if value else 0), n + 1)
    return total


def formatTable(summary, order=None):
    lines = ["| 지표 | 결과 | 비율 |", "|---|---|---|"]
    for key in order or summary:
        if key in summary:
            hit, n = summary[key]
            lines.append(f"| {METRIC_LABELS.get(key, key)} | {hit}/{n} | {hit / n * 100:.1f}% |")
    return "\n".join(lines)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_metrics.py -v`
Expected: 8 passed.

- [ ] **Step 5: 평가 문구 세트 작성**

`gold_basis`는 Task 3 수집 후 A 담당이 `"법령명 제n조"` 또는 `"법령명 별표 n"`으로 채운다(비어 있으면 인용 일치율·검색 적중률 대상에서 빠지고 보고서에 "정답 미정"으로 센다). `gold_recog_no`는 `materials.jsonl`에서 확인한 값이다(2024-20 홍삼 혈당 조절, 2006-21·2006-22·2005-16 공액리놀레산 체지방 감소).

`eval/questions.jsonl`:
```
{"id": "g01", "query": "SNS에 “면역력 강화에 좋아요”라고 올려도 되나요?", "food_type": "general", "usage": "sns", "category": "in_scope", "expected_verdict": "high", "gold_basis": [], "gold_recog_no": []}
{"id": "g02", "query": "상세페이지에 “다이어트 효과”라고 써도 되나요?", "food_type": "general", "usage": "page", "category": "in_scope", "expected_verdict": "high", "gold_basis": [], "gold_recog_no": []}
{"id": "g03", "query": "메뉴판에 “혈당 관리 샐러드”라고 써도 되나요?", "food_type": "general", "usage": "menu", "category": "in_scope", "expected_verdict": "high", "gold_basis": [], "gold_recog_no": []}
{"id": "g04", "query": "상세페이지에 “먹으면 혈당이 내려갑니다”라고 써도 되나요?", "food_type": "general", "usage": "page", "category": "in_scope", "expected_verdict": "high", "gold_basis": [], "gold_recog_no": []}
{"id": "g05", "query": "우리 카페 홍삼차, 혈당 관리에 최고!", "food_type": "general", "usage": "sns", "category": "in_scope", "expected_verdict": "high", "gold_basis": [], "gold_recog_no": []}
{"id": "g06", "query": "상세페이지에 “천연 무첨가”라고 써도 되나요?", "food_type": "general", "usage": "page", "category": "in_scope", "expected_verdict": "unsure", "gold_basis": [], "gold_recog_no": []}
{"id": "g07", "query": "메뉴판에 “국내산 쌀 100% 사용”이라고 써도 되나요? 실제로 국내산 쌀만 씁니다.", "food_type": "general", "usage": "menu", "category": "in_scope", "expected_verdict": "low", "gold_basis": [], "gold_recog_no": []}
{"id": "g08", "query": "SNS에 “암 예방에 좋은 버섯 반찬”이라고 올려도 되나요?", "food_type": "general", "usage": "sns", "category": "in_scope", "expected_verdict": "high", "gold_basis": [], "gold_recog_no": []}
{"id": "h01", "query": "홍삼 건강기능식품 상세페이지에 “혈당 조절에 도움을 줄 수 있음”이라고 써도 되나요?", "food_type": "health", "usage": "page", "category": "in_scope", "expected_verdict": "low", "gold_basis": [], "gold_recog_no": ["2024-20"]}
{"id": "h02", "query": "홍삼 건강기능식품을 SNS에 “당뇨를 치료합니다”라고 홍보해도 되나요?", "food_type": "health", "usage": "sns", "category": "in_scope", "expected_verdict": "high", "gold_basis": [], "gold_recog_no": ["2024-20"]}
{"id": "h03", "query": "공액리놀레산 제품 상세페이지에 “과체중인 성인의 체지방 감소에 도움을 줄 수 있음”이라고 써도 되나요?", "food_type": "health", "usage": "page", "category": "in_scope", "expected_verdict": "low", "gold_basis": [], "gold_recog_no": ["2006-21", "2006-22", "2005-16"]}
{"id": "h04", "query": "공액리놀레산 제품을 SNS에 “한 달에 10kg 감량 보장”이라고 홍보해도 되나요?", "food_type": "health", "usage": "sns", "category": "in_scope", "expected_verdict": "high", "gold_basis": [], "gold_recog_no": ["2006-21", "2006-22", "2005-16"]}
{"id": "h05", "query": "상세페이지에 “고혈압을 치료합니다”라고 써도 되나요?", "food_type": "health", "usage": "page", "category": "in_scope", "expected_verdict": "high", "gold_basis": [], "gold_recog_no": []}
{"id": "v-g01", "query": "인스타에 면역력 키워주는 음식이라고 올리면 문제 될까요?", "food_type": "general", "usage": "sns", "category": "variant", "expected_verdict": "high", "gold_basis": [], "gold_recog_no": []}
{"id": "v-g02", "query": "쇼핑몰 설명에 살 빠지는 효과 있다고 적어도 돼요?", "food_type": "general", "usage": "page", "category": "variant", "expected_verdict": "high", "gold_basis": [], "gold_recog_no": []}
{"id": "v-g03", "query": "메뉴 이름을 혈당 잡는 샐러드로 해도 괜찮나요?", "food_type": "general", "usage": "menu", "category": "variant", "expected_verdict": "high", "gold_basis": [], "gold_recog_no": []}
{"id": "v-g04", "query": "이거 먹으면 혈당 수치 떨어진다고 상세페이지에 써도 되나요", "food_type": "general", "usage": "page", "category": "variant", "expected_verdict": "high", "gold_basis": [], "gold_recog_no": []}
{"id": "v-g05", "query": "홍삼라떼 혈당 관리 최고라고 SNS에 올릴까 하는데요", "food_type": "general", "usage": "sns", "category": "variant", "expected_verdict": "high", "gold_basis": [], "gold_recog_no": []}
{"id": "v-g06", "query": "무첨가 천연 재료라고 상품 설명에 넣어도 될까요?", "food_type": "general", "usage": "page", "category": "variant", "expected_verdict": "unsure", "gold_basis": [], "gold_recog_no": []}
{"id": "v-g07", "query": "실제로 국내산 쌀만 쓰는데 메뉴판에 국내산 쌀 100%라고 적어도 되죠?", "food_type": "general", "usage": "menu", "category": "variant", "expected_verdict": "low", "gold_basis": [], "gold_recog_no": []}
{"id": "v-g08", "query": "버섯 반찬이 암을 막아준다고 블로그에 써도 돼요?", "food_type": "general", "usage": "sns", "category": "variant", "expected_verdict": "high", "gold_basis": [], "gold_recog_no": []}
{"id": "v-h01", "query": "홍삼 제품에 혈당 조절에 도움 줄 수 있다고 적는 건 괜찮나요?", "food_type": "health", "usage": "page", "category": "variant", "expected_verdict": "low", "gold_basis": [], "gold_recog_no": ["2024-20"]}
{"id": "v-h02", "query": "홍삼 건기식 홍보에 당뇨 치료된다고 써도 될까요?", "food_type": "health", "usage": "sns", "category": "variant", "expected_verdict": "high", "gold_basis": [], "gold_recog_no": ["2024-20"]}
{"id": "v-h03", "query": "CLA 제품 설명에 과체중 성인 체지방 감소에 도움 줄 수 있다고 넣어도 되나요?", "food_type": "health", "usage": "page", "category": "variant", "expected_verdict": "low", "gold_basis": [], "gold_recog_no": ["2006-21", "2006-22", "2005-16"]}
{"id": "v-h04", "query": "CLA 먹으면 한 달 10kg 빠진다고 인스타에 써도 돼요?", "food_type": "health", "usage": "sns", "category": "variant", "expected_verdict": "high", "gold_basis": [], "gold_recog_no": ["2006-21", "2006-22", "2005-16"]}
{"id": "v-h05", "query": "고혈압 치료 효과가 있다고 상품 페이지에 적어도 되나요?", "food_type": "health", "usage": "page", "category": "variant", "expected_verdict": "high", "gold_basis": [], "gold_recog_no": []}
{"id": "o01", "query": "식품 표시사항에 꼭 넣어야 하는 항목이 뭔가요?", "food_type": "general", "usage": "page", "category": "out_of_scope", "expected_verdict": "out_of_scope", "gold_basis": [], "gold_recog_no": []}
{"id": "o02", "query": "건강기능식품 표시사항에 들어가야 하는 내용은?", "food_type": "health", "usage": "page", "category": "out_of_scope", "expected_verdict": "out_of_scope", "gold_basis": [], "gold_recog_no": []}
{"id": "o03", "query": "식품 제조업 영업신고는 어떻게 하나요?", "food_type": "general", "usage": null, "category": "out_of_scope", "expected_verdict": "out_of_scope", "gold_basis": [], "gold_recog_no": []}
{"id": "o04", "query": "주방 위생 점검 기준이 궁금해요.", "food_type": "general", "usage": null, "category": "out_of_scope", "expected_verdict": "out_of_scope", "gold_basis": [], "gold_recog_no": []}
{"id": "o05", "query": "반찬가게 부가세 신고는 어떻게 하나요?", "food_type": "general", "usage": null, "category": "out_of_scope", "expected_verdict": "out_of_scope", "gold_basis": [], "gold_recog_no": []}
{"id": "o06", "query": "화장품 광고에 “주름 개선”이라고 써도 되나요?", "food_type": "health", "usage": "sns", "category": "out_of_scope", "expected_verdict": "out_of_scope", "gold_basis": [], "gold_recog_no": []}
{"id": "o07", "query": "광고 문구 때문에 걸리면 영업정지 몇 개월 받나요?", "food_type": "general", "usage": null, "category": "out_of_scope", "expected_verdict": "out_of_scope", "gold_basis": [], "gold_recog_no": []}
{"id": "n01", "query": "인스타 광고에 협찬 표시는 어떻게 해야 하나요?", "food_type": "general", "usage": "sns", "category": "no_basis", "expected_verdict": "out_of_scope", "gold_basis": [], "gold_recog_no": []}
{"id": "n02", "query": "상세페이지에 다른 회사 제품 사진을 써도 저작권 문제 없나요?", "food_type": "general", "usage": "page", "category": "no_basis", "expected_verdict": "out_of_scope", "gold_basis": [], "gold_recog_no": []}
{"id": "n03", "query": "배달앱 리뷰 이벤트로 별점 5점을 요구해도 되나요?", "food_type": "general", "usage": "sns", "category": "no_basis", "expected_verdict": "out_of_scope", "gold_basis": [], "gold_recog_no": []}
{"id": "n04", "query": "상세페이지 글씨체는 어떤 걸 써야 하나요?", "food_type": "general", "usage": "page", "category": "no_basis", "expected_verdict": "out_of_scope", "gold_basis": [], "gold_recog_no": []}
{"id": "n05", "query": "건강기능식품 쇼핑몰 할인 쿠폰 금액에 제한이 있나요?", "food_type": "health", "usage": "page", "category": "no_basis", "expected_verdict": "out_of_scope", "gold_basis": [], "gold_recog_no": []}
```

Run: `python -X utf8 -c "import json; rows=[json.loads(l) for l in open('eval/questions.jsonl',encoding='utf-8')]; from collections import Counter; print(len(rows), Counter(r['category'] for r in rows))"`
Expected: `38 Counter({'in_scope': 13, 'variant': 13, 'out_of_scope': 7, 'no_basis': 5})`

- [ ] **Step 6: `eval_retrieval.py` 작성**

`eval/eval_retrieval.py`:
```python
# -*- coding: utf-8 -*-
"""
eval_retrieval.py
범위 안 문구(in_scope, variant)로 BM25만 / kNN만 / 하이브리드 검색의 hit@5 를 비교한다.
gold_basis 가 빈 문구는 '정답 미정'으로 세고 비율 계산에서 뺀다.
결과: eval/report_retrieval.md

사용법:
  python eval/eval_retrieval.py
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "rag"))
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "common"))
from food_common import getOsClient, loadConfig
from metrics import hitAtK
from search_hybrid import MODES, embedQuery, ensurePipeline, searchLaw

TOP_K = 5


def loadQuestions():
    with open(HERE / "questions.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    cfg      = loadConfig()
    osClient = getOsClient(cfg)
    ensurePipeline(osClient)

    targets = [q for q in loadQuestions() if q["category"] in ("in_scope", "variant")]
    graded  = [q for q in targets if q["gold_basis"]]
    counts  = {mode: 0 for mode in MODES}
    rows    = []
    for q in graded:
        vec  = embedQuery(cfg, q["query"])
        mark = {}
        for mode in MODES:
            hits = searchLaw(osClient, cfg, q["query"], q["food_type"], topK=TOP_K, mode=mode, queryVector=vec)
            mark[mode] = hitAtK(hits, q["gold_basis"])
            counts[mode] += 1 if mark[mode] else 0
        rows.append((q["id"], mark))
        print(q["id"], {m: "O" if v else "X" for m, v in mark.items()})

    lines = [f"# 검색 방식별 근거 검색 적중률 (hit@{TOP_K})", "",
             f"실행: {datetime.now():%Y-%m-%d %H:%M} · 대상 {len(graded)}개 (정답 미정 {len(targets) - len(graded)}개 제외)", "",
             "| 방식 | 적중 | 비율 |", "|---|---|---|"]
    for mode in MODES:
        rate = counts[mode] / len(graded) * 100 if graded else 0
        lines.append(f"| {mode} | {counts[mode]}/{len(graded)} | {rate:.1f}% |")
    lines += ["", "| 문구 | " + " | ".join(MODES) + " |", "|---|" + "---|" * len(MODES)]
    for qid, mark in rows:
        lines.append(f"| {qid} | " + " | ".join("O" if mark[m] else "X" for m in MODES) + " |")
    (HERE / "report_retrieval.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n저장: {HERE / 'report_retrieval.md'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: `eval_answers.py` 작성**

`eval/eval_answers.py`:
```python
# -*- coding: utf-8 -*-
"""
eval_answers.py
실행 중인 서버의 /rag/query 를 문구 세트 전체로 호출해 답변 지표를 계산한다.
결과: eval/report_answers.md (지표 표 + 문구별 결과)

사용법 (rag_server.py 실행 중):
  python eval/eval_answers.py
  python eval/eval_answers.py --base-url http://localhost:5000
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from metrics import formatTable, scoreAnswer, summarize

ORDER = ["basis_shown", "refusal_ok", "citation_match", "no_decisive", "verdict_match", "material_match"]


def loadQuestions():
    with open(HERE / "questions.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    parser = argparse.ArgumentParser(description="답변 지표 평가")
    parser.add_argument("--base-url", default="http://localhost:5000")
    baseUrl = parser.parse_args().base_url

    rows, details = [], []
    for q in loadQuestions():
        start = time.time()
        body  = {"query": q["query"], "food_type": q["food_type"], "usage": q["usage"]}
        try:
            resp = requests.post(f"{baseUrl}/rag/query", json=body, timeout=300)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[{q['id']}] 호출 실패: {e}")
            details.append(f"| {q['id']} | {q['category']} | {q['expected_verdict']} | 호출 실패 | - | - |")
            continue
        score = scoreAnswer(q, data)
        rows.append(score)
        basis = ", ".join(b.get("article") or b.get("recog_no", "") for b in data["basis"])
        details.append(f"| {q['id']} | {q['category']} | {q['expected_verdict']} | {data['verdict']} | "
                       f"{basis or '-'} | {time.time() - start:.1f}s |")
        print(f"[{q['id']}] {data['verdict']:<12} 기대 {q['expected_verdict']:<12} {score}")

    lines = ["# 답변 평가", "", f"실행: {datetime.now():%Y-%m-%d %H:%M} · 서버 {baseUrl}", "",
             formatTable(summarize(rows), ORDER), "",
             "| 문구 | 구분 | 기대 판단 | 실제 판단 | 근거 | 시간 |", "|---|---|---|---|---|---|", *details]
    (HERE / "report_answers.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n저장: {HERE / 'report_answers.md'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 8: 전체 테스트**

Run: `python -m pytest -v`
Expected: 전부 통과, 실패 0.

- [ ] **Step 9: Commit**

```bash
git add eval tests/test_metrics.py
git commit -m "평가 지표, 문구 세트 38개, 검색·답변 평가 스크립트 추가"
```

---

### Task 14: 전체 연결 확인과 첫 평가

**Files:**
- Modify: `eval/questions.jsonl`(`gold_basis` 채우기), 결과 `eval/report_retrieval.md`, `eval/report_answers.md`

**Interfaces:**
- Consumes: Task 1~13 전부, 실행 중인 OpenSearch·Ollama·Redis

- [ ] **Step 1: 데이터 갱신 한 번에 실행**

Run: `python scripts/run_monthly.py`
Expected: 네 단계 모두 끝나고 `[완료] 월 1회 갱신 끝`. 이미 적재된 상태면 `indexed: 0`, 임베딩 `0건`.

- [ ] **Step 2: 서버 실행과 상태 확인**

Run (별도 터미널): `python scripts/rag/rag_server.py`
Run: `curl -s http://localhost:5000/rag/status`
Expected: `food-law-articles`, `food-materials` 모두 `docs`와 `embedded`가 같고 0보다 크다(`food-materials`는 731).

- [ ] **Step 3: 화면에서 시연 예시 확인**

브라우저에서 `http://localhost:5000`:
1. `일반식품` → “우리 카페 홍삼차, 혈당 관리에 최고!” 입력 → `위반 소지 큼`, 근거에 법령명·조문(또는 별표)이 보이고 하단에 수집 기준일과 고정 문구.
2. `건강기능식품`으로 바꿔 같은 문구 → 근거에 `제2024-20호 · 홍삼 · 인정 문구: 혈당 조절에 도움을 줄 수 있음`이 보이는지 확인(안 보이면 `python scripts/rag/search_hybrid.py "홍삼 혈당 관리" --food-type health --materials`로 검색 결과부터 본다).
3. 범위 밖 칩 → `범위 밖`, 근거 없음, 안내 2줄.
4. OpenSearch를 잠시 끄고 문구 입력 → “답변을 받지 못했어요 … 점검 중 오류가 발생했습니다 …” 말풍선, 입력창 다시 열림. 다시 켠다.

- [ ] **Step 4: 정답 근거 채우기 (A 담당)**

`eval/questions.jsonl`의 `in_scope`·`variant` 26개에 `gold_basis`를 채운다. 각 문구로
`python scripts/rag/search_hybrid.py "<문구>" --food-type <general|health> --topk 10`
을 돌려 후보를 보고, 실제 근거가 되는 조문을 `"<법령명> 제n조"` 또는 `"<법령명> 별표 n"` 형식으로 적는다(법령명은 `law_map.py`의 `name`과 글자까지 같게). 변형 문구는 원래 문구와 같은 값을 쓴다.

Run: `python -X utf8 -c "import json; rows=[json.loads(l) for l in open('eval/questions.jsonl',encoding='utf-8')]; print(sum(1 for r in rows if r['category'] in ('in_scope','variant') and not r['gold_basis']))"`
Expected: `0`

- [ ] **Step 5: 평가 실행**

Run: `python eval/eval_retrieval.py`
Expected: `eval/report_retrieval.md`에 bm25/knn/hybrid 세 줄 표. 
Run (서버 실행 중): `python eval/eval_answers.py`
Expected: `eval/report_answers.md`에 지표 6개 표와 문구 38개 결과. 근거 표기율이 100%가 아니면 해당 문구의 응답을 보고 Task 7 프롬프트를 조정한다(4일차 작업).

- [ ] **Step 6: Commit**

```bash
git add eval/questions.jsonl eval/report_retrieval.md eval/report_answers.md
git commit -m "정답 근거 채우기와 첫 평가 결과"
git push
```
