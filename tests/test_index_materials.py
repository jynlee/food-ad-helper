from pathlib import Path

from index_materials import MATERIAL_INDEX, buildActions, loadMaterials, selectChanged, selectRemoved

ROOT = Path(__file__).resolve().parents[1]


def test_loadMaterials_reads_all_731():
    mats = loadMaterials(ROOT / "data" / "foodsafety" / "materials.jsonl")
    assert len(mats) == 731
    assert any(m["_id"] == "2024-20" and m["material"] == "홍삼" for m in mats)


def test_buildActions_moves_id_out_of_source_and_adds_date():
    mats = [{"_id": "2024-20", "material": "홍삼", "claims": ["혈당 조절에 도움을 줄 수 있음"], "text": "t"}]
    action = buildActions(mats, "2026-10-15")[0]
    assert action["_index"] == MATERIAL_INDEX and action["_id"] == "2024-20"
    assert "_id" not in action["_source"]
    assert action["_source"]["collected_at"] == "2026-10-15"
    assert action["_source"]["claims"] == ["혈당 조절에 도움을 줄 수 있음"]


def test_selectChanged_skips_docs_with_same_text():
    actions = buildActions([{"_id": "a", "text": "같음"}, {"_id": "b", "text": "새것"}, {"_id": "c", "text": "추가"}],
                           "2026-10-15")
    changed = selectChanged(actions, {"a": "같음", "b": "옛것"})
    assert [a["_id"] for a in changed] == ["b", "c"]


def test_buildActions_skips_rows_without_recognition_number():
    # 원본 I-0040의 풋사과농축분말(APPLOZIN)은 인정번호 칸이 비어 있다 (2026-10-15 확인)
    mats = [{"_id": "", "material": "풋사과농축분말(APPLOZIN)", "text": "t"}, {"_id": "2024-20", "material": "홍삼", "text": "t"}]
    assert [a["_id"] for a in buildActions(mats, "2026-10-15")] == ["2024-20"]


def test_selectRemoved_finds_materials_dropped_from_list():
    # 인정이 취소되거나 목록에서 빠진 원료는 인덱스에서도 지워야 검색 근거로 나오지 않는다
    actions = buildActions([{"_id": "a", "text": "t"}, {"_id": "c", "text": "t"}], "2026-10-19")
    assert selectRemoved(["a", "b", "c", "d"], actions) == ["b", "d"]
