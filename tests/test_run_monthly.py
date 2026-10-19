import json

from run_monthly import dataChanged, readNewRows


def row(**kw):
    return {"status": "success", "fetched": 10, "indexed": 0, "unchanged": 10, "removed": 0, **kw}


def test_data_changed_when_any_source_added_modified_or_removed():
    assert dataChanged([row(), row(indexed=2, unchanged=8)])
    assert dataChanged([row(removed=1)])


def test_unchanged_or_failed_run_keeps_cache():
    assert not dataChanged([row(), row()])
    assert not dataChanged([{"status": "failed", "error": "timeout"}])
    assert not dataChanged([])


def test_readNewRows_returns_only_rows_written_during_this_run(tmp_path):
    log = tmp_path / "collect.jsonl"
    log.write_text(json.dumps(row(indexed=5)) + "\n", encoding="utf-8")
    start = readNewRows(log, 0)[1]
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(row(removed=1)) + "\n")
    rows, _ = readNewRows(log, start)
    assert rows == [row(removed=1)]
    assert readNewRows(tmp_path / "none.jsonl", 0) == ([], 0)
