# -*- coding: utf-8 -*-
"""
collect_admrul.py
법제처 API에서 식약처 고시 2개(행정규칙)를 받아 food-law-articles 인덱스에 적재.
원본 JSON은 data/law/admrul_<행정규칙일련번호>.json 에 저장.

사용법:
  python scripts/collect/collect_admrul.py
  python scripts/collect/collect_admrul.py --only "건강기능식품의 기준 및 규격"
  python scripts/collect/collect_admrul.py --offline
"""

# ============================================================
# 라이브러리 임포트
# ============================================================

import argparse
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from collect_law import LAW_SEARCH_URL, LAW_SERVICE_URL, RAW_DIR, loadIdCache, saveIdCache
from food_common import appendLog, getOsClient, loadConfig, retryGet
from law_map import ADMRUL_TARGETS
from law_parse import flattenText, parseAdmrulArticles, parseAnnexes, parseDate, pickTarget
from law_store import ensureLawIndex, storeDocs


# ============================================================
# 행정규칙 ID 확인 / 수집
# ============================================================

def resolveAdmrulId(cfg, name, cache, offline):
    """행정규칙명으로 목록 조회해 행정규칙일련번호를 찾는다."""
    key = f"admrul:{name}"
    if key in cache:
        return cache[key]
    if offline:
        raise LookupError(f"{name}: resolved_ids.json 에 ID가 없어 --offline 으로 진행할 수 없습니다.")
    params = {"OC": cfg['lawApiKey'], "target": "admrul", "type": "JSON", "query": name, "display": 100}
    found  = pickTarget(retryGet(LAW_SEARCH_URL, params).json().get("AdmRulSearch", {}).get("admrul"),
                        name, "행정규칙명")
    cache[key] = str(found["행정규칙일련번호"])
    return cache[key]


def fetchAdmrul(cfg, admId, offline):
    path = RAW_DIR / f"admrul_{admId}.json"
    if offline:
        return json.loads(path.read_text(encoding="utf-8"))
    params = {"OC": cfg['lawApiKey'], "target": "admrul", "ID": admId, "type": "JSON"}
    data   = retryGet(LAW_SERVICE_URL, params).json()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def buildAdmrulDocs(admData, admId, info, collectedAt):
    """고시 JSON → 조 단위 문서 + 별표 문서."""
    body = admData.get("AdmRulService", admData)
    meta = {
        "info":          info,
        "lawId":         admId,
        "sourceKey":     f"admrul_{admId}",
        "effectiveDate": parseDate(body.get("행정규칙기본정보", {}).get("시행일자")),
        "collectedAt":   collectedAt,
    }
    annexBlock = body.get("별표")
    annexUnits = annexBlock.get("별표단위") if isinstance(annexBlock, dict) else annexBlock
    return parseAdmrulArticles(flattenText(body.get("조문내용")), meta) + parseAnnexes(annexUnits, meta)


def collectOne(cfg, osClient, info, cache, offline, collectedAt):
    name = info["name"]
    print(f"\n[{name}] 수집 시작")
    try:
        admId   = resolveAdmrulId(cfg, name, cache, offline)
        docs    = buildAdmrulDocs(fetchAdmrul(cfg, admId, offline), admId, info, collectedAt)
        if not docs:
            raise ValueError("파싱된 조문 없음 - data/law 원본의 응답 구조 확인 필요")
        summary = storeDocs(osClient, f"admrul_{admId}", docs, collectedAt)
        appendLog("collect", {"source": f"admrul_{admId}", "name": name, "status": "success", **summary})
        print(f"  {summary}")
    except Exception as e:
        appendLog("collect", {"source": name, "name": name, "status": "failed", "error": str(e)})
        print({"success": False, "message": f"{name} 수집 실패: {e}"})


# ============================================================
# 메인
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="법제처 행정규칙(고시) 수집 → food-law-articles")
    parser.add_argument("--offline", action="store_true", help="API 대신 data/law 저장본 사용")
    parser.add_argument("--only",    default=None,        help="이 이름의 고시만 수집")
    args = parser.parse_args()

    cfg = loadConfig()
    if not args.offline and not cfg['lawApiKey']:
        print({"success": False, "message": ".env에 LAW_OC 가 없습니다."})
        sys.exit(1)

    osClient = getOsClient(cfg)
    ensureLawIndex(osClient)
    cache       = loadIdCache()
    collectedAt = date.today().isoformat()
    for info in [t for t in ADMRUL_TARGETS if args.only in (None, t["name"])]:
        collectOne(cfg, osClient, info, cache, args.offline, collectedAt)
    saveIdCache(cache)
    print("\n[완료] 결과는 logs/collect.jsonl 참고")


if __name__ == "__main__":
    main()
