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
    """materials.jsonl 행 → bulk 액션. _id 는 인정번호 (원본에 인정번호가 없는 행은 뺀다)."""
    actions = []
    for m in materials:
        if not m.get("_id"):
            continue
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
    materials = loadMaterials(MATERIALS_PATH)
    actions   = buildActions(materials, collectedAt)
    if len(actions) < len(materials):
        print(f"[INFO] 인정번호 없음 {len(materials) - len(actions)}건 제외")
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
