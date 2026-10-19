import pytest

import suggest

MAT_HIT = {"rank": 1, "score": 1.0, "recog_no": "2024-20", "material": "바나바잎 추출물",
           "claims": ["식후 혈당상승 억제에 도움을 줄 수 있음"], "daily_intake": "", "caution": "",
           "collected_at": "2026-10-15"}
ORIGINAL = {"verdict": "high", "verdict_reason": "‘피로 회복’은 질병 치료 효과처럼 보일 수 있어요.",
            "basis": [{"type": "law", "summary": "‘피로 회복에 최고’가 이 조항에 걸릴 수 있어요."}]}


def out(phrase, change="효능 표현을 뺐어요."):
    return f"[추천문구] {phrase}\n[바꾼점] {change}"


@pytest.fixture
def env(monkeypatch):
    log = {"llm": [], "checked": [], "answers": [], "verdicts": [], "materials": 0}

    def fakeMat(osClient, cfg, query, topK=3, queryVector=None):
        log["materials"] += 1
        return [dict(MAT_HIT)]

    def fakeLlm(cfg, prompt):
        log["llm"].append(prompt)
        return log["answers"].pop(0)

    def check(phrase):
        log["checked"].append(phrase)
        verdict = log["verdicts"].pop(0)
        return {"verdict": verdict, "verdict_reason": f"{phrase} 판단 이유"}

    monkeypatch.setattr(suggest, "searchMaterials", fakeMat)
    monkeypatch.setattr(suggest, "generateAnswer", fakeLlm)
    monkeypatch.setattr(suggest, "embedQuery", lambda cfg, q: [0.1])
    log["check"] = check
    return log


def run(env, query="우리 카페 홍삼차, 피로 회복에 최고!", foodType="general"):
    return suggest.runSuggest(None, {}, query, foodType, "sns", ORIGINAL, env["check"])


def test_parse_suggestion_reads_phrase_and_change():
    got = suggest.parseSuggestion("[추천문구] “진하게 우려낸 홍삼차”\n[바꾼점] 효능 표현을 뺐어요.")
    assert got == {"phrase": "진하게 우려낸 홍삼차", "change": "효능 표현을 뺐어요."}


def test_parse_suggestion_without_phrase_is_none():
    assert suggest.parseSuggestion("죄송하지만 만들 수 없습니다.") is None


def test_banned_words_found_but_recognized_claim_words_allowed():
    assert suggest.findBannedWords("피로 회복에 최고인 홍삼차") == ["회복", "최고"]
    assert suggest.findBannedWords("식후 혈당상승 억제에 도움", allowedText="식후 혈당상승 억제에 도움을 줄 수 있음") == []


def test_prompt_gives_reason_and_basis_but_not_law_text():
    # 법령 전문 대신 점검 결과(이유·문제 표현)만 줘서 읽는 시간을 줄인다
    prompt = suggest.buildSuggestPrompt("general", "sns", "홍삼차 피로 회복에 최고!", ORIGINAL)
    assert "홍삼차 피로 회복에 최고!" in prompt and ORIGINAL["verdict_reason"] in prompt
    assert ORIGINAL["basis"][0]["summary"] in prompt and "[법령 조문]" not in prompt
    assert "지어내지" in prompt and "SNS" in prompt


def test_prompt_keeps_product_kind_and_forbids_new_ingredients():
    prompt = suggest.buildSuggestPrompt("health", "page", "이 제품 먹으면 혈당이 쑥", ORIGINAL,
                                        claims=["식후 혈당상승 억제에 도움을 줄 수 있음"])
    assert "제품 종류" in prompt and "곁들임" in prompt
    assert "식후 혈당상승 억제에 도움을 줄 수 있음" in prompt


def test_first_candidate_low_returns_after_one_check(env):
    env["answers"] = [out("진하게 우려낸 우리 카페 홍삼차")]
    env["verdicts"] = ["low"]
    got = run(env)
    assert got == {"success": True, "phrase": "진하게 우려낸 우리 카페 홍삼차", "change": "효능 표현을 뺐어요.",
                   "tries": 1}
    assert env["checked"] == ["진하게 우려낸 우리 카페 홍삼차"] and len(env["llm"]) == 1
    assert env["materials"] == 0   # 일반식품은 검색 없이 바로 만든다


def test_failed_check_reason_goes_into_second_try(env):
    env["answers"] = [out("홍삼차로 활력 충전"), out("따뜻한 홍삼차 한 잔")]
    env["verdicts"] = ["unsure", "low"]
    got = run(env)
    assert got["success"] and got["phrase"] == "따뜻한 홍삼차 한 잔" and got["tries"] == 2
    assert "홍삼차로 활력 충전" in env["llm"][1] and "홍삼차로 활력 충전 판단 이유" in env["llm"][1]


def test_two_failed_checks_give_up(env):
    env["answers"] = [out("홍삼차로 활력 충전"), out("홍삼차로 기운 충전")]
    env["verdicts"] = ["high", "unsure"]
    got = run(env)
    assert got == {"success": False, "phrase": "", "change": "", "tries": 2}
    assert len(env["checked"]) == 2


def test_banned_word_is_rewritten_before_spending_a_check(env):
    env["answers"] = [out("피로 회복 홍삼차"), out("따뜻한 홍삼차 한 잔")]
    env["verdicts"] = ["low"]
    got = run(env)
    assert got["success"] and env["checked"] == ["따뜻한 홍삼차 한 잔"]
    assert "회복" in env["llm"][1] and "피로 회복 홍삼차" in env["llm"][1]


def test_unparsable_answer_counts_as_failed_try(env):
    env["answers"] = ["형식 없는 답", "또 형식 없는 답"]
    got = run(env)
    assert got["success"] is False and env["checked"] == []


def test_health_food_searches_materials_and_allows_recognized_claim(env):
    env["answers"] = [out("바나바잎 추출물, 식후 혈당상승 억제에 도움을 줄 수 있음")]
    env["verdicts"] = ["low"]
    got = run(env, query="혈당 뚝 바나바", foodType="health")
    assert got["success"] and env["materials"] == 1
    assert "식후 혈당상승 억제에 도움을 줄 수 있음" in env["llm"][0]


def test_prompt_allows_only_ingredients_from_original():
    # 2026-10-19: "들기름" → "참깨와 들깨를 사용하여 만든 들기름"처럼 없던 재료를 지어냈다
    prompt = suggest.buildSuggestPrompt("general", "page", "국내산 100% 들기름, 치매 예방에 좋아요", ORIGINAL)
    assert "재료 이름은 원래 문구에 있는 것만" in prompt


def test_prompt_forbids_invented_time_and_frequency():
    # 2026-10-19: "우리 동네 최고의 김밥" → "매일 아침 정성껏 말아낸 우리 동네 김밥"처럼 없던 때·횟수를 지어냈다
    prompt = suggest.buildSuggestPrompt("general", "sns", "우리 동네 최고의 김밥", ORIGINAL)
    assert "언제·얼마나 자주" in prompt
    assert "매일 아침 새로 무치는" not in prompt      # 좋은 예가 지어내기를 가르치면 안 됨
