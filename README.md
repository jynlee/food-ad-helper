# 식품 표시·광고 도우미

소상공인(카페·음식점·반찬가게, 온라인 식품 판매자)을 위한 RAG 기반 식품 표시·광고 도우미.
메뉴판·상세페이지·SNS 문구가 법에 걸릴 수 있는지 근거 조문과 함께 안내합니다.

- 개요: `식품 표시·광고 점검 도우미 개요서.md`
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
