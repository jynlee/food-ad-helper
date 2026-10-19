import pytest

import rag_pipeline

LAW_HIT = {"rank": 1, "score": 1.0, "doc_id": "d1", "law_name": "식품 등의 표시·광고에 관한 법률", "kind": "법률",
           "food_type": "공통", "article_no": "8", "clause_no": "1", "title": "부당한 표시 또는 광고행위의 금지",
           "content": "본문", "effective_date": "20250101", "collected_at": "2026-10-16"}
MAT_HIT = {"rank": 1, "score": 1.0, "recog_no": "2024-20", "material": "홍삼",
           "claims": ["혈당 조절에 도움을 줄 수 있음"], "daily_intake": "", "caution": "", "collected_at": "2026-10-15"}
LLM_OUT = "[판단] 큼\n[판단이유] 이유\n[해야할일]\n1. 뺍니다\n[근거]\n1 | 금지 조항\n2 | 인정 범위\n[식품종류] 일치"


@pytest.fixture
def calls(monkeypatch):
    log = {"materials": 0, "llm": [], "law": []}

    def fakeLaw(osClient, cfg, query, foodType, topK=5, mode="hybrid", queryVector=None):
        log["law"].append((foodType, queryVector))
        return [dict(LAW_HIT)]

    def fakeMat(osClient, cfg, query, topK=3, queryVector=None):
        log["materials"] += 1
        return [dict(MAT_HIT)]

    def fakeLlm(cfg, prompt, stop=None):
        log["llm"].append(prompt)
        log.setdefault("stops", []).append(stop)
        return log["outs"].pop(0) if log.get("outs") else LLM_OUT

    monkeypatch.setattr(rag_pipeline, "searchLaw", fakeLaw)
    monkeypatch.setattr(rag_pipeline, "searchMaterials", fakeMat)
    monkeypatch.setattr(rag_pipeline, "generateAnswer", fakeLlm)
    monkeypatch.setattr(rag_pipeline, "embedQuery", lambda cfg, q: [0.1])
    return log


def test_general_skips_material_search(calls):
    resp = rag_pipeline.runFoodRag(None, {}, "혈당 관리 샐러드", "general", usage="menu", queryVector=[0.2])
    # 법령 검색은 광고 맥락을 붙인 문장으로 searchLaw가 직접 임베딩하므로 원문 벡터를 넘기지 않는다
    assert calls["materials"] == 0 and calls["law"] == [("general", None)]
    assert "식품 종류: 일반식품" in calls["llm"][0] and "메뉴판" in calls["llm"][0]
    assert resp["verdict"] == "high" and [b["type"] for b in resp["basis"]] == ["law"]


def test_health_includes_materials_in_basis(calls):
    resp = rag_pipeline.runFoodRag(None, {}, "혈당 관리에 최고", "health")
    assert calls["materials"] == 1
    assert [b["type"] for b in resp["basis"]] == ["law", "material"]
    assert resp["basis"][1]["recog_no"] == "2024-20"


def test_no_hits_skips_llm_and_returns_no_basis(monkeypatch, calls):
    monkeypatch.setattr(rag_pipeline, "searchLaw", lambda *a, **k: [])
    monkeypatch.setattr(rag_pipeline, "latestIndexCollectedAt", lambda osClient: "2026-10-16")
    resp = rag_pipeline.runFoodRag(None, {}, "아무 말", "general")
    assert calls["llm"] == []
    assert resp["verdict"] == "out_of_scope" and resp["out_of_scope_reason"] == "no_basis"
    assert resp["collected_at"] == "2026-10-16"


def test_generateAnswer_turns_off_thinking_and_keeps_model_loaded(monkeypatch):
    # gemma4:e4b가 숨은 "생각"으로 1,300토큰 가까이 만들어 답변이 45초 넘게 걸렸다 (끄면 8~14초, 2026-10-15 측정)
    sent = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": "[판단] 큼"}

    def fakePost(url, json=None, timeout=None):
        sent.update(json)
        return FakeResp()

    monkeypatch.setattr(rag_pipeline.requests, "post", fakePost)
    out = rag_pipeline.generateAnswer({"ollamaHost": "http://x", "llmModel": "gemma4:e4b"}, "프롬프트")
    assert out == "[판단] 큼"
    assert sent["think"] is False
    assert sent["keep_alive"] == "30m"
    assert sent["options"]["temperature"] == 0.1
    # 같은 문구는 언제 점검해도 같은 판단이 나오게 seed를 고정한다 (추천 문구의 '다시 점검' 표시가 사실이 되도록)
    assert sent["options"]["seed"] == 42 and "stop" not in sent["options"]


def test_generateAnswer_can_stop_early(monkeypatch):
    sent = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": "[판단] 낮음\n"}

    def fakePost(url, json=None, timeout=None):
        sent.update(json)
        return FakeResp()

    monkeypatch.setattr(rag_pipeline.requests, "post", fakePost)
    rag_pipeline.generateAnswer({"ollamaHost": "http://x", "llmModel": "m"}, "p", stop=["[판단이유]"])
    assert sent["options"]["stop"] == ["[판단이유]"]


def test_quick_check_uses_same_prompt_and_stops_after_verdict(calls):
    calls["outs"] = ["[판단] 낮음\n"]
    got = rag_pipeline.quickCheck(None, {}, "따뜻한 홍삼차 한 잔", "general", usage="sns")
    assert got == {"verdict": "low", "verdict_reason": ""}
    assert calls["stops"] == [["[판단이유]"]]
    # 일반 점검과 같은 프롬프트여야 seed 고정으로 같은 판단이 나온다
    rag_pipeline.runFoodRag(None, {}, "따뜻한 홍삼차 한 잔", "general", usage="sns")
    assert calls["llm"][0] == calls["llm"][1]


def test_quick_check_gets_reason_only_when_not_low(calls):
    calls["outs"] = ["[판단] 어려움\n", "[판단] 어려움\n[판단이유] 근거 자료가 필요해요.\n"]
    got = rag_pipeline.quickCheck(None, {}, "최고의 홍삼차", "general")
    assert got == {"verdict": "unsure", "verdict_reason": "근거 자료가 필요해요."}
    assert calls["stops"] == [["[판단이유]"], ["[해야할일]"]]


def test_quick_check_without_hits_is_out_of_scope(monkeypatch, calls):
    monkeypatch.setattr(rag_pipeline, "searchLaw", lambda *a, **k: [])
    assert rag_pipeline.quickCheck(None, {}, "아무 말", "general")["verdict"] == "out_of_scope"
    assert calls["llm"] == []
