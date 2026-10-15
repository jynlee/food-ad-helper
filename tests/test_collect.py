import json
from pathlib import Path

from collect_admrul import buildAdmrulDocs
from collect_law import buildLawDocs
from law_map import ADMRUL_TARGETS, LAW_TARGETS

FIX = Path(__file__).parent / "fixtures"
KINDS = {"법률", "시행령", "시행규칙", "고시"}
FOOD_TYPES = {"공통", "일반식품", "건강기능식품"}


def test_targets_cover_checklist_1_to_10():
    assert len(LAW_TARGETS) == 8
    assert len(ADMRUL_TARGETS) == 2
    for t in LAW_TARGETS + ADMRUL_TARGETS:
        assert t["kind"] in KINDS and t["food_type"] in FOOD_TYPES and t["name"]


def test_food_sanitation_law_is_filtered():
    byName = {t["name"]: t for t in LAW_TARGETS}
    assert byName["식품위생법"]["food_type"] == "일반식품"
    assert byName["식품위생법"]["articles"]
    assert "articles" in byName["식품위생법 시행규칙"]


def test_buildLawDocs_combines_clauses_and_annexes():
    data = json.loads((FIX / "law_sample.json").read_text(encoding="utf-8"))
    info = {"name": "식품 등의 표시·광고에 관한 법률", "kind": "법률", "food_type": "공통"}
    docs = buildLawDocs(data, "100", info, "2026-10-16")
    assert len(docs) == 5
    assert docs[0]["_source"]["effective_date"] == "20250101"
    assert docs[-1]["_id"] == "law_100_annex1_p1"


def test_buildAdmrulDocs_combines_articles_and_annexes():
    data = json.loads((FIX / "admrul_sample.json").read_text(encoding="utf-8"))
    info = {"name": "부당한 표시 또는 광고의 내용 기준", "kind": "고시", "food_type": "공통"}
    docs = buildAdmrulDocs(data, "200", info, "2026-10-16")
    assert [d["_id"] for d in docs] == ["admrul_200_1", "admrul_200_2", "admrul_200_3의2", "admrul_200_annex1_p1"]
    assert docs[0]["_source"]["kind"] == "고시"
    assert docs[0]["_source"]["effective_date"] == "20240101"
