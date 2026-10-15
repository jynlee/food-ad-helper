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
