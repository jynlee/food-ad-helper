# -*- coding: utf-8 -*-
"""
rag_pipeline.py
광고 문구 점검 RAG: 법령 검색(+건강기능식품이면 인정 기능성 검색) → Context → Gemma 1회 → 파싱.
quickCheck: 같은 프롬프트로 [판단] 줄까지만 받는 빠른 점검 (추천 문구의 다시 점검용).

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
                           parseAnswer, parseVerdict, splitSections)
from food_common import FOOD_TYPE_MAP, getOsClient, loadConfig
from search_hybrid import LAW_INDEX, embedQuery, ensurePipeline, searchLaw, searchMaterials


# ============================================================
# 상수 정의
# ============================================================

GENERATE_API_PATH = "/api/generate"
LAW_TOP_K         = 5
MATERIAL_TOP_K    = 3
LLM_SEED          = 42      # 숫자 자체는 의미 없음. 고정해 두면 같은 문구에 언제나 같은 판단이 나온다
STOP_AFTER_VERDICT = ["[판단이유]"]
STOP_AFTER_REASON  = ["[해야할일]"]


# ============================================================
# LLM / 인덱스 보조
# ============================================================

def generateAnswer(cfg, prompt, stop=None):
    """Ollama Gemma로 답변 생성 (스트리밍 없음). stop을 주면 그 글자가 나오기 직전에 멈춘다."""
    url     = cfg['ollamaHost'].rstrip("/") + GENERATE_API_PATH
    options = {"temperature": 0.1, "num_ctx": 8192, "seed": LLM_SEED}
    if stop:
        options["stop"] = stop
    payload = {
        "model":   cfg['llmModel'],
        "prompt":  prompt,
        "stream":  False,
        "think":   False,     # gemma4의 숨은 생각 끄기: 45초 → 8~14초 (답변 형식·판단은 그대로)
        "keep_alive": "30m",  # 5분 쉬면 모델을 내리므로, 시연 중 첫 질문도 빠르게 30분 유지
        "options": options,
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

def searchAndPrompt(osClient, cfg, query, foodType, usage=None, queryVector=None):
    """검색 → (프롬프트, 근거 번호표). 검색 결과가 하나도 없으면 (None, {})."""
    lawHits      = searchLaw(osClient, cfg, query, foodType, topK=LAW_TOP_K)   # 법령은 광고 맥락을 붙여 따로 임베딩
    materialHits = []
    if foodType == "health":
        if queryVector is None:
            queryVector = embedQuery(cfg, query)
        materialHits = searchMaterials(osClient, cfg, query, topK=MATERIAL_TOP_K, queryVector=queryVector)
    if not lawHits and not materialHits:
        return None, {}
    context, refTable = buildContext(lawHits, materialHits)
    return buildPrompt(foodType, usage, context, query), refTable


def runFoodRag(osClient, cfg, query, foodType, usage=None, queryVector=None):
    """
    광고 문구 점검 전체 실행. 반환: API 응답 dict (spec 5.5).
    검색 결과가 하나도 없으면 LLM을 부르지 않고 '근거 조문을 찾지 못함'으로 답한다.
    """
    prompt, refTable = searchAndPrompt(osClient, cfg, query, foodType, usage, queryVector)
    if prompt is None:
        return buildResponse(NO_BASIS_PARSED, {}, "", latestIndexCollectedAt(osClient))
    raw = generateAnswer(cfg, prompt)
    return buildResponse(parseAnswer(raw), refTable, raw, query=query)


def quickCheck(osClient, cfg, query, foodType, usage=None):
    """
    runFoodRag와 같은 프롬프트로 [판단] 줄까지만 받는다 (약 4초 → 1~2초). seed가 고정이라 전체 점검과 같은 판단.
    '낮음'이 아니면 고쳐 쓸 때 알려 줄 판단 이유까지 한 번 더 받는다. 반환: {"verdict", "verdict_reason"}
    """
    prompt, _ = searchAndPrompt(osClient, cfg, query, foodType, usage)
    if prompt is None:
        return {"verdict": "out_of_scope", "verdict_reason": ""}
    verdict = parseVerdict(splitSections(generateAnswer(cfg, prompt, stop=STOP_AFTER_VERDICT)).get("판단", ""))
    if verdict == "low":
        return {"verdict": "low", "verdict_reason": ""}
    sections = splitSections(generateAnswer(cfg, prompt, stop=STOP_AFTER_REASON))
    return {"verdict": verdict or "unsure", "verdict_reason": sections.get("판단이유", "").strip()}


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
