import pytest

from search_hybrid import (buildLawQuery, buildMaterialQuery, searchLaw, searchMaterials, toLawHit,
                           toMaterialHit)

VEC = [0.1, 0.2]
FILTER = {"terms": {"food_type": ["일반식품", "공통"]}}


def test_bm25_query_filters_food_type_and_common():
    body = buildLawQuery("혈당 관리", None, "general", 5, "bm25")
    assert body["size"] == 5
    assert body["query"]["bool"]["filter"] == [FILTER]
    assert body["query"]["bool"]["must"][0]["match"]["content"]["query"] == "혈당 관리"
    assert "knn_vector" not in body["_source"]


def test_knn_query_uses_vector_and_filter():
    body = buildLawQuery("혈당 관리", VEC, "health", 5, "knn")
    knn = body["query"]["knn"]["knn_vector"]
    assert knn["vector"] == VEC and knn["k"] == 5
    assert knn["filter"] == {"terms": {"food_type": ["건강기능식품", "공통"]}}


def test_hybrid_query_combines_bm25_and_knn():
    body = buildLawQuery("혈당 관리", VEC, "general", 5, "hybrid")
    bm25, knn = body["query"]["hybrid"]["queries"]
    assert bm25["bool"]["filter"] == [FILTER]
    assert knn["knn"]["knn_vector"]["k"] == 10


def test_buildLawQuery_rejects_bad_mode_and_food_type():
    with pytest.raises(ValueError):
        buildLawQuery("q", VEC, "general", 5, "fuzzy")
    with pytest.raises(ValueError):
        buildLawQuery("q", VEC, "cosmetic", 5, "hybrid")


def test_material_query_is_hybrid_on_text():
    body = buildMaterialQuery("혈당", VEC, 3)
    bm25, knn = body["query"]["hybrid"]["queries"]
    assert bm25["match"]["text"]["query"] == "혈당"
    assert knn["knn"]["knn_vector"]["k"] == 6


def test_hit_converters():
    lawHit = toLawHit({"_id": "law_1_0008001_1", "_score": 0.87654,
                       "_source": {"law_name": "법", "article_no": "8", "clause_no": "1", "content": "본문",
                                   "collected_at": "2026-10-16"}}, 1)
    assert lawHit["doc_id"] == "law_1_0008001_1" and lawHit["score"] == 0.8765 and lawHit["rank"] == 1
    assert lawHit["title"] == "" and lawHit["collected_at"] == "2026-10-16"
    mat = toMaterialHit({"_id": "2024-20", "_score": 1.0, "_source": {"material": "홍삼",
                         "claims": ["혈당 조절에 도움을 줄 수 있음"]}}, 1)
    assert mat["recog_no"] == "2024-20" and mat["claims"] == ["혈당 조절에 도움을 줄 수 있음"]


class FakeOs:
    def __init__(self):
        self.calls = []

    def search(self, index, body, params=None):
        self.calls.append({"index": index, "body": body, "params": params or {}})
        return {"hits": {"hits": [{"_id": "x", "_score": 1.0, "_source": {"law_name": "법", "material": "홍삼"}}]}}


def test_searchLaw_bm25_does_not_embed_or_use_pipeline(monkeypatch):
    import search_hybrid
    monkeypatch.setattr(search_hybrid, "embedQuery", lambda cfg, q: pytest.fail("embed called"))
    fake = FakeOs()
    hits = searchLaw(fake, {}, "혈당", "general", topK=5, mode="bm25")
    assert len(hits) == 1 and fake.calls[0]["index"] == "food-law-articles"
    assert fake.calls[0]["params"] == {}


def test_searchLaw_hybrid_uses_pipeline_and_given_vector(monkeypatch):
    import search_hybrid
    monkeypatch.setattr(search_hybrid, "embedQuery", lambda cfg, q: pytest.fail("embed called"))
    fake = FakeOs()
    searchLaw(fake, {}, "혈당", "general", queryVector=VEC)
    assert fake.calls[0]["params"] == {"search_pipeline": "food-hybrid-pipeline"}


def test_searchLaw_weights_send_inline_pipeline_instead_of_named(monkeypatch):
    fake = FakeOs()
    searchLaw(fake, {}, "혈당", "general", queryVector=VEC, weights=(0.5, 0.5))
    call = fake.calls[0]
    assert call["params"] == {}
    combo = call["body"]["search_pipeline"]["phase_results_processors"][0]["normalization-processor"]["combination"]
    assert combo["parameters"]["weights"] == [0.5, 0.5]


def test_searchMaterials_targets_material_index():
    fake = FakeOs()
    hits = searchMaterials(fake, {}, "혈당", queryVector=VEC)
    assert fake.calls[0]["index"] == "food-materials" and hits[0]["recog_no"] == "x"


# ---------- 2026-10-15 검색 확인에서 찾은 문제 ----------

def test_law_search_text_adds_ad_context():
    from search_hybrid import lawSearchText
    text = lawSearchText("먹으면 혈당이 내려갑니다")
    assert text.startswith("먹으면 혈당이 내려갑니다")
    assert "부당한 표시 또는 광고" in text


def test_searchLaw_searches_and_embeds_the_ad_context_text(monkeypatch):
    import search_hybrid
    embedded = []
    monkeypatch.setattr(search_hybrid, "embedQuery", lambda cfg, q: embedded.append(q) or [0.3])
    fake = FakeOs()
    searchLaw(fake, {}, "먹으면 혈당이 내려갑니다", "general")
    bm25 = fake.calls[0]["body"]["query"]["hybrid"]["queries"][0]
    assert "부당한 표시 또는 광고" in bm25["bool"]["must"][0]["match"]["content"]["query"]
    assert len(embedded) == 1 and "부당한 표시 또는 광고" in embedded[0]


def test_text_fields_use_cjk_analyzer_for_korean():
    # standard 분석기는 "혈당이"와 "혈당"을 다른 단어로 봐서 BM25가 0건이었다
    from index_materials import MAPPING as MATERIAL_MAPPING
    from law_store import MAPPING as LAW_MAPPING
    law = LAW_MAPPING["mappings"]["properties"]
    assert law["content"]["analyzer"] == "cjk" and law["title"]["analyzer"] == "cjk"
    assert MATERIAL_MAPPING["mappings"]["properties"]["text"]["analyzer"] == "cjk"


def test_embed_query_keeps_model_loaded(monkeypatch):
    # bge-m3는 기본 5분 쉬면 내려가서, 쉬고 난 뒤 첫 질문이 10초 넘게 걸렸다
    import search_hybrid
    sent = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"embeddings": [[0.1, 0.2]]}

    def fakePost(url, json=None, timeout=None):
        sent.update(json)
        return FakeResp()

    monkeypatch.setattr(search_hybrid.requests, "post", fakePost)
    out = search_hybrid.embedQuery({"ollamaHost": "http://x", "embedModel": "bge-m3"}, "문구")
    assert out == [0.1, 0.2]
    assert sent["keep_alive"] == "30m"
