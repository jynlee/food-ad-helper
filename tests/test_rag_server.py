import pytest
from fastapi.testclient import TestClient

import rag_server
from answer_format import DISCLAIMER

SAMPLE = {"success": True, "verdict": "high", "verdict_reason": "이유", "actions": ["빼기"],
          "basis": [{"type": "law", "law_name": "식품 등의 표시·광고에 관한 법률", "article": "제8조 1항",
                     "summary": "요약", "effective_date": "20250101"}],
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
    assert r.status_code == 200 and 'id="kind-general"' in r.text


def test_health(env):
    client, _ = env
    assert client.get("/rag/health").json()["status"] == "ok"
