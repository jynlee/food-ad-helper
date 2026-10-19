# -*- coding: utf-8 -*-
"""
run_monthly.py
월 1회 갱신: 법령 → 고시 → 인정 기능성 → 임베딩 순서로 실행. 바뀐 조문만 다시 인덱싱·임베딩된다.
한 단계가 실패(종료 코드 0이 아님)하면 멈춘다. 결과는 logs/collect.jsonl 에 남는다.
근거 데이터가 하나라도 추가·수정·삭제되면 마지막에 답변·추천 문구 캐시를 비운다
(예전 조문으로 만든 답이 캐시 유효기간 7일 동안 남지 않도록).

사용법:
  python scripts/run_monthly.py
Windows 작업 스케줄러에 등록할 때는 '시작 위치'를 저장소 루트로 지정한다.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT        = Path(__file__).resolve().parents[1]
COLLECT_LOG = ROOT / "logs" / "collect.jsonl"

STEPS = [
    ["scripts/collect/collect_law.py"],
    ["scripts/collect/collect_admrul.py"],
    ["scripts/collect/index_materials.py"],
    ["scripts/rag/embed_index.py", "--index", "all"],
]
CLEAR_CACHE = ["scripts/rag/qa_cache.py", "--clear"]


def readNewRows(path, startLine):
    """startLine 번째 줄 이후에 추가된 로그 행. 반환: (행 리스트, 지금 줄 수)."""
    path = Path(path)
    if not path.exists():
        return [], 0
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [json.loads(l) for l in lines[startLine:]], len(lines)


def dataChanged(rows):
    """이번 실행에서 근거 문서가 하나라도 추가·수정·삭제됐는지."""
    return any(r.get("status") == "success" and (r.get("indexed", 0) or r.get("removed", 0)) for r in rows)


def runStep(step):
    print(f"\n===== {' '.join(step)} =====")
    code = subprocess.run([sys.executable, *step], cwd=ROOT).returncode
    if code != 0:
        print(f"[중단] {step[0]} 종료 코드 {code}")
        sys.exit(code)


def main():
    _, start = readNewRows(COLLECT_LOG, 0)
    for step in STEPS:
        runStep(step)
    rows, _ = readNewRows(COLLECT_LOG, start)
    if dataChanged(rows):
        runStep(CLEAR_CACHE)
    else:
        print("\n[캐시 유지] 바뀐 근거 문서 없음")
    print("\n[완료] 월 1회 갱신 끝 — logs/collect.jsonl 확인")


if __name__ == "__main__":
    main()
