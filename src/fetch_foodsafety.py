"""
식품안전나라 OpenAPI 수집 스크립트
- 인증키는 코드에 적지 말고 환경변수 FOODSAFETY_KEY 로 넣는다 (GitHub에 키가 올라가지 않게)
- 서비스별로 1000건씩 끝까지 받아서 data/foodsafety/<서비스ID>.jsonl 로 저장
- 저장된 파일로 청킹·인덱싱하고, API는 다시 부르지 않는다 (호출 제한 대비)

사용법
    # Windows PowerShell
    $env:FOODSAFETY_KEY="발급받은키"
    # WSL / Linux
    export FOODSAFETY_KEY=발급받은키

    python fetch_foodsafety.py --test        # 서비스별로 3건만 받아서 키·필드 확인
    python fetch_foodsafety.py               # 전체 수집
    python fetch_foodsafety.py I0490         # 특정 서비스만 수집
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

BASE = "http://openapi.foodsafetykorea.go.kr/api"
SERVICES = {
    "I-0040": "건강기능식품 기능성 원료 인정현황",
    "I-0050": "건강기능식품 개별인정형 정보",
    "I0030":  "건강기능식품 품목제조 신고사항",
    "I0490":  "회수·판매중지 정보",
}
PAGE = 1000          # 한 번에 받을 건수 (최대치는 서비스 안내 페이지에서 확인)
SLEEP = 0.5          # 호출 사이 대기(초)
OUT_DIR = Path("data/foodsafety")


def call(key: str, sid: str, start: int, end: int) -> dict:
    url = f"{BASE}/{key}/{sid}/json/{start}/{end}"
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            if attempt == 2:
                raise RuntimeError(f"{sid} {start}-{end} 호출 실패: {e}") from e
            time.sleep(2 * (attempt + 1))
    return {}


def parse(sid: str, data: dict) -> tuple[int, list[dict], str, str]:
    """응답에서 (전체건수, 행 목록, 결과코드, 메시지) 추출"""
    body = data.get(sid) or next(iter(data.values()), {})
    result = body.get("RESULT", {}) if isinstance(body, dict) else {}
    code, msg = result.get("CODE", ""), result.get("MSG", "")
    total = int(body.get("total_count", 0) or 0) if isinstance(body, dict) else 0
    rows = body.get("row", []) if isinstance(body, dict) else []
    return total, rows, code, msg


def check(sid: str, code: str, msg: str) -> None:
    # INFO-000 정상, INFO-200 데이터 없음. 그 외(인증키 오류 등)는 중단
    if code and code not in ("INFO-000", "INFO-200"):
        raise SystemExit(f"[{sid}] 오류 {code}: {msg}\n"
                         "→ 인증키 오타, 아직 활성화 전, 서비스 ID 표기(I-0040 / I0490) 를 확인하세요.")


def test(key: str) -> None:
    for sid, name in SERVICES.items():
        total, rows, code, msg = parse(sid, call(key, sid, 1, 3))
        check(sid, code, msg)
        print(f"\n[{sid}] {name}  전체 {total:,}건  ({code} {msg})")
        if rows:
            print("  필드:", ", ".join(rows[0].keys()))
            first = {k: (str(v)[:60] + "…" if len(str(v)) > 60 else v) for k, v in rows[0].items()}
            print("  예시:", json.dumps(first, ensure_ascii=False))
        time.sleep(SLEEP)


def fetch(key: str, sid: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{sid}.jsonl"
    total, rows, code, msg = parse(sid, call(key, sid, 1, PAGE))
    check(sid, code, msg)
    n = 0
    with open(out, "w", encoding="utf-8") as f:
        start = 1
        while True:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += len(rows)
            print(f"  [{sid}] {n:,} / {total:,}", end="\r")
            start += PAGE
            if not rows or start > total:
                break
            time.sleep(SLEEP)
            _, rows, code, msg = parse(sid, call(key, sid, start, start + PAGE - 1))
            check(sid, code, msg)
    print(f"  [{sid}] {SERVICES[sid]}: {n:,}건 저장 → {out}")


def main() -> None:
    key = os.environ.get("FOODSAFETY_KEY", "").strip()
    if not key:
        raise SystemExit("환경변수 FOODSAFETY_KEY 에 인증키를 넣어주세요.")
    args = sys.argv[1:]
    if "--test" in args:
        test(key)
        return
    targets = [a for a in args if a in SERVICES] or list(SERVICES)
    for sid in targets:
        fetch(key, sid)


if __name__ == "__main__":
    main()