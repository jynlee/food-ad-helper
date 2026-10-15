# -*- coding: utf-8 -*-
"""
metrics.py
평가 지표 계산 (순수 함수). 정답 근거는 "법령명 제n조" / "법령명 별표 n" 단위로 비교한다(항은 무시).
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "common"))
from answer_format import formatArticle

DECISIVE_RE = re.compile(r"위법입니다|불법입니다|위반입니다")
ARTICLE_RE  = re.compile(r"(제\d+조(?:의\d+)?|별표\s*\d+(?:의\d+)?)")

METRIC_LABELS = {
    "hit_at_5":       "근거 검색 적중률 (hit@5)",
    "basis_shown":    "근거 표기율",
    "refusal_ok":     "거절 정확도",
    "citation_match": "인용 일치율",
    "no_decisive":    "단정 회피율",
    "verdict_match":  "판단 일치율",
    "material_match": "인정 문구 대조 정확도",
}


def articleKey(lawName, article):
    m = ARTICLE_RE.search(article or "")
    return f"{lawName} {m.group(1) if m else article}"


def hitAtK(lawHits, gold):
    keys = {articleKey(h["law_name"], formatArticle(h["article_no"], h["clause_no"])) for h in lawHits}
    return bool(keys & set(gold))


def basisKeys(basis):
    return {articleKey(b["law_name"], b["article"]) for b in basis if b.get("type") == "law"}


def recogNos(basis):
    return {b["recog_no"] for b in basis if b.get("type") == "material"}


def scoreAnswer(q, resp):
    """문구 하나의 지표별 결과. 해당 없는 지표는 넣지 않거나 None."""
    out = {"verdict_match": resp["verdict"] == q["expected_verdict"]}
    if q["category"] in ("in_scope", "variant"):
        text = (resp.get("verdict_reason") or "") + " " + " ".join(resp.get("actions") or [])
        out["basis_shown"]    = any(b.get("type") == "law" for b in resp.get("basis") or [])
        out["no_decisive"]    = DECISIVE_RE.search(text) is None
        out["citation_match"] = bool(basisKeys(resp.get("basis") or []) & set(q["gold_basis"])) if q["gold_basis"] else None
    else:
        out["refusal_ok"] = resp["verdict"] == "out_of_scope"
    if q["food_type"] == "health" and q.get("gold_recog_no"):
        out["material_match"] = out["verdict_match"] and bool(set(q["gold_recog_no"]) & recogNos(resp.get("basis") or []))
    return out


def summarize(rows):
    """{지표: (맞은 수, 대상 수)}. None은 대상에서 뺀다."""
    total = {}
    for row in rows:
        for key, value in row.items():
            if value is None:
                continue
            hit, n = total.get(key, (0, 0))
            total[key] = (hit + (1 if value else 0), n + 1)
    return total


def formatTable(summary, order=None):
    lines = ["| 지표 | 결과 | 비율 |", "|---|---|---|"]
    for key in order or summary:
        if key in summary:
            hit, n = summary[key]
            lines.append(f"| {METRIC_LABELS.get(key, key)} | {hit}/{n} | {hit / n * 100:.1f}% |")
    return "\n".join(lines)
