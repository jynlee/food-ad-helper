# -*- coding: utf-8 -*-
"""
suggest.py
추천 문구: 위반 소지가 있는 광고 문구를 '위반 소지 낮음'이 나오도록 고쳐 쓴다.

흐름: (건강기능식품이면 인정 기능성 검색) → Gemma로 고친 문구 1개 → 금지 표현이 남았으면 바로 다시 쓰기
     → 점검과 같은 프롬프트로 판단만 받기(quickCheck) → '낮음'이면 반환, 아니면 걸린 이유를 알려 주고 한 번 더.
법령 전문은 넣지 않고 원래 문구의 점검 결과(판단 이유·문제 표현)만 줘서 빠르게 만든다 (목표: 5초 이내).

사용법 (CLI 테스트):
  python scripts/rag/suggest.py "우리 카페 홍삼차, 피로 회복에 최고!" --food-type general --usage sns
"""

# ============================================================
# 라이브러리 임포트
# ============================================================

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from answer_format import USAGE_HINT
from food_common import FOOD_TYPE_MAP, getOsClient, loadConfig
from rag_pipeline import MATERIAL_TOP_K, generateAnswer, quickCheck, runFoodRag
from search_hybrid import embedQuery, ensurePipeline, searchMaterials


# ============================================================
# 상수 정의
# ============================================================

MAX_TRIES = 2      # 다시 점검은 최대 2번

# 점검에서 '큼'이나 '어려움'이 나오는 대표 표현. 남아 있으면 8초짜리 다시 점검 전에 바로 다시 쓰게 한다.
BANNED_WORDS = ("회복", "면역", "예방", "치료", "완치", "특효", "개선", "해독", "디톡스", "다이어트", "살 빠",
                "혈당", "혈압", "콜레스테롤", "항암", "노화", "효능", "효과", "최고", "최상", "100%", "무첨가")

SUGGEST_PROMPT = """당신은 카페·음식점·반찬가게 사장님의 광고 문구를 식품 표시·광고 기준에 맞게 고쳐 쓰는 도우미입니다.
아래 [원래 문구]를 고쳐서, 다시 점검했을 때 '위반 소지 낮음'이 나오는 광고 문구 1개를 만듭니다.

점검 기준 (고친 문구도 이 기준으로 다시 점검합니다):
- 질병 예방·치료, 몸의 기능이 좋아진다는 효능·효과 표현은 '큼'입니다. (예: 피로 회복, 면역력, 혈당, 다이어트, 해독)
- 일반식품이 건강기능식품처럼 보이는 표현은 '큼'입니다.
- "최고", "100%", "무첨가"처럼 근거 자료가 필요한 단정·과장 표현은 '어려움'입니다.
- 건강기능식품은 [인정 기능성 문구]를 글자 그대로 옮긴 표현만 기능성으로 쓸 수 있습니다. 그 밖의 효능 표현은 '큼'입니다.
- 맛·향·식감·만드는 방법·먹는 상황·가게 분위기를 그리는 평범한 말은 '낮음'입니다.

고쳐 쓰는 규칙:
1. 효능·효과 대신 원래 문구에 있는 원료, 맛·향, 만드는 방법, 먹는 상황, 가게 분위기를 말합니다.
2. 원래 문구에 없는 사실(원산지, 연수, 함량, 수상 경력, 재료, 곁들임 음식 등)은 지어내지 않습니다.
   재료 이름은 원래 문구에 있는 것만 씁니다. (예: "들기름"에 "참깨와 들깨로 만든"을 붙이지 않음)
   언제·얼마나 자주·누가 만드는지도 원래 문구에 없으면 쓰지 않습니다. (예: "매일 아침", "새벽마다", "직접", "주문 즉시")
3. 제품 종류는 바꾸지 않습니다. 원래 문구의 가게 이름·제품 이름을 그대로 쓰고, '이 제품'이면 '이 제품'으로 둡니다.
   (예: 건강기능식품을 '반찬'으로, 들기름을 '참기름'으로 바꾸지 않음) 사용처에 맞는 길이로 씁니다.
4. 아래 [점검 결과]에서 문제가 된 표현은 비슷한 말로 바꾸지 말고 아예 뺍니다. (예: '피로 회복' → '활력 충전'도 안 됨)

좋은 예: "우리 카페 홍삼차, 피로 회복에 최고!" → "진하게 우려낸 우리 카페 홍삼차, 따뜻하게 한 잔 하고 가세요"
나쁜 예: "우리 카페 홍삼차, 지친 몸에 활력을!" (효능 표현이 남음)
좋은 예: "우리 반찬 먹으면 면역력 쑥쑥" → "밥 한 공기 뚝딱 비우게 되는 우리 가게 반찬"
나쁜 예: "국내산 재료로 만든 건강 반찬" (원래 문구에 없는 '국내산'을 지어냄)

반드시 아래 형식 그대로 답합니다. 형식 밖의 말은 쓰지 않습니다.
[추천문구] 고친 광고 문구 한 줄
[바꾼점] 원래 문구에서 무엇을 왜 바꿨는지 쉬운 말 한 문장"""

