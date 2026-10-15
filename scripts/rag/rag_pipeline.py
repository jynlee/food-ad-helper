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

    lawHits      = searchLaw(osClient, cfg, query, foodType, topK=LAW_TOP_K)   # 법령은 광고 맥락을 붙여 따로 임베딩
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
