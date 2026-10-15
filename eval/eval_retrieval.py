# -*- coding: utf-8 -*-
"""
eval_retrieval.py
범위 안 문구(in_scope, variant)로 BM25만 / kNN만 / 하이브리드 검색의 hit@5 를 비교한다.
gold_basis 가 빈 문구는 '정답 미정'으로 세고 비율 계산에서 뺀다.
결과: eval/report_retrieval.md

사용법:
  python eval/eval_retrieval.py
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "rag"))
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "common"))
from food_common import getOsClient, loadConfig
from metrics import hitAtK
from search_hybrid import MODES, embedQuery, ensurePipeline, lawSearchText, searchLaw

TOP_K = 5


def loadQuestions():
    with open(HERE / "questions.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    cfg      = loadConfig()
    osClient = getOsClient(cfg)
    ensurePipeline(osClient)

    targets = [q for q in loadQuestions() if q["category"] in ("in_scope", "variant")]
    graded  = [q for q in targets if q["gold_basis"]]
    counts  = {mode: 0 for mode in MODES}
    rows    = []
    for q in graded:
        vec  = embedQuery(cfg, lawSearchText(q["query"]))
        mark = {}
        for mode in MODES:
            hits = searchLaw(osClient, cfg, q["query"], q["food_type"], topK=TOP_K, mode=mode, queryVector=vec)
            mark[mode] = hitAtK(hits, q["gold_basis"])
            counts[mode] += 1 if mark[mode] else 0
        rows.append((q["id"], mark))
        print(q["id"], {m: "O" if v else "X" for m, v in mark.items()})

    lines = [f"# 검색 방식별 근거 검색 적중률 (hit@{TOP_K})", "",
             f"실행: {datetime.now():%Y-%m-%d %H:%M} · 대상 {len(graded)}개 (정답 미정 {len(targets) - len(graded)}개 제외)", "",
             "| 방식 | 적중 | 비율 |", "|---|---|---|"]
    for mode in MODES:
        rate = counts[mode] / len(graded) * 100 if graded else 0
        lines.append(f"| {mode} | {counts[mode]}/{len(graded)} | {rate:.1f}% |")
    lines += ["", "| 문구 | " + " | ".join(MODES) + " |", "|---|" + "---|" * len(MODES)]
    for qid, mark in rows:
        lines.append(f"| {qid} | " + " | ".join("O" if mark[m] else "X" for m in MODES) + " |")
    (HERE / "report_retrieval.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n저장: {HERE / 'report_retrieval.md'}")


if __name__ == "__main__":
    main()
