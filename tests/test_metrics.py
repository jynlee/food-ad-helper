from metrics import METRIC_LABELS, articleKey, hitAtK, scoreAnswer, summarize

LAW = "식품 등의 표시·광고에 관한 법률"


def test_articleKey_drops_clause():
    assert articleKey(LAW, "제8조 1항") == f"{LAW} 제8조"
    assert articleKey(LAW, "제3조의2") == f"{LAW} 제3조의2"
    assert articleKey(LAW, "별표 1") == f"{LAW} 별표 1"


def test_hitAtK_matches_on_article_level():
    hits = [{"law_name": LAW, "article_no": "8", "clause_no": "2"}]
    assert hitAtK(hits, [f"{LAW} 제8조"]) is True
    assert hitAtK(hits, [f"{LAW} 제9조"]) is False


def question(**kw):
    base = {"category": "in_scope", "food_type": "general", "expected_verdict": "high",
            "gold_basis": [f"{LAW} 제8조"], "gold_recog_no": []}
    base.update(kw)
    return base


def response(**kw):
    base = {"verdict": "high", "verdict_reason": "위반 소지가 큽니다.", "actions": ["표현을 뺍니다."],
            "basis": [{"type": "law", "law_name": LAW, "article": "제8조 1항"}]}
    base.update(kw)
    return base


def test_scoreAnswer_in_scope_all_good():
    s = scoreAnswer(question(), response())
    assert s == {"verdict_match": True, "basis_shown": True, "no_decisive": True, "citation_match": True}


def test_scoreAnswer_detects_decisive_wording_and_missing_basis():
    s = scoreAnswer(question(), response(verdict_reason="이 문구는 위법입니다.", basis=[]))
    assert s["no_decisive"] is False and s["basis_shown"] is False and s["citation_match"] is False


def test_scoreAnswer_citation_not_applicable_without_gold():
    assert scoreAnswer(question(gold_basis=[]), response())["citation_match"] is None


def test_scoreAnswer_refusal():
    s = scoreAnswer(question(category="out_of_scope", expected_verdict="out_of_scope"),
                    response(verdict="out_of_scope", basis=[]))
    assert s == {"verdict_match": True, "refusal_ok": True}


def test_scoreAnswer_material_match():
    q = question(food_type="health", gold_recog_no=["2024-20"])
    good = response(basis=[{"type": "material", "recog_no": "2024-20", "material": "홍삼"}])
    assert scoreAnswer(q, good)["material_match"] is True
    assert scoreAnswer(q, response())["material_match"] is False


def test_summarize_counts_only_applicable():
    rows = [{"verdict_match": True, "citation_match": None}, {"verdict_match": False, "citation_match": True}]
    assert summarize(rows) == {"verdict_match": (1, 2), "citation_match": (1, 1)}
    assert set(METRIC_LABELS) >= {"verdict_match", "basis_shown", "no_decisive", "citation_match",
                                  "refusal_ok", "material_match"}
