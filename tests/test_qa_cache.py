import json

import qa_cache
from qa_cache import CACHE_INDEX, REDIS_PREFIX, lookupCache, storeCache

CFG = {"qaCacheThreshold": 0.95, "qaCacheTtlSec": 60}


class FakeOs:
    def __init__(self, hits=None, exc=None):
        self.hits, self.exc, self.searched, self.indexed = hits or [], exc, [], []

    def search(self, index, body):
        if self.exc:
            raise self.exc
        self.searched.append((index, body))
        return {"hits": {"hits": self.hits}}

    def index(self, index, body):
        if self.exc:
            raise self.exc
        self.indexed.append((index, body))


class FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value


def patchEmbed(monkeypatch):
    monkeypatch.setattr(qa_cache, "embedQuery", lambda cfg, q: [0.5])


def test_lookup_miss_when_search_fails(monkeypatch):
    patchEmbed(monkeypatch)
    cached, vec = lookupCache(FakeOs(exc=RuntimeError("down")), FakeRedis(), CFG, "food", "q", scope="general:_")
    assert cached is None and vec == [0.5]


def test_lookup_filters_by_doc_type_and_scope(monkeypatch):
    patchEmbed(monkeypatch)
    fake = FakeOs()
    lookupCache(fake, FakeRedis(), CFG, "food", "q", scope="health:sns")
    index, body = fake.searched[0]
    filters = body["query"]["knn"]["knn_vector"]["filter"]["bool"]["filter"]
    assert index == CACHE_INDEX
    assert {"term": {"doc_type": "food"}} in filters and {"term": {"scope": "health:sns"}} in filters


def test_lookup_hit_reads_prefixed_redis_key(monkeypatch):
    patchEmbed(monkeypatch)
    redis = FakeRedis()
    redis.store[f"{REDIS_PREFIX}abc"] = json.dumps({"verdict": "high"})
    fake = FakeOs(hits=[{"_score": 0.99, "_source": {"answer_id": "abc"}}])
    cached, _ = lookupCache(fake, redis, CFG, "food", "q", scope="general:_")
    assert cached == {"verdict": "high"}


def test_lookup_below_threshold_is_miss(monkeypatch):
    patchEmbed(monkeypatch)
    fake = FakeOs(hits=[{"_score": 0.90, "_source": {"answer_id": "abc"}}])
    assert lookupCache(fake, FakeRedis(), CFG, "food", "q")[0] is None


def test_store_writes_redis_and_index_and_survives_failure():
    redis, fake = FakeRedis(), FakeOs()
    storeCache(fake, redis, CFG, "food", "q", {"verdict": "low"}, scope="general:menu", queryVector=[0.5])
    assert len(redis.store) == 1 and next(iter(redis.store)).startswith(REDIS_PREFIX)
    assert fake.indexed[0][1]["scope"] == "general:menu"
    storeCache(FakeOs(exc=RuntimeError("down")), FakeRedis(), CFG, "food", "q", {}, queryVector=[0.5])


class FakeScanRedis(FakeRedis):
    def scan_iter(self, pattern):
        return [k for k in list(self.store) if k.startswith(pattern.rstrip("*"))]

    def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)


class FakeDeleteOs:
    def __init__(self):
        self.deleted = []

    def delete_by_query(self, index, body, refresh):
        self.deleted.append((index, body))
        return {"deleted": 3}


def test_clear_all_removes_answer_and_suggestion_caches_only():
    # 법령·인정 기능성이 바뀌면 예전 근거로 만든 답이 7일 동안 남지 않게 바로 비운다
    r = FakeScanRedis()
    r.store = {"foodqa:a": "1", "foodqa:b": "2", "foodsug:c": "3", "other:d": "4"}
    o = FakeDeleteOs()
    counts = qa_cache.clearAll(o, r)
    assert set(r.store) == {"other:d"}
    assert o.deleted[0][0] == CACHE_INDEX
    assert counts == {"answers": 2, "suggestions": 1, "questions": 3}
