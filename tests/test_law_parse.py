import json
from pathlib import Path

import pytest

from law_parse import (INDEX_NAME, chunkText, flattenText, hashContent, parseAdmrulArticles,
                       parseAnnexes, parseClauses, parseDate, pickTarget, planChanges)

FIX = Path(__file__).parent / "fixtures"
LAW = json.loads((FIX / "law_sample.json").read_text(encoding="utf-8"))
ADM = json.loads((FIX / "admrul_sample.json").read_text(encoding="utf-8"))


def makeMeta(articles=None, annexes=None, sourceKey="law_100"):
    info = {"name": "식품 등의 표시·광고에 관한 법률", "kind": "법률", "food_type": "공통"}
    if articles is not None:
        info["articles"] = articles
    if annexes is not None:
        info["annexes"] = annexes
    return {"info": info, "lawId": "100", "sourceKey": sourceKey,
            "effectiveDate": "20250101", "collectedAt": "2026-10-16"}


def annexUnits(data):
    return data["법령"]["별표"]["별표단위"]


# ---------- 기본 유틸 ----------

def test_flattenText_flattens_nested_lists_and_newlines():
    assert flattenText([["a", "b\nc"], "d", None]) == ["a", "b", "c", "d"]


def test_chunkText_splits_by_length_without_breaking_lines():
    lines = ["가" * 500, "나" * 500, "다" * 500]
    chunks = chunkText(lines, maxLen=1200)
    assert len(chunks) == 2
    assert chunks[0] == "가" * 500 + "\n" + "나" * 500
    assert chunks[1] == "다" * 500


def test_parseDate_normalizes_or_returns_none():
    assert parseDate("2025-01-01") == "20250101"
    assert parseDate("2025.01.01") == "20250101"
    assert parseDate("") is None


# ---------- 법령 조문 ----------

def test_parseClauses_builds_clause_docs_and_skips_headings():
    docs = parseClauses(LAW, makeMeta())
    ids = [d["_id"] for d in docs]
    assert ids == ["law_100_0001001_0", "law_100_0008001_1", "law_100_0008001_2", "law_100_0008002_1"]
    assert all(d["_index"] == INDEX_NAME for d in docs)


def test_parseClauses_joins_items_and_subitems_into_clause():
    doc = parseClauses(LAW, makeMeta())[1]["_source"]
    assert doc["article_no"] == "8" and doc["clause_no"] == "1"
    assert doc["content"].startswith("제8조(부당한 표시 또는 광고행위의 금지) 1항\n")
    assert "1. 질병의 예방ㆍ치료에 효능" in doc["content"]
    assert "가. 예시 목 내용" in doc["content"]
    assert doc["content_hash"] == hashContent(doc["content"])
    assert doc["food_type"] == "공통" and doc["collected_at"] == "2026-10-16"
    assert doc["source_key"] == "law_100" and doc["law_id"] == "100"


def test_parseClauses_handles_branch_article_and_single_clause_dict():
    doc = parseClauses(LAW, makeMeta())[3]["_source"]
    assert doc["article_no"] == "8의2"
    assert "항이 하나뿐이면" in doc["content"]


def test_parseClauses_article_filter():
    docs = parseClauses(LAW, makeMeta(articles=["8"]))
    assert [d["_source"]["article_no"] for d in docs] == ["8", "8"]


# ---------- 별표 ----------

def test_parseAnnexes_keeps_annex_and_skips_forms():
    docs = parseAnnexes(annexUnits(LAW), makeMeta())
    assert [d["_id"] for d in docs] == ["law_100_annex1_p1"]
    src = docs[0]["_source"]
    assert src["article_no"] == "별표 1" and src["clause_no"] == "0"
    assert src["content"].startswith("[별표 1] 부당한 표시 또는 광고의 내용\n")
    assert "질병 또는 질병군의 발생을 예방" in src["content"]


def test_parseAnnexes_filter_and_empty_filter():
    assert parseAnnexes(annexUnits(LAW), makeMeta(annexes=["2"])) == []
    assert parseAnnexes(annexUnits(LAW), makeMeta(annexes=[])) == []


def test_parseAnnexes_reads_six_digit_number_with_branch():
    units = [{"별표번호": "000102", "별표제목": "가지 별표", "별표내용": "내용"}]
    docs = parseAnnexes(units, makeMeta())
    assert docs[0]["_source"]["article_no"] == "별표 1의2"


