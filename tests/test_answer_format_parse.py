from answer_format import (DISCLAIMER, NO_BASIS_PARSED, OUT_OF_SCOPE_ACTIONS, buildResponse, latestCollectedAt,
                           articleText, parseAnswer, resolveBasis, shortSummary)

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
                        "summary": "요약1", "effective_date": "20250101", "title": "", "content": ""}
    assert items[1]["article"] == "별표 1"
    assert items[2] == {"type": "material", "material": "홍삼", "recog_no": "2024-20",
                        "claim": "혈당 조절에 도움을 줄 수 있음", "summary": "인정"}


def test_resolveBasis_drops_material_summary_that_repeats_context():
    echo = "원료: 홍삼 (인정번호 2024-20) / 인정 문구: 혈당 조절에 도움을 줄 수 있음"
    items, _ = resolveBasis([(3, echo)], REFS)
    assert items[0]["summary"] == ""
    items, _ = resolveBasis([(3, "혈당 조절에 도움을 줄 수 있음까지만 인정됩니다.")], REFS)
    assert items[0]["summary"] == ""


def test_resolveBasis_keeps_only_first_sentence_of_summary():
    items, _ = resolveBasis([(1, "질병 치료 표현을 금지합니다. 그래서 이 문구는 문제가 됩니다. 추가 설명입니다.")], REFS)
    assert items[0]["summary"] == "질병 치료 표현을 금지합니다."


def test_shortSummary_does_not_cut_at_list_numbers():
    law = {"type": "law"}
    s = "1. 질병의 예방ㆍ치료에 효능이 있는 것으로 인식할 우려가 있는 표시 또는 광고에 해당합니다. 추가 설명입니다."
    assert shortSummary(s, law) == "질병의 예방ㆍ치료에 효능이 있는 것으로 인식할 우려가 있는 표시 또는 광고에 해당합니다."
    s = "가. 질병 발생을 예방한다는 표시ㆍ광고. 다만 예외가 있습니다."
    assert shortSummary(s, law) == "질병 발생을 예방한다는 표시ㆍ광고. 다만 예외가 있습니다."


def test_shortSummary_drops_bare_item_numbers():
    for s in ("1.", "1. 다.", "가.", "3. 나 ", "제1호 다목"):
        assert shortSummary(s, {"type": "law"}) == ""


LONG_ARTICLE = ("제8조(부당한 표시 또는 광고행위의 금지) 1항\n① 누구든지 식품등의 명칭 등에 관하여 "
                "다음 각 호의 표시 또는 광고를 하여서는 아니 된다. <개정 2021.8.17>\n"
                "1. 질병의 예방ㆍ치료에 효능이 있는 것으로 인식할 우려가 있는 표시 또는 광고\n" + "2. 기타 " * 40)


def test_shortSummary_strips_leading_item_numbers():
    s = "1. 가. '면역력'은 질병의 발생을 예방한다는 내용으로 해석될 여지가 있어 주의가 필요합니다."
    assert shortSummary(s, {"type": "law"}) == "'면역력'은 질병의 발생을 예방한다는 내용으로 해석될 여지가 있어 주의가 필요합니다."


def test_shortSummary_drops_copied_article_text():
    s = ("■ 식품 등의 표시ㆍ광고에 관한 법률 시행령 [별표 1] <개정 2023. 12. 26.> 부당한 표시 또는 광고의 내용"
         "(제3조제1항 관련) 나. 질병 또는 질병군에 치료 효과가 있다는 내용의 표시ㆍ광고")
    assert shortSummary(s, {"type": "law"}) == ""


def test_resolveBasis_law_sends_title_and_full_article_text():
    refs = {1: dict(REFS[1], title="부당한 표시 또는 광고행위의 금지", content=LONG_ARTICLE)}
    items, _ = resolveBasis([(1, "‘면역력’은 질병 예방 효과처럼 보일 수 있어요.")], refs)
    item = items[0]
    assert item["title"] == "부당한 표시 또는 광고행위의 금지"
    text = item["content"]
    assert text.startswith("① 누구든지 식품등의 명칭") and "<개정" not in text and "제8조(" not in text
    assert "\n1. 질병의 예방" in text            # 호 단위 줄바꿈은 살린다
    assert text.endswith("2. 기타")             # 잘라내지 않는다
    assert "excerpt" not in item


def test_resolveBasis_law_fills_empty_summary_from_title():
    refs = {1: dict(REFS[1], title="부당한 표시 또는 광고의 내용(제3조제1항 관련)", content="본문")}
    for summary in ("", "1. 다."):
        items, _ = resolveBasis([(1, summary)], refs)
        assert items[0]["summary"] == "이 조문은 ‘부당한 표시 또는 광고의 내용’에 관한 조항입니다."
    items, _ = resolveBasis([(1, "")], {1: dict(REFS[1], content="본문")})   # 제목도 없으면 빈칸
    assert items[0]["summary"] == ""


def test_articleText_strips_repeated_heading():
    assert articleText("제8조(광고의 기준)\n제8조(광고의 기준) 법 제7조제2항에 따른 사항은 별표 6과 같다.") == \
        "법 제7조제2항에 따른 사항은 별표 6과 같다."


def test_articleText_strips_annex_heading():
    title = "부당한 표시 또는 광고의 내용(제3조제1항 관련)"
    content = (f"[별표 1] {title} ■ 식품 등의 표시ㆍ광고에 관한 법률 시행령 [별표 1] {title} "
               "1. 질병의 예방ㆍ치료에 효능이 있는 것으로 인식할 우려가 있는 표시 또는 광고")
    assert articleText(content, title) == "1. 질병의 예방ㆍ치료에 효능이 있는 것으로 인식할 우려가 있는 표시 또는 광고"


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


GEMMA_NO_NUMBER = """[판단] 낮음
[판단이유] 사용하려는 문구는 건강기능식품의 인정 기능성 문구에 명확히 포함되어 있어 사용이 가능합니다.
[해야할일]
1. 현재 사용하려는 문구는 인정된 기능성 문구이므로 사용 가능합니다.
[근거]
[인정 기능성 문구] | '혈당 조절에 도움을 줄 수 있음'은 홍삼 원료에 대해 인정된 기능성 문구와 일치합니다.
[범위밖사유] 근거없음
[식품종류] 일치"""


def test_buildResponse_adds_material_whose_claim_is_in_query_when_not_cited():
    query = "홍삼 상세페이지에 “혈당 조절에 도움을 줄 수 있음”이라고 써도 되나요?"
    resp = buildResponse(parseAnswer(GEMMA_NO_NUMBER), REFS, GEMMA_NO_NUMBER, query=query)
    assert resp["verdict"] == "low"
    assert [(b["type"], b.get("recog_no")) for b in resp["basis"]] == [("material", "2024-20")]
    assert resp["collected_at"] == "2026-10-15"


def test_buildResponse_matched_material_not_duplicated_or_added_without_match():
    query = "홍삼에 “혈당 조절에 도움을 줄 수 있음”이라고 써도 되나요?"
    resp = buildResponse(parseAnswer(NORMAL), REFS, NORMAL, query=query)
    assert [b.get("recog_no") for b in resp["basis"]] == [None, "2024-20"]
    resp = buildResponse(parseAnswer(GEMMA_NO_NUMBER), REFS, GEMMA_NO_NUMBER, query="홍삼으로 당뇨를 치료합니다")
    assert resp["basis"] == []


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
