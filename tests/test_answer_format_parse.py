from answer_format import (DISCLAIMER, NO_BASIS_PARSED, OUT_OF_SCOPE_ACTIONS, buildResponse, latestCollectedAt,
                           parseAnswer, resolveBasis)

REFS = {
    1: {"type": "law", "law_name": "식품 등의 표시·광고에 관한 법률", "article_no": "8", "clause_no": "1",
        "effective_date": "20250101", "collected_at": "2026-10-16"},
    2: {"type": "law", "law_name": "식품 등의 표시·광고에 관한 법률 시행령", "article_no": "별표 1", "clause_no": "0",
        "effective_date": None, "collected_at": "2026-10-17"},
    3: {"type": "material", "material": "홍삼", "recog_no": "2024-20", "claims": ["혈당 조절에 도움을 줄 수 있음"],
        "collected_at": "2026-10-15"},
}

NORMAL = """[판단] 큼
[판단이유] 일반식품에서 질병 치료 효과를 나타내는 표현은 부당한 표시·광고에 해당할 수 있습니다.
[해야할일]
1. 질병을 암시하는 표현을 뺍니다.
2) 확신이 없으면 관할 기관에 확인합니다.
[근거]
1 | 질병 예방·치료 표현 금지 조항입니다.
3 | 인정 문구는 혈당 조절까지입니다.
[식품종류] 일치"""


def test_parse_normal_answer():
    p = parseAnswer(NORMAL)
    assert p["ok"] and p["verdict"] == "high"
    assert p["verdict_reason"].startswith("일반식품에서")
    assert p["actions"] == ["질병을 암시하는 표현을 뺍니다.", "확신이 없으면 관할 기관에 확인합니다."]
    assert p["basis_refs"] == [(1, "질병 예방·치료 표현 금지 조항입니다."), (3, "인정 문구는 혈당 조절까지입니다.")]
    assert p["food_type_mismatch"] is False and p["out_of_scope_reason"] is None


def test_parse_all_verdict_words():
    for word, code in (("낮음", "low"), ("판단하기 어려움", "unsure"), ("위반 소지 큼", "high"), ("범위 밖", "out_of_scope")):
        assert parseAnswer(f"[판단] {word}\n[판단이유] 이유")["verdict"] == code


def test_parse_tolerates_bold_and_fullwidth_brackets_and_comma_refs():
    raw = "**[판단]** 어려움\n【판단이유】 근거 자료가 필요합니다.\n[근거] 2, 1\n[식품 종류] 불일치"
    p = parseAnswer(raw)
    assert p["verdict"] == "unsure" and p["verdict_reason"] == "근거 자료가 필요합니다."
    assert p["basis_refs"] == [(2, ""), (1, "")]
    assert p["food_type_mismatch"] is True


def test_parse_out_of_scope_reasons():
    assert parseAnswer("[판단] 범위밖\n[범위밖사유] 근거없음")["out_of_scope_reason"] == "no_basis"
    assert parseAnswer("[판단] 범위밖\n[범위밖사유] 주제")["out_of_scope_reason"] == "topic"
    assert parseAnswer("[판단] 범위밖")["out_of_scope_reason"] == "topic"


def test_parse_failure_when_verdict_missing_or_unknown():
    assert parseAnswer("그냥 설명만 했습니다.")["ok"] is False
    assert parseAnswer("[판단] 높음")["ok"] is False


def test_resolveBasis_maps_numbers_and_drops_unknown_or_duplicate():
    items, used = resolveBasis([(1, "요약1"), (9, "없는 번호"), (1, "중복"), (2, ""), (3, "인정")], REFS)
    assert used == [1, 2, 3]
    assert items[0] == {"type": "law", "law_name": "식품 등의 표시·광고에 관한 법률", "article": "제8조 1항",
                        "summary": "요약1", "effective_date": "20250101"}
    assert items[1]["article"] == "별표 1"
    assert items[2] == {"type": "material", "material": "홍삼", "recog_no": "2024-20",
                        "claim": "혈당 조절에 도움을 줄 수 있음", "summary": "인정"}


def test_latestCollectedAt_ignores_empty():
    assert latestCollectedAt([{"collected_at": "2026-10-15"}, {"collected_at": ""}, {"collected_at": "2026-10-17"}]) == "2026-10-17"
    assert latestCollectedAt([]) is None


def test_buildResponse_normal_uses_dates_of_cited_refs():
    resp = buildResponse(parseAnswer(NORMAL), REFS, NORMAL)
    assert resp["success"] is True and resp["verdict"] == "high"
    assert [b["type"] for b in resp["basis"]] == ["law", "material"]
    assert resp["collected_at"] == "2026-10-16"
    assert resp["disclaimer"] == DISCLAIMER and resp["raw_fallback"] == ""


def test_buildResponse_out_of_scope_clears_basis_and_uses_fixed_actions():
    raw = "[판단] 범위밖\n[판단이유] 영업 신고 질문입니다.\n[근거] 1\n[범위밖사유] 주제"
    resp = buildResponse(parseAnswer(raw), REFS, raw)
    assert resp["verdict"] == "out_of_scope" and resp["out_of_scope_reason"] == "topic"
    assert resp["basis"] == [] and resp["actions"] == OUT_OF_SCOPE_ACTIONS["topic"]
    assert resp["collected_at"] == "2026-10-17"


def test_buildResponse_parse_failure_keeps_raw():
    resp = buildResponse(parseAnswer("형식 없는 답"), REFS, "형식 없는 답")
    assert resp["verdict"] == "unsure" and resp["raw_fallback"] == "형식 없는 답" and resp["basis"] == []


def test_buildResponse_in_scope_without_valid_refs_is_not_refused():
    raw = "[판단] 어려움\n[판단이유] 이유\n[근거] 7"
    resp = buildResponse(parseAnswer(raw), REFS, raw)
    assert resp["verdict"] == "unsure" and resp["basis"] == []


def test_buildResponse_no_hits_uses_no_basis_and_fallback_date():
    resp = buildResponse(NO_BASIS_PARSED, {}, "", "2026-10-16")
    assert resp["verdict"] == "out_of_scope" and resp["out_of_scope_reason"] == "no_basis"
    assert resp["actions"] == OUT_OF_SCOPE_ACTIONS["no_basis"] and resp["collected_at"] == "2026-10-16"


def test_parse_gemma_style_bracket_refs_with_law_prefix():
    # gemma4:e4b 실제 출력 형식 (2026-10-15 확인): "[n] 법령명 제n조 n항: 요약" / "[n] 요약"
    raw = ("[판단] 큼\n[판단이유] 이유\n[근거]\n"
           "[1] 식품 등의 표시·광고에 관한 법률 제8조 1항: 일반식품이 질병 예방 효능을 광고할 수 없습니다.\n"
           "[2] 홍삼의 인정 문구는 혈당 조절까지입니다.\n[식품종류] 일치")
    assert parseAnswer(raw)["basis_refs"] == [(1, "일반식품이 질병 예방 효능을 광고할 수 없습니다."),
                                               (2, "홍삼의 인정 문구는 혈당 조절까지입니다.")]
