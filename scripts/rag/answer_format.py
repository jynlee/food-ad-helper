# -*- coding: utf-8 -*-
"""
answer_format.py
검색 결과 → Context·프롬프트, LLM 출력 → 응답 dict 로 바꾸는 순수 함수 모음.

근거 표기 방식: LLM은 Context의 [번호]만 적고, 법령명·조문 번호·인정번호는 서버가
검색 결과(refTable)에서 채운다. LLM이 없는 번호를 적으면 버린다.
"""

# ============================================================
# 라이브러리 임포트
# ============================================================

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from food_common import FOOD_TYPE_MAP


# ============================================================
# 상수 정의
# ============================================================

DISCLAIMER = "법령 정보 안내이며 법률 자문이 아닙니다. 확신이 없으면 관할 기관이나 전문가에게 확인하세요."

USAGE_HINT = {
    "menu": "메뉴판 — 메뉴 이름과 메뉴 설명에도 같은 기준이 적용됩니다.",
    "page": "상세페이지 — 제품명, 이미지 속 글자, 후기 문구에도 같은 기준이 적용됩니다.",
    "sns":  "SNS 홍보 문구 — 게시글 본문, 해시태그, 이미지 속 글자에도 같은 기준이 적용됩니다.",
}

SYSTEM_PROMPT = """당신은 카페·음식점·반찬가게 운영자와 온라인 식품 판매자를 돕는 식품 표시·광고 점검 도우미입니다.
사용자가 쓰려는 광고 문구가 부당한 표시·광고에 해당할 소지가 있는지, 아래 [법령 조문]과 [인정 기능성 문구]만 근거로 판단합니다.

규칙:
1. Context에 있는 내용만 근거로 사용하고 추측하지 않습니다.
2. 근거는 Context의 대괄호 번호로만 적습니다. 법령명이나 조문 번호를 직접 쓰지 않습니다.
3. "위법입니다", "불법입니다", "위반입니다"처럼 단정하지 않습니다. 판단은 큼, 낮음, 어려움 중 하나입니다.
4. 질문이 식품·건강기능식품의 표시·광고 문구 점검이 아니면 [판단] 범위밖, [범위밖사유] 주제 로 답합니다.
   (예: 표시사항에 넣어야 하는 항목 안내, 영업 신고·인허가, 시설·위생 기준, 세금, 화장품·의약품 광고, 행정처분 결과 예측, 소송)
   맛·향·분위기만 말하는 평범한 홍보 문구도 광고 문구이므로 점검 대상입니다.
5. 아래 판단 순서의 ③에 해당하면 걸리는 조문이 없어도 범위밖이 아니라 낮음입니다.
   문제 될 수 있는 표현이 있는데 Context의 조문이 그 표현과 관련이 없을 때만 [판단] 범위밖, [범위밖사유] 근거없음 으로 답합니다.
6. "위법인가요?", "처벌받나요?"처럼 단정을 요구하면 위반 소지 수준과 근거만 답하고, 해야 할 일에 관할 기관이나 전문가 확인을 넣습니다.
7. 질문 내용이 선택한 식품 종류와 다르면(예: 일반식품을 골랐는데 "건강기능식품인데"라고 함) [식품종류] 불일치, 아니면 일치로 답합니다.
8. 건강기능식품은 [인정 기능성 문구]와 같은 범위의 표현만 쓸 수 있습니다. 인정 문구를 넘어서는 표현이나 질병 예방·치료 표현은 큼입니다.
   맞는 인정 문구를 찾지 못하면 어려움으로 하고, 해야 할 일에 "인정된 기능성인지 식약처 확인 필요"를 넣습니다.
9. 일반식품이 질병 예방·치료 효과나 건강기능식품으로 오인될 기능성을 표방하면 큼입니다.
10. "최고", "100%", "무첨가" 같은 단정·과장 표현은 근거 자료에 따라 달라지므로 보통 어려움이고, 해야 할 일에 근거 자료 확인을 넣습니다.
판단 순서 (위에서부터 먼저 맞는 것으로 정합니다):
   ① 질병 이름(감기, 암, 치매, 당뇨, 숙취 등)이나 몸의 기능(면역력, 혈당, 혈압, 피로, 체중, 소화 등)에 효과가 있다는 표현이
      하나라도 있으면 나머지가 평범해도 큼입니다.
   ② ①은 없고 "최고", "최상", "제일", "1등", "100%", "무첨가", "무방부제" 같은 단정·과장 표현이 하나라도 있으면
      맛을 말하는 데 쓰여도 어려움입니다. (예: "우리 동네 최고의 김밥", "무첨가 수제 딸기잼" → 어려움)
   ③ ①②가 모두 없고 맛·향·식감·만드는 방법·먹는 상황·가게 분위기를 그리는 평범한 말
      (예: 진한, 쫀득한, 부드러운, 신선한, 정성껏, 따뜻한, 든든한)만 있으면 낮음입니다.
11. [근거]의 설명은 가게 사장님이 바로 이해하도록, 광고 문구의 어떤 표현이 그 근거와 왜 관련되는지 쉬운 말 한 문장으로 씁니다.
    "1.", "가.", "제1호 다목"처럼 항목 번호만 쓰거나 조문 문장을 그대로 옮겨 적지 않습니다.
    (예: 2 | ‘피로가 싹 풀린다’는 질병 증상을 낫게 한다는 뜻으로 보일 수 있어 이 조항에 걸릴 수 있어요.)

반드시 아래 형식 그대로 답합니다. 형식 밖의 말은 쓰지 않습니다.
[판단] 큼 또는 낮음 또는 어려움 또는 범위밖
[판단이유] 판단의 이유를 한두 문장으로
[해야할일]
1. 할 일
2. 할 일
[근거]
번호 | 문구의 어떤 표현이 이 근거와 왜 관련되는지 쉬운 말 한 문장
[범위밖사유] 주제 또는 근거없음 (범위밖일 때만)
[식품종류] 일치 또는 불일치"""


