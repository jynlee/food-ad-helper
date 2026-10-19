from answer_format import (DISCLAIMER, SYSTEM_PROMPT, buildContext, buildPrompt, fixByteFallbackTokens,
                           formatArticle)

LAW1 = {"law_name": "식품 등의 표시·광고에 관한 법률", "article_no": "8", "clause_no": "1",
        "title": "부당한 표시 또는 광고행위의 금지", "content": "제8조(...) 1항\n본문", "collected_at": "2026-10-16"}
ANNEX = {"law_name": "식품 등의 표시·광고에 관한 법률 시행령", "article_no": "별표 1", "clause_no": "0",
         "title": "부당한 표시 또는 광고의 내용", "content": "[별표 1] ...", "collected_at": "2026-10-16"}
MAT = {"recog_no": "2024-20", "material": "홍삼", "claims": ["혈당 조절에 도움을 줄 수 있음"],
       "collected_at": "2026-10-15"}


def test_formatArticle():
    assert formatArticle("8", "1") == "제8조 1항"
    assert formatArticle("8", "0") == "제8조"
    assert formatArticle("3의2", "") == "제3조의2"
    assert formatArticle("별표 1", "0") == "별표 1"


def test_buildContext_numbers_laws_then_materials():
    context, refs = buildContext([LAW1, ANNEX], [MAT])
    assert sorted(refs) == [1, 2, 3]
    assert refs[1]["type"] == "law" and refs[3]["type"] == "material"
    assert "[법령 조문]" in context
    assert "[1] 식품 등의 표시·광고에 관한 법률 제8조 1항 (부당한 표시 또는 광고행위의 금지)" in context
    assert "[2] 식품 등의 표시·광고에 관한 법률 시행령 별표 1 (부당한 표시 또는 광고의 내용)" in context
    assert "[인정 기능성 문구]" in context
    assert "[3] 원료: 홍삼 (인정번호 2024-20) / 인정 문구: 혈당 조절에 도움을 줄 수 있음" in context


def test_buildContext_omits_material_section_when_empty():
    context, refs = buildContext([LAW1], [])
    assert "[인정 기능성 문구]" not in context and list(refs) == [1]


def test_buildPrompt_includes_conditions_context_and_query():
    prompt = buildPrompt("health", "sns", "CTX", "혈당 관리에 최고!")
    assert prompt.startswith(SYSTEM_PROMPT)
    assert "식품 종류: 건강기능식품" in prompt
    assert "해시태그" in prompt
    assert "CTX" in prompt and prompt.rstrip().endswith("[답변]")
    assert "[질문]\n혈당 관리에 최고!" in prompt


def test_buildPrompt_without_usage():
    assert "사용처: 지정 안 함" in buildPrompt("general", None, "CTX", "q")


def test_system_prompt_demands_tag_format_and_number_citations():
    for tag in ("[판단]", "[판단이유]", "[해야할일]", "[근거]", "[범위밖사유]", "[식품종류]"):
        assert tag in SYSTEM_PROMPT
    assert "번호로만" in SYSTEM_PROMPT


def test_disclaimer_text_is_exact():
    assert DISCLAIMER == "법령 정보 안내이며 법률 자문이 아닙니다. 확신이 없으면 관할 기관이나 전문가에게 확인하세요."


def test_fixByteFallbackTokens_restores_hangul():
    assert fixByteFallbackTokens("그래<0xEB><0x89><0xBC>") == "그래뉼"


def test_system_prompt_treats_plain_description_and_clean_ad_as_low():
    # 2026-10-19: "쫀득한 식감" → 어려움, 효능 표현 없는 홍보 문구 → 범위밖 으로 잘못 판단해서 고쳤다
    assert "쫀득한" in SYSTEM_PROMPT and "범위밖이 아니라 낮음" in SYSTEM_PROMPT


def test_system_prompt_puts_efficacy_before_plain_description():
    # 2026-10-19: "우리 카페 쌍화차, 감기 뚝! 면역력 최고"가 평범한 말 규칙 때문에 낮음으로 나와서 판단 순서를 못 박았다
    assert "하나라도 있으면 나머지가 평범해도 큼" in SYSTEM_PROMPT


def test_system_prompt_keeps_exaggeration_unsure_even_about_taste():
    # 2026-10-19: 평범한 말 규칙을 넣은 뒤 "우리 동네 최고의 김밥", "무첨가 수제 딸기잼"이 낮음으로 나왔다 (전에는 어려움)
    assert "맛을 말하는 데 쓰여도 어려움" in SYSTEM_PROMPT
