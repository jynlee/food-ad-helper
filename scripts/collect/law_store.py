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
