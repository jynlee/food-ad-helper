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