def test_parseAnnexes_splits_long_annex_into_parts():
    units = [{"별표번호": "0003", "별표제목": "긴 별표", "별표내용": ["가" * 700, "나" * 700]}]
    docs = parseAnnexes(units, makeMeta())
    assert [d["_id"] for d in docs] == ["law_100_annex3_p1", "law_100_annex3_p2"]


# ---------- 행정규칙(고시) ----------

def test_parseAdmrulArticles_groups_lines_by_article():
    meta = makeMeta(sourceKey="admrul_200")
    lines = flattenText(ADM["AdmRulService"]["조문내용"])
    docs = parseAdmrulArticles(lines, meta)
    assert [d["_id"] for d in docs] == ["admrul_200_1", "admrul_200_2", "admrul_200_3의2"]
    second = docs[1]["_source"]
    assert second["title"] == "정의"
    assert "2. 두 번째 정의" in second["content"]
    assert docs[2]["_source"]["article_no"] == "3의2"


def test_parseAdmrulArticles_keeps_first_when_number_repeats():
    meta = makeMeta(sourceKey="admrul_200")
    docs = parseAdmrulArticles(["제1조(목적) 본문", "제1조(시행일) 부칙"], meta)
    assert len(docs) == 1 and "본문" in docs[0]["_source"]["content"]


# ---------- 이름 매칭 ----------

def test_pickTarget_prefers_exact_name_over_longer_names():
    cands = [{"법령명한글": "식품 등의 표시ㆍ광고에 관한 법률 시행령"},
             {"법령명한글": "식품 등의 표시ㆍ광고에 관한 법률"},
             {"법령명한글": "식품 등의 표시ㆍ광고에 관한 법률 시행규칙"}]
    found = pickTarget(cands, "식품 등의 표시·광고에 관한 법률", "법령명한글")
    assert found["법령명한글"] == "식품 등의 표시ㆍ광고에 관한 법률"


def test_pickTarget_accepts_single_partial_match_and_dict_candidate():
    cand = {"행정규칙명": "식품등의 부당한 표시 또는 광고의 내용 기준"}
    assert pickTarget(cand, "부당한 표시 또는 광고의 내용 기준", "행정규칙명") == cand


def test_pickTarget_raises_when_ambiguous_or_missing():
    cands = [{"n": "가 기준 A"}, {"n": "가 기준 B"}]
    with pytest.raises(LookupError):
        pickTarget(cands, "가 기준", "n")
    with pytest.raises(LookupError):
        pickTarget([], "없는 법", "n")


# ---------- 변경 계획 ----------

def doc(docId, content):
    return {"_index": INDEX_NAME, "_id": docId,
            "_source": {"law_name": "법", "source_key": "law_100", "article_no": "1", "clause_no": "0",
                        "content": content, "content_hash": hashContent(content)}}


def test_planChanges_classifies_added_modified_unchanged_removed():
    existing = {
        "a": {"content": "같음", "content_hash": hashContent("같음"), "article_no": "1", "clause_no": "0", "law_name": "법"},
        "b": {"content": "예전", "content_hash": hashContent("예전"), "article_no": "2", "clause_no": "0", "law_name": "법"},
        "gone": {"content": "삭제됨", "content_hash": hashContent("삭제됨"), "article_no": "9", "clause_no": "0", "law_name": "법"},
    }
    plan = planChanges([doc("a", "같음"), doc("b", "새로움"), doc("c", "추가")], existing)
    assert [d["_id"] for d in plan["toIndex"]] == ["b", "c"]
    assert plan["unchangedIds"] == ["a"]
    assert plan["removedIds"] == ["gone"]
    assert sorted(h["change_type"] for h in plan["history"]) == ["added", "modified", "removed"]


def test_planChanges_rerun_with_same_docs_changes_nothing():
    docs = [doc("a", "같음"), doc("b", "둘")]
    existing = {d["_id"]: dict(d["_source"]) for d in docs}
    plan = planChanges(docs, existing)
    assert plan["toIndex"] == [] and plan["removedIds"] == [] and plan["history"] == []
    assert plan["unchangedIds"] == ["a", "b"]
