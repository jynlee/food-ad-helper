# -*- coding: utf-8 -*-
"""
rag_server.py
FastAPI 서버 — 식품 표시·광고 점검 API와 웹 화면(web/index.html)을 함께 제공.
포트 5000. Swagger UI: http://localhost:5000/docs

엔드포인트:
  POST /rag/query  : 광고 문구 점검 (캐시 → 검색 → LLM 1회)
  POST /rag/suggest: 추천 문구 (고쳐 쓰기 → 다시 점검해서 '낮음'인 문구 1개)
  GET  /rag/health : 서버 상태
  GET  /rag/status : 인덱스 문서 수·임베딩 수
  GET  /           : 웹 화면

사용법:
  python scripts/rag/rag_server.py
"""

# ============================================================
# 라이브러리 임포트
# ============================================================

import hashlib
import json
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
from rag_pipeline import quickCheck, runFoodRag
from suggest import runSuggest
from search_hybrid import LAW_INDEX, MATERIAL_INDEX, ensurePipeline


# ============================================================
# 상수 / 공유 클라이언트
# ============================================================

MAX_QUERY_LEN  = 2000
SUGGEST_PREFIX = "foodsug:"     # Redis: 추천 문구 (같은 문구·식품 종류·사용처면 7일 동안 재사용)
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
    title:          Optional[str] = None
    content:        Optional[str] = None
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


class SuggestResponse(BaseModel):
    success: bool
    phrase:  str = ""
    change:  str = ""
    tries:   int = 0


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


def checkPhrase(query, foodType, usage):
    """점검 한 번 (캐시 → RAG → 캐시 저장). /rag/query 와 추천 문구(원래 문구의 점검 결과)가 같이 쓴다."""
    scope = f"{foodType}:{usage or '_'}"
    cached, queryVector = lookupCache(state["osClient"], state["redisClient"], state["cfg"],
                                      "food", query, scope=scope)
    if cached:
        return cached
    result = runFoodRag(state["osClient"], state["cfg"], query, foodType, usage=usage, queryVector=queryVector)
    if not result.get("raw_fallback"):    # 형식이 깨진 답변은 7일 동안 재사용되지 않게 저장하지 않음
        storeCache(state["osClient"], state["redisClient"], state["cfg"], "food", query, result,
                   scope=scope, queryVector=queryVector)
    return result


def checkQueryText(query):
    query = query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="문구를 입력해 주세요.")
    if len(query) > MAX_QUERY_LEN:
        raise HTTPException(status_code=400, detail=f"문구는 {MAX_QUERY_LEN}자 이내로 입력해 주세요.")
    return query


@app.post("/rag/query", response_model=QueryResponse, tags=["점검"])
def ragQuery(req: QueryRequest):
    """광고 문구를 받아 위반 소지·해야 할 일·근거를 반환."""
    query = checkQueryText(req.query)
    try:
        return QueryResponse(**checkPhrase(query, req.food_type, req.usage))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"점검 중 오류가 발생했습니다: {e}")


@app.post("/rag/suggest", response_model=SuggestResponse, tags=["점검"])
def ragSuggest(req: QueryRequest):
    """위반 소지가 큼·어려움인 문구를 고쳐 쓰고, 다시 점검해서 '낮음'이 나온 문구 1개를 반환."""
    query = checkQueryText(req.query)
    key   = SUGGEST_PREFIX + hashlib.sha1(f"{req.food_type}:{req.usage or '_'}|{query}".encode("utf-8")).hexdigest()
    try:
        cached = state["redisClient"].get(key)
        if cached:
            return SuggestResponse(**json.loads(cached))
    except Exception as e:
        print(f"[WARN] 추천 문구 캐시 조회 실패, 새로 만듭니다: {e}")

    try:
        original = checkPhrase(query, req.food_type, req.usage)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"점검 중 오류가 발생했습니다: {e}")
    if original.get("verdict") not in ("high", "unsure") or original.get("raw_fallback"):
        raise HTTPException(status_code=400, detail="추천 문구는 위반 소지가 크거나 판단이 어려운 문구에만 만들어요.")

    try:
        # 고친 문구는 캐시에서 비슷한 옛 답을 찾지 않고, 같은 프롬프트로 판단만 새로 받는다 (seed 고정 → 전체 점검과 같은 판단)
        check  = lambda phrase: quickCheck(state["osClient"], state["cfg"], phrase, req.food_type, req.usage)
        result = runSuggest(state["osClient"], state["cfg"], query, req.food_type, req.usage, original, check)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"추천 문구를 만드는 중 오류가 발생했습니다: {e}")
    if result["success"]:
        try:
            state["redisClient"].setex(key, state["cfg"]['qaCacheTtlSec'], json.dumps(result, ensure_ascii=False))
        except Exception as e:
            print(f"[WARN] 추천 문구 캐시 저장 실패 (응답에는 영향 없음): {e}")
    return SuggestResponse(**result)


# 정적 화면은 API 라우트 다음에 마운트해야 /rag/* 를 가리지 않는다
app.mount("/", StaticFiles(directory=str(ROOT / "web"), html=True), name="web")


# ============================================================
# 메인
# ============================================================

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