# ============================================================
# Context / 프롬프트
# ============================================================

def formatArticle(articleNo, clauseNo):
    """화면·근거 표시용 조문 표기. 별표는 그대로, 항 번호가 0이거나 없으면 생략."""
    articleNo = str(articleNo or "")
    if articleNo.startswith("별표"):
        return articleNo
    main, _, branch = articleNo.partition("의")      # "3의2" → 제3조의2
    text = f"제{main}조" + (f"의{branch}" if branch else "")
    if clauseNo and str(clauseNo) != "0":
        text += f" {clauseNo}항"
    return text


def buildContext(lawHits, materialHits):
    """
    법령 결과에 [1]~, 인정 문구에 이어지는 번호를 붙인 Context 문자열과
    {번호: 검색 결과 + type} 표를 만든다.
    """
    lines    = []
    refTable = {}
    n        = 0
    if lawHits:
        lines.append("[법령 조문]")
        for hit in lawHits:
            n += 1
            refTable[n] = dict(hit, type="law")
            lines.append(f"[{n}] {hit['law_name']} {formatArticle(hit['article_no'], hit['clause_no'])} "
                         f"({hit.get('title', '')})\n{hit.get('content', '')}")
    if materialHits:
        lines.append("\n[인정 기능성 문구]")
        for hit in materialHits:
            n += 1
            refTable[n] = dict(hit, type="material")
            claims = " / ".join(hit.get("claims") or [])
            lines.append(f"[{n}] 원료: {hit['material']} (인정번호 {hit['recog_no']}) / 인정 문구: {claims}")
    return "\n".join(lines), refTable


def buildPrompt(foodType, usage, context, query):
    """시스템 프롬프트 + 점검 조건(식품 종류·사용처) + Context + 질문."""
    usageLine = USAGE_HINT.get(usage, "지정 안 함")
    return f"""{SYSTEM_PROMPT}

[점검 조건]
식품 종류: {FOOD_TYPE_MAP[foodType]}
사용처: {usageLine}

{context}

[질문]
{query}

[답변]"""


