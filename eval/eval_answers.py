# -*- coding: utf-8 -*-
"""
eval_answers.py
실행 중인 서버의 /rag/query 를 문구 세트 전체로 호출해 답변 지표를 계산한다.
결과: eval/report_answers.md (지표 표 + 문구별 결과)

사용법 (rag_server.py 실행 중):
  python eval/eval_answers.py
  python eval/eval_answers.py --base-url http://localhost:5000
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from metrics import formatTable, scoreAnswer, summarize

ORDER = ["basis_shown", "refusal_ok", "citation_match", "no_decisive", "verdict_match", "material_match"]


def loadQuestions():
    with open(HERE / "questions.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    parser = argparse.ArgumentParser(description="답변 지표 평가")
    parser.add_argument("--base-url", default="http://localhost:5000")
    baseUrl = parser.parse_args().base_url

    rows, details = [], []
    for q in loadQuestions():
        start = time.time()
        body  = {"query": q["query"], "food_type": q["food_type"], "usage": q["usage"]}
        try:
            resp = requests.post(f"{baseUrl}/rag/query", json=body, timeout=300)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[{q['id']}] 호출 실패: {e}")
            details.append(f"| {q['id']} | {q['category']} | {q['expected_verdict']} | 호출 실패 | - | - |")
            continue
        score = scoreAnswer(q, data)
        rows.append(score)
        basis = ", ".join(b.get("article") or b.get("recog_no", "") for b in data["basis"])
        details.append(f"| {q['id']} | {q['category']} | {q['expected_verdict']} | {data['verdict']} | "
                       f"{basis or '-'} | {time.time() - start:.1f}s |")
        print(f"[{q['id']}] {data['verdict']:<12} 기대 {q['expected_verdict']:<12} {score}")

    lines = ["# 답변 평가", "", f"실행: {datetime.now():%Y-%m-%d %H:%M} · 서버 {baseUrl}", "",
             formatTable(summarize(rows), ORDER), "",
             "| 문구 | 구분 | 기대 판단 | 실제 판단 | 근거 | 시간 |", "|---|---|---|---|---|---|", *details]
    (HERE / "report_answers.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n저장: {HERE / 'report_answers.md'}")


if __name__ == "__main__":
    main()
