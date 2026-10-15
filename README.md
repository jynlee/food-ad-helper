# 식품 표시·광고 도우미 챗봇

소상공인(카페·음식점·반찬가게, 온라인 식품 판매자)을 위한 RAG 기반 식품 표시·광고 도우미 챗봇.
메뉴판·상세페이지·SNS 문구가 법에 걸릴 수 있는지 근거 조문과 함께 안내합니다.

## 폴더
- `data/law/` 법제처 법령·고시 (수집 예정)
- `data/foodsafety/` 식품안전나라 원본(I-0040, I-0050)과 정제본 `materials.jsonl`
- `src/` 수집·정제·검색·API 코드
- `eval/` 평가 문구 세트
- `docs/` 개요서 등 문서

## 식품안전나라 데이터 만들기
API는 다시 부르지 않고 저장된 원본으로 정제합니다.

    python src/build_materials.py

(원본 수집이 필요하면 `FOODSAFETY_KEY` 환경변수를 넣고 `python src/fetch_foodsafety.py`)
