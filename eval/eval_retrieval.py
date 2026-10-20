# -*- coding: utf-8 -*-
"""
eval_retrieval.py
범위 안 문구(in_scope, variant)로 검색 방식·가중치별 근거 검색 성능을 비교한다.
- hit@5    : 상위 5건 안에 정답 근거가 하나라도 있는지
- MRR      : 처음 나온 정답 근거의 순위 역수 평균 (1위 1.0, 2위 0.5 …)
- recall@5 : 정답 근거 중 상위 5건에 나온 비율
gold_basis 가 빈 문구는 '정답 미정'으로 세고 계산에서 뺀다.
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
from metrics import hitAtK, recallAtK, reciprocalRank
from search_hybrid import WEIGHT_BM25, WEIGHT_KNN, embedQuery, ensurePipeline, lawSearchText, searchLaw

TOP_K   = 5
# (이름, 검색 방식, (BM25, kNN) 가중치)
CONFIGS = [
    ("BM25만",       "bm25",   None),
    ("kNN만",        "knn",    None),
    ("하이브리드 0.7:0.3", "hybrid", (0.7, 0.3)),
    ("하이브리드 0.5:0.5", "hybrid", (0.5, 0.5)),
    (f"하이브리드 {WEIGHT_BM25}:{WEIGHT_KNN} (현재)", "hybrid", (WEIGHT_BM25, WEIGHT_KNN)),
    ("하이브리드 0.1:0.9", "hybrid", (0.1, 0.9)),
]


def loadQuestions():
    with open(HERE / "questions.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    cfg      = loadConfig()
    osClient = getOsClient(cfg)
    ensurePipeline(osClient)

    targets = [q for q in loadQuestions() if q["category"] in ("in_scope", "variant")]
    graded  = [q for q in targets if q["gold_basis"]]
    sums    = {name: {"hit": 0, "mrr": 0.0, "recall": 0.0} for name, _, _ in CONFIGS}
    rows    = []
    for q in graded:
        vec   = embedQuery(cfg, lawSearchText(q["query"]))
        ranks = {}
        for name, mode, weights in CONFIGS:
            hits = searchLaw(osClient, cfg, q["query"], q["food_type"], topK=TOP_K, mode=mode,
                             queryVector=vec, weights=weights)
            rr = reciprocalRank(hits, q["gold_basis"])
            sums[name]["hit"]    += 1 if hitAtK(hits, q["gold_basis"]) else 0
            sums[name]["mrr"]    += rr
            sums[name]["recall"] += recallAtK(hits, q["gold_basis"])
            ranks[name] = str(round(1 / rr)) if rr else "-"
        rows.append((q["id"], ranks))
        print(q["id"], ranks)

    n     = len(graded) or 1
    names = [name for name, _, _ in CONFIGS]
    lines = [f"# 검색 방식·가중치별 근거 검색 성능 (상위 {TOP_K}건)", "",
             f"실행: {datetime.now():%Y-%m-%d %H:%M} · 대상 {len(graded)}개 (정답 미정 {len(targets) - len(graded)}개 제외)", "",
             f"| 방식 (BM25:kNN) | hit@{TOP_K} | MRR | recall@{TOP_K} |", "|---|---|---|---|"]
    for name in names:
        t = sums[name]
        lines.append(f"| {name} | {t['hit']}/{len(graded)} ({t['hit'] / n * 100:.1f}%) "
                     f"| {t['mrr'] / n:.3f} | {t['recall'] / n * 100:.1f}% |")
    lines += ["", "문구별 첫 정답 근거 순위 (- = 상위 5건 안에 없음)", "",
              "| 문구 | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for qid, ranks in rows:
        lines.append(f"| {qid} | " + " | ".join(ranks[nm] for nm in names) + " |")
    (HERE / "report_retrieval.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n저장: {HERE / 'report_retrieval.md'}")


if __name__ == "__main__":
    main()
