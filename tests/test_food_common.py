import json

import pytest

from food_common import COMMON, FOOD_TYPE_MAP, appendLog, loadConfig


def test_appendLog_writes_one_json_line_per_call(tmp_path):
    appendLog("collect", {"source": "law_1", "status": "success"}, logDir=tmp_path)
    appendLog("collect", {"source": "law_2", "status": "failed"}, logDir=tmp_path)
    lines = (tmp_path / "collect.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["source"] for line in lines] == ["law_1", "law_2"]
    assert "logged_at" in json.loads(lines[0])


def test_appendLog_keeps_korean_readable(tmp_path):
    appendLog("law_history", {"law_name": "식품위생법"}, logDir=tmp_path)
    assert "식품위생법" in (tmp_path / "law_history.jsonl").read_text(encoding="utf-8")


def test_appendLog_rejects_unknown_kind(tmp_path):
    with pytest.raises(ValueError):
        appendLog("other", {}, logDir=tmp_path)


def test_loadConfig_reads_law_oc(monkeypatch):
    monkeypatch.setenv("LAW_OC", "my-oc")
    assert loadConfig()["lawApiKey"] == "my-oc"


def test_food_type_constants():
    assert FOOD_TYPE_MAP == {"general": "일반식품", "health": "건강기능식품"}
    assert COMMON == "공통"
