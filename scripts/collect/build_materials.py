"""
I-0040(기능성 원료 인정현황) + I-0050(개별인정형 정보)를 같은 형식으로 합쳐서
OpenSearch에 넣을 문서 파일(data/foodsafety/materials.jsonl)을 만든다.

    python build_materials.py

- 같은 인정번호가 두 데이터에 모두 있으면 하나로 합친다 (인정 문구는 중복 제거 후 합침)
- 인정번호 표기가 서로 달라서(I-0040 "2006-11", I-0050 "제2006-11호", "New제2007-13호") 먼저 같은 형식으로 맞춘 뒤 합친다
- claims: 광고 문구와 비교할 '인정된 기능성 문구' 목록
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DIR = Path("data/foodsafety")
OUT = DIR / "materials.jsonl"
EMPTY = {"", ".", "-", "없음", "데이터없음"}
# 인정 문구가 아닌 줄(기준·규격 항목, 첨부 안내 등)
NOT_CLAIM = re.compile(r"^(성상|납|총?비소|카드뮴|총?수은|대장균군|세균수|붕해|수분)\b|별도\s*첨부|인체적용시험이\s*미흡")


def clean(v) -> str:
    v = (v or "").strip()
    return "" if v in EMPTY else v


def norm_id(v) -> str:
    """인정번호를 '2006-11' 형식으로 통일 (제2006-11호, New제2007-13호 → 2007-13)"""
    v = clean(v)
    v = re.sub(r"^New", "", v)
    v = re.sub(r"^제", "", v)
    v = re.sub(r"호$", "", v)
    return v.strip()


def clean_material(name: str) -> str:
    """원료명 끝의 인정번호 표기 제거: (기능성원료인정제2006-11호), (기능성원료인정New제2007-13호), (제2023-40호)"""
    return re.sub(r"\((?:기능성원료인정)?\s*(?:New)?\s*제?\d{4}-\d+호?\)\s*$", "", clean(name)).strip()


def same(a: str, b: str) -> bool:
    """띄어쓰기만 다른 문구는 같은 문구로 본다 (혈당 조절에 / 혈당조절에)"""
    return a.replace(" ", "") == b.replace(" ", "")


def split_claims(text: str) -> list[str]:
    """기능성 문구를 문장 단위 목록으로 나눈다."""
    text = clean(text)
    if not text:
        return []
    # I-0050: "(국문) ...\n(영문) ..." → 국문 부분만
    if "(국문)" in text:
        text = text.split("(국문)", 1)[1].split("(영문)", 1)[0]
    # 따옴표 안 문장이 있으면 그것만 (I-0040 형식)
    quoted = re.findall(r'[“"]([^”"]+)[”"]', text)
    parts = quoted or re.split(r'\n|(?:^|\s)\(\d+\)\s*|(?:^|\s)\d+\.\s+|①|②|③|④|⑤', text)
    out = []
    for p in parts:
        p = re.sub(r'\((?:기타기능|생리활성기능)[^)]*\)', '', p or '')
        p = re.sub(r'\(\s*기타\s*[ⅠⅡIⅰⅱ1-2]+\s*(?:등급)?\s*\)?\s*$', '', p)   # 끝의 (기타Ⅱ), (기타 I등급) 표기
        p = p.strip(" .-\t\r\n“”‘’\"'")
        if len(p) >= 4 and not NOT_CLAIM.search(p) and not any(same(p, o) for o in out):
            out.append(p)
    return out


def from_i0040(r: dict) -> dict:
    return {
        "id": norm_id(r.get("HF_FNCLTY_MTRAL_RCOGN_NO")),
        "material": clean_material(r.get("APLC_RAWMTRL_NM")),
        "claims": split_claims(r.get("FNCLTY_CN")),
        "daily_intake": clean(r.get("DAY_INTK_CN")),
        "caution": clean(r.get("IFTKN_ATNT_MATR_CN")),
        "approved": clean(r.get("PRMS_DT")),
        "src": "I-0040",
    }


def from_i0050(r: dict) -> dict:
    name = clean_material(r.get("RAWMTRL_NM"))   # 끝의 (제2023-40호), (기능성원료인정제2006-11호) 제거
    lo, hi = clean(r.get("DAY_INTK_LOWLIMIT")), clean(r.get("DAY_INTK_HIGHLIMIT"))
    intake = lo if lo == hi else " ~ ".join(x for x in (lo, hi) if x)
    return {
        "id": norm_id(r.get("HF_FNCLTY_MTRAL_RCOGN_NO")),
        "material": name,
        "claims": split_claims(r.get("PRIMARY_FNCLTY")),
        "daily_intake": intake,
        "caution": clean(r.get("IFTKN_ATNT_MATR_CN")),
        "approved": "",
        "src": "I-0050",
    }


def to_doc(m: dict) -> dict:
    parts = [f"[건강기능식품 인정 기능성] 원료: {m['material']}."]
    if m["claims"]:
        parts.append("인정된 기능성: " + " / ".join(m["claims"]) + ".")
    if m["daily_intake"]:
        parts.append(f"1일 섭취량: {m['daily_intake']}.")
    if m["caution"]:
        parts.append("섭취 시 주의: " + m["caution"].replace("\n", " "))
    return {
        "_id": m["id"],
        "text": " ".join(parts),               # BM25 + 임베딩 대상
        "sector": "건강기능식품",
        "source": f"식약처 건강기능식품 기능성 원료 인정(제{m['id']}호)" if m["id"] else "식약처 건강기능식품 기능성 원료 인정",
        "material": m["material"],
        "claims": m["claims"],                 # 광고 문구 대조용 원문
        "daily_intake": m["daily_intake"],
        "caution": m["caution"],
        "approved": m["approved"],
        "datasets": m["src"],
    }


def load(name: str):
    p = DIR / name
    if not p.exists():
        print(f"  (없음) {p}")
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    merged: dict[str, dict] = {}
    stats = {"I-0040": 0, "I-0050": 0, "합침": 0, "문구없음": 0}
    for src, conv in (("I-0040.jsonl", from_i0040), ("I-0050.jsonl", from_i0050)):
        for r in load(src):
            m = conv(r)
            stats[m["src"]] += 1
            key = m["id"] or f"{m['src']}-{m['material']}"
            if key in merged:
                old = merged[key]
                old["claims"] += [c for c in m["claims"] if not any(same(c, o) for o in old["claims"])]
                for k in ("material", "daily_intake", "caution", "approved"):   # 비어 있는 칸은 다른 쪽 값으로 채움
                    old[k] = old[k] or m[k]
                old["src"] += "," + m["src"]
                stats["합침"] += 1
            else:
                merged[key] = m
    saved = 0
    with open(OUT, "w", encoding="utf-8") as f:
        for m in merged.values():
            if not m["claims"]:          # 원본에 기능성 문구가 비어 있는 건은 판단 근거가 없어 제외
                stats["문구없음"] += 1
                continue
            f.write(json.dumps(to_doc(m), ensure_ascii=False) + "\n")
            saved += 1
    print(f"I-0040 {stats['I-0040']}건 + I-0050 {stats['I-0050']}건 "
          f"→ 인정번호 기준 {len(merged)}건 (겹친 {stats['합침']}건 합침)")
    print(f"기능성 문구가 비어 있는 {stats['문구없음']}건 제외 → 최종 {saved}건")
    print(f"저장: {OUT}")


if __name__ == "__main__":
    main()