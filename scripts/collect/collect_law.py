# -*- coding: utf-8 -*-
"""
collect_law.py
법제처 API에서 법률·시행령·시행규칙 8개를 받아 food-law-articles 인덱스에 적재.
원본 JSON은 data/law/law_<법령ID>.json 에 저장하고, --offline 이면 API 대신 저장본을 읽는다.

사용법:
  python scripts/collect/collect_law.py                 # 8개 전체
  python scripts/collect/collect_law.py --only 식품위생법
  python scripts/collect/collect_law.py --offline       # 저장된 원본으로 다시 적재
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
from food_common import ROOT, appendLog, getOsClient, loadConfig, retryGet
from law_map import LAW_TARGETS
from law_parse import parseAnnexes, parseClauses, parseDate, pickTarget
from law_store import ensureLawIndex, storeDocs


# ============================================================
# 상수 정의
# ============================================================

LAW_SEARCH_URL  = "https://www.law.go.kr/DRF/lawSearch.do"
LAW_SERVICE_URL = "https://www.law.go.kr/DRF/lawService.do"
RAW_DIR         = ROOT / "data" / "law"
ID_CACHE        = RAW_DIR / "resolved_ids.json"


# ============================================================
# 법령 ID 확인 (이름 → 법령ID)
# ============================================================

def loadIdCache():
    if ID_CACHE.exists():
        return json.loads(ID_CACHE.read_text(encoding="utf-8"))
    return {}


def saveIdCache(cache):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ID_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def resolveLawId(cfg, name, cache, offline):
    """법령명으로 목록 조회해 법령ID를 찾는다. 찾은 값은 cache에 저장."""
    key = f"law:{name}"
    if key in cache:
        return cache[key]
    if offline:
        raise LookupError(f"{name}: resolved_ids.json 에 ID가 없어 --offline 으로 진행할 수 없습니다.")
    params = {"OC": cfg['lawApiKey'], "target": "law", "type": "JSON", "query": name, "display": 100}
    found  = pickTarget(retryGet(LAW_SEARCH_URL, params).json().get("LawSearch", {}).get("law"),
                        name, "법령명한글")
    cache[key] = str(found["법령ID"])
    return cache[key]


# ============================================================
# 수집 / 문서화
# ============================================================

def fetchLaw(cfg, lawId, offline):
    """법령 본문 JSON. 온라인이면 받아서 저장, 오프라인이면 저장본을 읽는다."""
    path = RAW_DIR / f"law_{lawId}.json"
    if offline:
        return json.loads(path.read_text(encoding="utf-8"))
    params = {"OC": cfg['lawApiKey'], "target": "law", "ID": lawId, "type": "JSON"}
    data   = retryGet(LAW_SERVICE_URL, params).json()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def buildLawDocs(lawData, lawId, info, collectedAt):
    """법령 JSON → 조문(항 단위) 문서 + 별표 문서."""
    lawBlock = lawData.get("법령", {})
    meta = {
        "info":          info,
        "lawId":         lawId,
        "sourceKey":     f"law_{lawId}",
        "effectiveDate": parseDate(lawBlock.get("기본정보", {}).get("시행일자")),
        "collectedAt":   collectedAt,
    }
    annexBlock = lawBlock.get("별표")
    annexUnits = annexBlock.get("별표단위") if isinstance(annexBlock, dict) else annexBlock
    return parseClauses(lawData, meta) + parseAnnexes(annexUnits, meta)


def collectOne(cfg, osClient, info, cache, offline, collectedAt):
    """법령 하나 수집 → 문서화 → 저장 → collect 로그."""
    name = info["name"]
    print(f"\n[{name}] 수집 시작")
    try:
        lawId   = resolveLawId(cfg, name, cache, offline)
        docs    = buildLawDocs(fetchLaw(cfg, lawId, offline), lawId, info, collectedAt)
        if not docs:
            raise ValueError("파싱된 조문 없음 - data/law 원본의 응답 구조 확인 필요")
        summary = storeDocs(osClient, f"law_{lawId}", docs, collectedAt)
        appendLog("collect", {"source": f"law_{lawId}", "name": name, "status": "success", **summary})
        print(f"  {summary}")
    except Exception as e:
        appendLog("collect", {"source": name, "name": name, "status": "failed", "error": str(e)})
        print({"success": False, "message": f"{name} 수집 실패: {e}"})


# ============================================================
# 메인
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="법제처 법령 수집 → food-law-articles")
    parser.add_argument("--offline", action="store_true", help="API 대신 data/law 저장본 사용")
    parser.add_argument("--only",    default=None,        help="이 이름의 법령만 수집")
    args = parser.parse_args()

    cfg = loadConfig()
    if not args.offline and not cfg['lawApiKey']:
        print({"success": False, "message": ".env에 LAW_OC 가 없습니다."})
        sys.exit(1)

    osClient = getOsClient(cfg)
    ensureLawIndex(osClient)
    cache       = loadIdCache()
    collectedAt = date.today().isoformat()
    targets     = [t for t in LAW_TARGETS if args.only in (None, t["name"])]
    for info in targets:
        collectOne(cfg, osClient, info, cache, args.offline, collectedAt)
    saveIdCache(cache)
    print("\n[완료] 결과는 logs/collect.jsonl 참고")


if __name__ == "__main__":
    main()
