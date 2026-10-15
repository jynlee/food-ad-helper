# -*- coding: utf-8 -*-
"""
run_monthly.py
월 1회 갱신: 법령 → 고시 → 인정 기능성 → 임베딩 순서로 실행. 바뀐 조문만 다시 인덱싱·임베딩된다.
한 단계가 실패(종료 코드 0이 아님)하면 멈춘다. 결과는 logs/collect.jsonl 에 남는다.

사용법:
  python scripts/run_monthly.py
Windows 작업 스케줄러에 등록할 때는 '시작 위치'를 저장소 루트로 지정한다.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

STEPS = [
    ["scripts/collect/collect_law.py"],
    ["scripts/collect/collect_admrul.py"],
    ["scripts/collect/index_materials.py"],
    ["scripts/rag/embed_index.py", "--index", "all"],
]


def main():
    for step in STEPS:
        print(f"\n===== {' '.join(step)} =====")
        code = subprocess.run([sys.executable, *step], cwd=ROOT).returncode
        if code != 0:
            print(f"[중단] {step[0]} 종료 코드 {code}")
            sys.exit(code)
    print("\n[완료] 월 1회 갱신 끝 — logs/collect.jsonl 확인")


if __name__ == "__main__":
    main()