# ============================================================
# LLM 출력 보정
# ============================================================

_BYTE_TOKEN_RE = re.compile(r'(?:<0x[0-9A-Fa-f]{2}>)+')


def fixByteFallbackTokens(text):
    """
    Ollama/llama.cpp가 병합하지 못한 byte-fallback 토큰(예: <0xEB><0x89><0xBC>)을
    UTF-8 문자로 복원한다.
    """
    def repl(m):
        raw = bytes(int(h, 16) for h in re.findall(r'0x([0-9A-Fa-f]{2})', m.group(0)))
        return raw.decode("utf-8", errors="replace")
    return _BYTE_TOKEN_RE.sub(repl, text)


# ============================================================
# LLM 출력 파싱
# ============================================================

VERDICT_MAP = {"큼": "high", "낮음": "low", "어려움": "unsure", "범위밖": "out_of_scope"}
VERDICT_ORDER = ("범위밖", "어려움", "낮음", "큼")   # "판단하기 어려움"이 "큼"보다 먼저 걸리도록

OUT_OF_SCOPE_ACTIONS = {
    "topic": [
        "이 도우미는 식품·건강기능식품의 표시·광고 문구만 점검합니다.",
        "영업 신고·인허가는 관할 시·군·구청, 제품 심사·신고는 식품의약품안전처에 문의하세요.",
    ],
    "no_basis": [
        "근거 조문을 찾지 못했습니다.",
        "관할 시·군·구청 식품 담당 부서나 식품의약품안전처에 문의하세요.",
    ],
}

NO_BASIS_PARSED = {
    "ok": True, "verdict": "out_of_scope", "verdict_reason": "", "actions": [], "basis_refs": [],
    "out_of_scope_reason": "no_basis", "food_type_mismatch": False,
}

_TAG_RE        = re.compile(r"\[\s*(판단\s*이유|판단|해야\s*할\s*일|근거|범위\s*밖\s*사유|식품\s*종류)\s*\]")
_LIST_MARK_RE  = re.compile(r"^\s*(?:\d+\s*[.)]|[-•·*])\s*")
_REF_LINE_RE   = re.compile(r"^\s*\[?(\d+)\]?\s*[|:：\-–.)]?\s*(.*)$")
_REF_LAW_HEAD_RE = re.compile(r"^.*?(?:제\d+조(?:의\d+)?(?:\s*\d+항)?|별표\s*\d+(?:의\d+)?)\s*[:：|]\s*")
_REF_LIST_RE   = re.compile(r"^[\d\s,\[\]]+$")


def _squash(text):
    return re.sub(r"\s+", "", text or "")


def splitSections(raw):
    """[태그] 기준으로 나눈 {태그(공백 제거): 내용}. 같은 태그가 다시 나오면 처음 것만."""
    text    = (raw or "").replace("**", "").replace("【", "[").replace("】", "]")
    matches = list(_TAG_RE.finditer(text))
    out     = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        key = _squash(m.group(1))
        if key not in out:
            out[key] = text[m.end():end].strip()
    return out


def parseVerdict(value):
    squashed = _squash(value)
    for word in VERDICT_ORDER:
        if word in squashed:
            return VERDICT_MAP[word]
    return None


def parseActions(value):
    actions = []
    for line in (value or "").split("\n"):
        line = _LIST_MARK_RE.sub("", line).strip()
        if line:
            actions.append(line)
    return actions


