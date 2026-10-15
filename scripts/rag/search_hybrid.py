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
# 광고 문구만으로 검색하면 의미 검색이 나트륨·영양성분 "표시사항" 조문으로 쏠린다.
# 법령 검색에만 이 맥락을 붙여 부당한 표시·광고 조문(법 제8조, 시행령 별표 1, 고시 제2조)이 먼저 나오게 한다.
LAW_QUERY_SUFFIX = " 라는 광고 문구가 부당한 표시 또는 광고에 해당하는지"


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

def lawSearchText(queryText):
    """법령 검색에 실제로 쓰는 문장: 사용자 문구 + 광고 점검 맥락."""
    return queryText.rstrip() + LAW_QUERY_SUFFIX


def searchLaw(osClient, cfg, queryText, foodType, topK=5, mode="hybrid", queryVector=None):
    """법령·고시 검색. bm25 모드는 임베딩을 만들지 않는다."""
    searchText = lawSearchText(queryText)          # queryVector를 넘길 때는 이 문장의 벡터여야 한다
    if mode != "bm25" and queryVector is None:
        queryVector = embedQuery(cfg, searchText)
    body   = buildLawQuery(searchText, queryVector, foodType, topK, mode)
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
