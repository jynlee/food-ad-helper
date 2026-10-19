import pytest
from fastapi.testclient import TestClient

import rag_server
from answer_format import DISCLAIMER

SAMPLE = {"success": True, "verdict": "high", "verdict_reason": "이유", "actions": ["빼기"],
          "basis": [{"type": "law", "law_name": "식품 등의 표시·광고에 관한 법률", "article": "제8조 1항",
                     "summary": "요약", "effective_date": "20250101",
                     "title": "부당한 표시 또는 광고행위의 금지", "content": "① 누구든지 …"}],
          "out_of_scope_reason": None, "food_type_mismatch": False, "collected_at": "2026-10-16",
          "disclaimer": DISCLAIMER, "raw_fallback": ""}


@pytest.fixture
def env(monkeypatch):
    calls = {"stored": 0, "rag": [], "cached": None, "result": dict(SAMPLE), "error": None}

    def fakeLookup(osClient, redisClient, cfg, docType, query, scope=None):
        calls["scope"] = scope
        return calls["cached"], [0.0]

    def fakeStore(*args, **kwargs):
        calls["stored"] += 1

    def fakeRag(osClient, cfg, query, foodType, usage=None, queryVector=None):
        if calls["error"]:
            raise calls["error"]
        calls["rag"].append((query, foodType, usage))
        return calls["result"]

    monkeypatch.setattr(rag_server, "lookupCache", fakeLookup)
    monkeypatch.setattr(rag_server, "storeCache", fakeStore)
    monkeypatch.setattr(rag_server, "runFoodRag", fakeRag)
    return TestClient(rag_server.app), calls


def post(client, **body):
    return client.post("/rag/query", json=body)


def test_query_runs_rag_and_stores_cache(env):
    client, calls = env
    r = post(client, query="  혈당 관리 샐러드  ", food_type="general", usage="menu")
    assert r.status_code == 200 and r.json()["verdict"] == "high"
    assert calls["rag"] == [("혈당 관리 샐러드", "general", "menu")]
    assert calls["scope"] == "general:menu" and calls["stored"] == 1


def test_response_keeps_article_title_and_text(env):
    client, _ = env
    b = post(client, query="문구", food_type="general").json()["basis"][0]
    assert b["title"] == "부당한 표시 또는 광고행위의 금지" and b["content"] == "① 누구든지 …"


def test_scope_without_usage(env):
    client, calls = env
    post(client, query="문구", food_type="health")
    assert calls["scope"] == "health:_"


def test_blank_and_too_long_query_are_400(env):
    client, _ = env
    assert post(client, query="   ", food_type="general").status_code == 400
    r = post(client, query="가" * 2001, food_type="general")
    assert r.status_code == 400 and "2000자" in r.json()["detail"]


def test_bad_or_missing_food_type_is_422(env):
    client, _ = env
    assert post(client, query="문구", food_type="cosmetic").status_code == 422
    assert post(client, query="문구").status_code == 422
    assert post(client, query="문구", food_type="general", usage="tv").status_code == 422


def test_cache_hit_skips_rag(env):
    client, calls = env
    calls["cached"] = dict(SAMPLE, verdict="low")
    r = post(client, query="문구", food_type="general")
    assert r.json()["verdict"] == "low" and calls["rag"] == [] and calls["stored"] == 0


def test_parse_failure_result_is_not_cached(env):
    client, calls = env
    calls["result"] = dict(SAMPLE, verdict="unsure", basis=[], raw_fallback="형식 없는 답")
    r = post(client, query="문구", food_type="general")
    assert r.status_code == 200 and r.json()["raw_fallback"] == "형식 없는 답"
    assert calls["stored"] == 0


def test_backend_failure_is_500_with_detail(env):
    client, calls = env
    calls["error"] = ConnectionError("Ollama 연결 실패")
    r = post(client, query="문구", food_type="general")
    assert r.status_code == 500 and "Ollama 연결 실패" in r.json()["detail"]


def test_root_serves_web_page(env):
    client, _ = env
    r = client.get("/")
    assert r.status_code == 200 and 'id="shop-cafe"' in r.text