_PHRASE_RE = re.compile(r'\[추천문구\]\s*(.+)')
_CHANGE_RE = re.compile(r'\[바꾼점\]\s*(.+)')
_QUOTES    = "\"'“”‘’「」"


# ============================================================
# 프롬프트 / 파싱
# ============================================================

def buildSuggestPrompt(foodType, usage, query, original, failed=None, claims=None):
    """
    original: 원래 문구의 점검 결과 (verdict_reason, basis[].summary 사용)
    failed  : (앞서 만든 문구, 걸린 이유) — 두 번째 시도에만
    claims  : 건강기능식품의 인정 기능성 문구 목록
    """
    notes = [b.get("summary", "") for b in original.get("basis") or [] if b.get("summary")]
    lines = [SUGGEST_PROMPT, "",
             "[점검 조건]",
             f"식품 종류: {FOOD_TYPE_MAP[foodType]}",
             f"사용처: {USAGE_HINT.get(usage, '지정 안 함')}", ""]
    if claims:
        lines += ["[인정 기능성 문구]"] + [f"- {c}" for c in claims] + [""]
    lines += ["[점검 결과]",
             f"판단 이유: {original.get('verdict_reason', '')}"]
    lines += [f"- {n}" for n in notes]
    if failed:
        lines += ["", "[앞서 만든 문구 — 이것도 걸렸으니 같은 표현을 쓰지 마세요]",
                  f"문구: {failed[0]}", f"걸린 이유: {failed[1]}"]
    lines += ["", "[원래 문구]", query, "", "[답변]"]
    return "\n".join(lines)


def parseSuggestion(raw):
    """Gemma 답에서 추천 문구와 바꾼 점을 꺼낸다. 추천 문구가 없으면 None."""
    m = _PHRASE_RE.search(raw or "")
    if not m:
        return None
    phrase = m.group(1).strip().strip(_QUOTES).strip()
    if not phrase:
        return None
    c = _CHANGE_RE.search(raw)
    return {"phrase": phrase, "change": c.group(1).strip() if c else ""}


def findBannedWords(phrase, allowedText=""):
    """문구에 남은 금지 표현. 인정 기능성 문구(allowedText)에 있는 말은 건강기능식품이 써도 되므로 뺀다."""
    return [w for w in BANNED_WORDS if w in phrase and w not in allowedText]


# ============================================================
# 추천 실행
# ============================================================

def _candidate(cfg, foodType, usage, query, original, failed, claims):
    """문구 1개 만들기. 금지 표현이 남으면 다시 점검하기 전에 한 번 바로 다시 쓴다. 실패하면 (None, 이유)."""
    allowedText = " ".join(claims)
    cand = parseSuggestion(generateAnswer(cfg, buildSuggestPrompt(foodType, usage, query, original, failed, claims)))
    if cand is None:
        return None, None
    banned = findBannedWords(cand["phrase"], allowedText)
    if not banned:
        return cand, None
    reason = f"'{', '.join(banned)}' 같은 효능·과장 표현이 남아 있어요."
    cand = parseSuggestion(generateAnswer(cfg, buildSuggestPrompt(foodType, usage, query, original,
                                                                  (cand["phrase"], reason), claims)))
    if cand is None or findBannedWords(cand["phrase"], allowedText):
        return None, (cand["phrase"] if cand else "", reason)
    return cand, None


def runSuggest(osClient, cfg, query, foodType, usage, original, checkFn):
    """
    추천 문구 1개. checkFn(문구) → {"verdict", "verdict_reason"} (서버에서는 quickCheck).
    반환: {"success", "phrase", "change", "tries"} — tries는 다시 점검한 횟수
    """
    claims = []
    if foodType == "health":
        hits   = searchMaterials(osClient, cfg, query, topK=MATERIAL_TOP_K, queryVector=embedQuery(cfg, query))
        claims = [c for h in hits for c in h.get("claims") or []]

    failed, tries = None, 0
    for _ in range(MAX_TRIES):
        cand, bannedFail = _candidate(cfg, foodType, usage, query, original, failed, claims)
        if cand is None:
            failed = bannedFail or failed
            continue
        tries += 1
        result = checkFn(cand["phrase"])
        if result.get("verdict") == "low":
            return {"success": True, "phrase": cand["phrase"], "change": cand["change"], "tries": tries}
        failed = (cand["phrase"], result.get("verdict_reason", ""))
    return {"success": False, "phrase": "", "change": "", "tries": tries}


# ============================================================
# 메인 (CLI 테스트)
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="추천 문구 테스트")
    parser.add_argument("query")
    parser.add_argument("--food-type", default="general", choices=list(FOOD_TYPE_MAP))
    parser.add_argument("--usage",     default=None,      choices=["menu", "page", "sns"])
    args = parser.parse_args()

    cfg      = loadConfig()
    osClient = getOsClient(cfg)
    ensurePipeline(osClient)
    original = runFoodRag(osClient, cfg, args.query, args.food_type, usage=args.usage)
    print(f"[원래 문구] {original['verdict']} — {original.get('verdict_reason', '')}")
    check  = lambda p: quickCheck(osClient, cfg, p, args.food_type, usage=args.usage)
    result = runSuggest(osClient, cfg, args.query, args.food_type, args.usage, original, check)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