def parseBasisRefs(value):
    refs = []
    for line in (value or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        if _REF_LIST_RE.match(line):
            refs += [(int(n), "") for n in re.findall(r"\d+", line)]
            continue
        m = _REF_LINE_RE.match(line)
        if m:
            summary = _REF_LAW_HEAD_RE.sub("", (m.group(2) or "").strip(), count=1)   # "[1] 법령명 제8조 1항: 요약" → 요약
            refs.append((int(m.group(1)), summary.strip()))
    return refs


def parseAnswer(raw):
    """LLM 원문을 구조화. [판단]이 없거나 값을 알 수 없으면 ok=False."""
    sections = splitSections(raw)
    verdict  = parseVerdict(sections.get("판단", ""))
    if verdict is None:
        return dict(NO_BASIS_PARSED, ok=False, verdict=None, out_of_scope_reason=None)
    outReason = None
    if verdict == "out_of_scope":
        outReason = "no_basis" if "근거없음" in _squash(sections.get("범위밖사유", "")) else "topic"
    return {
        "ok":                  True,
        "verdict":             verdict,
        "verdict_reason":      sections.get("판단이유", "").strip(),
        "actions":             parseActions(sections.get("해야할일", "")),
        "basis_refs":          parseBasisRefs(sections.get("근거", "")),
        "out_of_scope_reason": outReason,
        "food_type_mismatch":  "불일치" in _squash(sections.get("식품종류", "")),
    }


# ============================================================
# 근거 채우기 / 응답 조립
# ============================================================

# 한국어 문장 끝(…다. …요. …음.)에서만 자른다. "1. ", "가. ", "표시ㆍ광고. 다만" 같은 번호·법령 문구에서 잘리지 않게.
_SENTENCE_END_RE = re.compile(r"(?<=[다요음함됨임][.!?])\s+")
# "1. 다.", "가.", "제1호 다목"처럼 항목 번호만 적은 요약 (설명이 없으므로 버리고 조문 제목으로 대신 채운다)
_BARE_ITEM_RE    = re.compile(r"^(?:제?\s*\d+\s*(?:호|\.)?\s*)?(?:[가-하]\s*(?:목|\.)?\s*)?$")
_LEAD_ITEM_RE    = re.compile(r"^(?:제?\s*\d+\s*(?:호|\.)\s*)?(?:[가-하]\s*(?:목|\.)\s+)?")
_COPIED_LAW_MARKS = ("■", "[별표", "<개정", "<신설")
_MATERIAL_ECHO   = ("인정 문구", "인정번호", "원료:")


_ARTICLE_HEAD_RE = re.compile(r"^\s*제\d+조(?:의\d+)?\([^)]*\)\s*(?:\d+항)?\s*")
_AMEND_TAG_RE    = re.compile(r"<(?:개정|신설|전문개정|본조신설)[^>]*>")
_ANNEX_TAG_RE    = re.compile(r"\[별표\s*\d+(?:의\d+)?\]")
_ANNEX_LAW_RE    = re.compile(r"■[^\[]*(?=\[)")          # "■ 식품 등의 … 시행령 [별표 1]" 의 법령명 부분
_TITLE_TAIL_RE   = re.compile(r"\s*\([^)]*관련\)\s*$")


def articleText(content, title=""):
    """화면 '조문 원문 보기'용 본문: 조문·별표 제목 줄과 개정 표시를 빼고, 호·목 줄바꿈은 살린다 (자르지 않음)."""
    text = _ANNEX_LAW_RE.sub("", content or "")
    text = _ANNEX_TAG_RE.sub("", text)
    if title:
        text = text.replace(title, "")
    while True:
        stripped = _ARTICLE_HEAD_RE.sub("", text, count=1)
        if stripped == text:
            break
        text = stripped
    lines = (re.sub(r"[ \t]+", " ", line).strip() for line in _AMEND_TAG_RE.sub("", text).split("\n"))
    return "\n".join(line for line in lines if line)


def titleSummary(title):
    """요약이 비었을 때 대신 보여 줄 한 줄: 조문 제목에서 '(제3조제1항 관련)' 같은 꼬리를 뗀다."""
    title = _TITLE_TAIL_RE.sub("", (title or "").strip())
    return f"이 조문은 ‘{title}’에 관한 조항입니다." if title else ""


def shortSummary(summary, entry):
    """화면에 보일 근거 요약: 첫 문장만. 인정 원료는 Context를 그대로 되풀이하거나
    인정 문구를 다시 적은 요약이면 버린다 (인정 문구는 화면에 따로 표시됨)."""
    s = (summary or "").strip()
    if entry["type"] == "material":
        if any(w in s for w in _MATERIAL_ECHO) or any(c and c in s for c in entry.get("claims") or []):
            return ""
    if any(w in s for w in _COPIED_LAW_MARKS):       # 조문 원문을 그대로 옮겨 적은 요약
        return ""
    s = _LEAD_ITEM_RE.sub("", s)                      # "1. 가. 설명…" → "설명…"
    if _BARE_ITEM_RE.match(s):
        return ""
    return _SENTENCE_END_RE.split(s, maxsplit=1)[0]


def resolveBasis(basisRefs, refTable):
    """번호 → 근거 항목. refTable에 없는 번호와 중복 번호는 버린다."""
    items = []
    used  = []
    for n, summary in basisRefs:
        entry = refTable.get(n)
        if entry is None or n in used:
            continue
        used.append(n)
        summary = shortSummary(summary, entry)
        if entry["type"] == "law":
            title = (entry.get("title") or "").strip()
            items.append({
                "type":           "law",
                "law_name":       entry["law_name"],
                "article":        formatArticle(entry["article_no"], entry["clause_no"]),
                "summary":        summary or titleSummary(title),
                "effective_date": entry.get("effective_date"),
                "title":          title,
                "content":        articleText(entry.get("content"), title),
            })
        else:
            items.append({
                "type":     "material",
                "material": entry["material"],
                "recog_no": entry["recog_no"],
                "claim":    " / ".join(entry.get("claims") or []),
                "summary":  summary,
            })
    return items, used


def claimRefsInQuery(query, refTable):
    """질문에 인정 기능성 문구가 그대로 들어 있는 원료 번호. LLM이 [근거]에 번호를 빠뜨려도 근거로 보여 주기 위함."""
    q = _squash(query)
    return [n for n, e in refTable.items()
            if q and e["type"] == "material" and any(_squash(c) and _squash(c) in q for c in e.get("claims") or [])]


def latestCollectedAt(entries):
    dates = [e.get("collected_at") for e in entries if e.get("collected_at")]
    return max(dates) if dates else None


def buildResponse(parsed, refTable, raw, fallbackCollectedAt=None, query=None):
    """parsed + refTable → API 응답 dict (spec 5.5)."""
    contextDate = latestCollectedAt(list(refTable.values())) or fallbackCollectedAt
    resp = {
        "success":             True,
        "verdict":             "unsure",
        "verdict_reason":      "",
        "actions":             [],
        "basis":               [],
        "out_of_scope_reason": None,
        "food_type_mismatch":  False,
        "collected_at":        contextDate,
        "disclaimer":          DISCLAIMER,
        "raw_fallback":        "",
    }
    if not parsed["ok"]:
        resp["raw_fallback"] = (raw or "").strip()
        return resp

    resp["verdict_reason"]     = parsed["verdict_reason"]
    resp["food_type_mismatch"] = parsed["food_type_mismatch"]
    if parsed["verdict"] == "out_of_scope":
        reason = parsed["out_of_scope_reason"] or "topic"
        resp.update(verdict="out_of_scope", out_of_scope_reason=reason,
                    actions=list(OUT_OF_SCOPE_ACTIONS[reason]))
        return resp

    refs = parsed["basis_refs"] + [(n, "") for n in claimRefsInQuery(query, refTable)]
    items, used = resolveBasis(refs, refTable)
    resp.update(verdict=parsed["verdict"], actions=parsed["actions"], basis=items,
                collected_at=latestCollectedAt([refTable[n] for n in used]) or contextDate)
    return resp