def test_health(env):
    client, _ = env
    assert client.get("/rag/health").json()["status"] == "ok"


# ------------------------------------------------------------
# 추천 문구 /rag/suggest
# ------------------------------------------------------------

class FakeRedis:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def setex(self, key, ttl, value):
        self.data[key] = value


@pytest.fixture
def sug(env, monkeypatch):
    client, calls = env
    calls["suggest"] = {"success": True, "phrase": "진하게 우려낸 홍삼차", "change": "효능 표현을 뺐어요.", "tries": 1}
    calls["suggestRuns"] = []
    calls["lookups"] = 0
    redisClient = FakeRedis()

    def fakeLookup(osClient, redisClient_, cfg, docType, query, scope=None):
        calls["lookups"] += 1
        calls["scope"] = scope
        return calls["cached"], [0.0]

    def fakeSuggest(osClient, cfg, query, foodType, usage, original, checkFn):
        calls["suggestRuns"].append((query, foodType, usage, original["verdict"]))
        calls["checkedVerdict"] = checkFn("고친 문구")["verdict"]
        return calls["suggest"]

    monkeypatch.setattr(rag_server, "lookupCache", fakeLookup)
    monkeypatch.setattr(rag_server, "runSuggest", fakeSuggest)
    calls["quick"] = []

    def fakeQuick(osClient, cfg, query, foodType, usage=None):
        calls["quick"].append((query, foodType, usage))
        return {"verdict": "low", "verdict_reason": ""}

    monkeypatch.setattr(rag_server, "quickCheck", fakeQuick)
    monkeypatch.setitem(rag_server.state, "redisClient", redisClient)
    monkeypatch.setitem(rag_server.state, "cfg", {"qaCacheTtlSec": 60})
    return client, calls, redisClient


def test_suggest_returns_phrase_and_checks_candidate_without_cache_lookup(sug):
    client, calls, _ = sug
    r = client.post("/rag/suggest", json={"query": "홍삼차 피로 회복에 최고!", "food_type": "general", "usage": "sns"})
    assert r.status_code == 200
    assert r.json() == {"success": True, "phrase": "진하게 우려낸 홍삼차", "change": "효능 표현을 뺐어요.", "tries": 1}
    assert calls["suggestRuns"] == [("홍삼차 피로 회복에 최고!", "general", "sns", "high")]
    # 원래 문구만 캐시에서 찾고, 고친 문구는 비슷한 옛 답이 섞이지 않게 판단만 새로 받는다 (seed 고정이라 전체 점검과 같은 판단)
    assert calls["lookups"] == 1 and calls["quick"] == [("고친 문구", "general", "sns")]
    assert calls["rag"] == [("홍삼차 피로 회복에 최고!", "general", "sns")]


def test_suggest_success_is_cached_and_reused(sug):
    client, calls, redisClient = sug
    body = {"query": "홍삼차 피로 회복에 최고!", "food_type": "general", "usage": "sns"}
    client.post("/rag/suggest", json=body)
    assert len(redisClient.data) == 1
    r = client.post("/rag/suggest", json=body)
    assert r.json()["phrase"] == "진하게 우려낸 홍삼차" and len(calls["suggestRuns"]) == 1


def test_suggest_failure_is_not_cached(sug):
    client, calls, redisClient = sug
    calls["suggest"] = {"success": False, "phrase": "", "change": "", "tries": 2}
    r = client.post("/rag/suggest", json={"query": "문구", "food_type": "general"})
    assert r.status_code == 200 and r.json()["success"] is False and redisClient.data == {}


def test_suggest_not_offered_for_low_or_out_of_scope(sug):
    client, calls, _ = sug
    for verdict in ("low", "out_of_scope"):
        calls["cached"] = dict(SAMPLE, verdict=verdict)
        r = client.post("/rag/suggest", json={"query": "문구", "food_type": "general"})
        assert r.status_code == 400
    assert calls["suggestRuns"] == []


def test_suggest_blank_query_is_400(sug):
    client, _, _ = sug
    assert client.post("/rag/suggest", json={"query": " ", "food_type": "general"}).status_code == 400
