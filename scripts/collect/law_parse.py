# -*- coding: utf-8 -*-
"""
law_parse.py
법제처 법령·행정규칙(고시) JSON을 OpenSearch food-law-articles 문서로 바꾸는 순수 함수 모음.
collect_law.py / collect_admrul.py 가 함께 사용한다. (네트워크·OpenSearch 접근 없음)

- parseClauses        : 법령 조문 → 항 단위 문서 (호·목 내용 이어붙임, 에스테틱 collect_law.py 방식)
- parseAnnexes        : 별표 → 1,200자 안팎으로 나눈 문서 (서식은 제외)
- parseAdmrulArticles : 고시 조문내용(줄 목록) → 조 단위 문서
- pickTarget          : 목록 조회 결과에서 수집 대상 하나 고르기
- planChanges         : 기존 문서와 비교해 추가·변경·유지·삭제 계획 세우기
"""

# ============================================================
# 라이브러리 임포트
# ============================================================

import hashlib
import html
import re


# ============================================================
# 상수 정의
# ============================================================

INDEX_NAME   = "food-law-articles"
ANNEX_CHUNK  = 1200    # 별표 문서 하나의 최대 글자 수 (줄 단위로 자름)

_ARTICLE_HEAD_RE = re.compile(r"^\s*제(\d+)조(?:의(\d+))?\s*(?:\(([^)]*)\))?")
_CHAPTER_RE      = re.compile(r"^\s*제\d+(?:편|장|절|관)\s")
_NAME_STRIP_RE   = re.compile(r"[\s·ㆍ∙]")
# 별표 원문은 고정 폭으로 줄을 바꿔 단어가 중간에서 끊긴다. 항목 기호로 시작하는 줄만 새 줄로 본다.
_ITEM_START_RE   = re.compile(r"^(?:■|※|□|○|◦|-\s|\d+\.|\d+\)|\(\d+\)|[가나다라마바사아자차카타파하][.)]|[①-⑳]|비고|\[별표|제\d+조)")
_BOX_BORDER_RE   = re.compile(r"[┌┐└┘├┤┬┴┼─━┏┓┗┛┣┫┳┻╋┯┷┠┨┿]+")
_SPACE_AFTER_RE  = re.compile(r"[.,;:)\]>」』”\"'?!]$")
# 고시 조문은 "…광고가. 한약의…", "…광고2. 건강…"처럼 항목이 줄바꿈 없이 붙어 온다.
# "다."는 문장 끝("한다. ")과 헷갈리므로 동사 어미 뒤에서는 나누지 않는다.
_GLUED_ITEM_RE   = re.compile(r"(?<=[^\s\d])(?=\d{1,2}\.\s)"
                              r"|(?<=[^\s\d])(?=[가나라마바사아자차카타파하]\.\s)"
                              r"|(?<=[^\s\d한있같된없않였니])(?=다\.\s)"
                              r"|(?<=\S)(?=\(예시\))")
_DELETED_RE      = re.compile(r"(?:제\d+조(?:의\d+)?(?:\([^)]*\))?\s*)?[①-⑳]?\s*삭제\s*(?:[<〈＜][^>〉＞]*[>〉＞])?")


# ============================================================
# 기본 유틸
# ============================================================

def asList(v):
    """API가 항목이 하나면 dict, 여러 개면 list로 주는 경우를 list로 통일."""
    if v is None or v == "":
        return []
    if isinstance(v, list):
        return v
    return [v]


def flattenText(v):
    """문자열·리스트·dict가 섞인 값을 빈 줄 없는 줄 목록으로 펼친다."""
    if v is None:
        return []
    if isinstance(v, str):
        v = html.unescape(v)     # 원문에 &lt;개정 ...&gt; 같은 HTML 기호가 섞여 있음
        return [line.rstrip() for line in v.split("\n") if line.strip()]
    if isinstance(v, list):
        out = []
        for x in v:
            out += flattenText(x)
        return out
    if isinstance(v, dict):
        out = []
        for x in v.values():
            out += flattenText(x)
        return out
    return [str(v)]


def chunkText(lines, maxLen=ANNEX_CHUNK):
    """줄을 자르지 않고 maxLen 안팎으로 묶는다. 한 줄이 maxLen보다 길면 그 줄만 한 덩어리."""
    chunks = []
    cur    = ""
    pieces = []
    for line in lines:                       # 안전장치: maxLen보다 긴 한 줄은 글자 수로 강제로 자른다
        pieces += [line[i:i + maxLen] for i in range(0, len(line), maxLen)] or [line]
    for line in pieces:
        if cur and len(cur) + 1 + len(line) > maxLen:
            chunks.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        chunks.append(cur)
    return chunks


def cleanText(v):
    """제목 등 한 줄 값: HTML 기호를 원래 글자로 바꾸고 앞뒤 공백 제거."""
    return html.unescape(str(v or "")).strip()


def isDeleted(text):
    """'삭제 <2016.2.4.>', '제10조 삭제', '② 삭제' 처럼 내용 없이 삭제 표시만 있는지."""
    return bool(_DELETED_RE.fullmatch(cleanText(text)))


def joinWrappedLines(lines):
    """
    고정 폭으로 끊긴 줄을 다시 잇는다. 항목 기호로 시작하지 않는 줄은 앞 줄에 붙이고,
    앞 줄이 문장부호로 끝나면 한 칸 띄운다 (예: "…각 목의 표" + "시 또는 광고" → "표시 또는 광고").
    """
    out = []
    for line in (l.strip() for l in lines):
        if line[:1] in ("│", "┃"):                     # 상자 문자 표의 행 → "칸 | 칸 | 칸" 한 줄
            out.append(" | ".join(cell.strip() for cell in line.strip("│┃").split("│")))
            continue
        line = _BOX_BORDER_RE.sub("", line).strip()     # 테두리 줄은 지우고, 줄 끝에 붙은 테두리도 뗀다
        if not line:
            continue
        if not out or _ITEM_START_RE.match(line):
            out.append(line)
            continue
        sep = " " if _SPACE_AFTER_RE.search(out[-1]) else ""
        out[-1] = out[-1] + sep + line
    return out


def hashContent(content):
    """content 문자열의 SHA-256 해시(hex). 재수집 시 변경 여부 비교용."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def parseDate(rawDate):
    """날짜를 yyyyMMdd로 정규화. 형식이 맞지 않으면 None."""
    cleaned = str(rawDate or "").strip().replace("-", "").replace(".", "")
    if len(cleaned) == 8 and cleaned.isdigit():
        return cleaned
    return None


def makeDoc(meta, docId, articleNo, clauseNo, title, content):
    """food-law-articles 문서 하나를 만든다."""
    info = meta["info"]
    return {
        "_index": INDEX_NAME,
        "_id":    docId,
        "_source": {
            "law_name":       info["name"],
            "law_id":         meta["lawId"],
            "source_key":     meta["sourceKey"],
            "kind":           info["kind"],
            "food_type":      info["food_type"],
            "article_no":     articleNo,
            "clause_no":      clauseNo,
            "title":          title,
            "content":        content,
            "content_hash":   hashContent(content),
            "effective_date": meta["effectiveDate"],
            "collected_at":   meta["collectedAt"],
        },
    }


# ============================================================
# 법령 조문
# ============================================================

def displayArticleNo(art):
    """조문번호 표시: 제3조의2 → "3의2"."""
    articleNo = str(art.get("조문번호", "")).strip()
    branchNo  = str(art.get("조문가지번호", "")).strip()
    return f"{articleNo}의{branchNo}" if branchNo else articleNo


def parseClauses(lawData, meta):
    """
    법령 JSON의 조문단위를 항 단위 문서로 만든다.
    - 조문여부가 "전문"(장·절 제목)인 항목은 건너뛴다.
    - 항이 없는 조문은 조문 전체를 문서 하나로(clause_no="0").
    - 항 아래 호·목 내용을 이어붙인다(안 하면 "다음 각 호" 도입부만 남아 근거로 못 씀).
    - meta.info.articles 가 있으면 그 조문번호만 남긴다.
    """
    articles = meta["info"].get("articles")
    docs     = []
    for art in asList(lawData.get("법령", {}).get("조문", {}).get("조문단위")):
        if str(art.get("조문여부", "")).strip() == "전문":
            continue
        displayNo = displayArticleNo(art)
        if articles is not None and displayNo not in articles:
            continue
        artKey  = str(art.get("조문키", "")).strip()
        title   = cleanText(art.get("조문제목"))
        clauses = asList(art.get("항"))

        if not clauses:
            body = "\n".join(flattenText(art.get("조문내용")))
            if not body or isDeleted(body):
                continue
            content = f"제{displayNo}조({title})\n{body}"
            docs.append(makeDoc(meta, f"{meta['sourceKey']}_{artKey}_0", displayNo, "0", title, content))
            continue

        for j, clause in enumerate(clauses, start=1):
            parts = flattenText(clause.get("항내용"))
            for item in asList(clause.get("호")):
                parts += flattenText(item.get("호내용"))
                for mok in asList(item.get("목")):
                    parts += flattenText(mok.get("목내용"))
            if not parts or isDeleted(" ".join(parts)):
                continue
            content = f"제{displayNo}조({title}) {j}항\n" + "\n".join(parts)
            docs.append(makeDoc(meta, f"{meta['sourceKey']}_{artKey}_{j}", displayNo, str(j), title, content))
    return docs


# ============================================================
# 별표
# ============================================================

def annexNo(unit):
    """별표번호 표시: "0001"/"00" → "1", "0001"/"02" → "1의2", "000102" → "1의2"."""
    raw    = re.sub(r"\D", "", str(unit.get("별표번호", "")))
    branch = re.sub(r"\D", "", str(unit.get("별표가지번호", "")))
    if len(raw) == 6:
        raw, branch = raw[:4], (branch or raw[4:])
    number    = str(int(raw)) if raw else "0"
    branchNum = int(branch) if branch else 0
    return f"{number}의{branchNum}" if branchNum else number


def parseAnnexes(annexUnits, meta):
    """
    별표단위 목록을 문서로 만든다. 별표구분이 "서식"인 것은 뺀다.
    본문은 chunkText로 나눠 _id 끝에 _p1, _p2 ... 를 붙인다.
    meta.info.annexes 가 있으면 그 별표번호만 남긴다(빈 리스트면 하나도 넣지 않음).
    """
    wanted = meta["info"].get("annexes")
    docs   = []
    for unit in asList(annexUnits):
        if str(unit.get("별표구분", "별표")).strip() == "서식":
            continue
        number = annexNo(unit)
        if wanted is not None and number not in wanted:
            continue
        title = cleanText(unit.get("별표제목"))
        lines = joinWrappedLines(flattenText(unit.get("별표내용")))
        if not lines or isDeleted(title) or all(isDeleted(line) for line in lines):
            continue
        for p, chunk in enumerate(chunkText(lines), start=1):
            content = f"[별표 {number}] {title}\n{chunk}"
            docs.append(makeDoc(meta, f"{meta['sourceKey']}_annex{number}_p{p}",
                                f"별표 {number}", "0", title, content))
    return docs


# ============================================================
# 행정규칙(고시) 조문
# ============================================================

def parseAdmrulArticles(lines, meta):
    """
    고시 조문내용(줄 목록)을 "제n조(제목)" 머리줄 기준으로 묶어 조 단위 문서를 만든다.
    장·절 제목 줄은 건너뛰고, 같은 조번호가 다시 나오면(부칙 등) 처음 것만 남긴다.
    """
    articles = meta["info"].get("articles")
    groups   = []
    for line in lines:
        if _CHAPTER_RE.match(line):
            continue
        m = _ARTICLE_HEAD_RE.match(line)
        if m:
            number = f"{m.group(1)}의{m.group(2)}" if m.group(2) else m.group(1)
            groups.append({"no": number, "title": (m.group(3) or "").strip(), "lines": [line.strip()]})
        elif groups:
            groups[-1]["lines"].append(line.strip())

    docs = []
    seen = set()
    for g in groups:
        if g["no"] in seen:
            continue
        seen.add(g["no"])
        if articles is not None and g["no"] not in articles:
            continue
        content = _GLUED_ITEM_RE.sub("\n", "\n".join(g["lines"]))
        if isDeleted(content):
            continue
        baseId = f"{meta['sourceKey']}_{g['no']}"
        if len(content) <= ANNEX_CHUNK:
            docs.append(makeDoc(meta, baseId, g["no"], "0", g["title"], content))
            continue
        # 긴 조문(예: 부당한 표시·광고 고시 제2조 5천여 자)은 줄 단위로 나누고, 조각마다 조문 머리를 붙인다
        main, _, branch = g["no"].partition("의")
        head = f"제{main}조" + (f"의{branch}" if branch else "") + f"({g['title']})"
        for p, chunk in enumerate(chunkText([l for l in content.split("\n") if l.strip()]), start=1):
            text = chunk if p == 1 else f"{head}\n{chunk}"
            docs.append(makeDoc(meta, f"{baseId}_p{p}", g["no"], "0", g["title"], text))
    return docs


# ============================================================
# 수집 대상 이름 매칭
# ============================================================

def normalizeName(s):
    """비교용 이름: 공백과 가운뎃점(·ㆍ∙) 제거."""
    return _NAME_STRIP_RE.sub("", str(s or ""))


def pickTarget(candidates, name, nameKey):
    """
    목록 조회 결과에서 이름이 같은 후보를 고른다.
    같은 이름이 없으면 이름을 포함하는 후보가 정확히 하나일 때만 고른다.
    고를 수 없으면 후보 이름을 담아 LookupError.
    """
    want  = normalizeName(name)
    cands = asList(candidates)
    exact = [c for c in cands if normalizeName(c.get(nameKey)) == want]
    if exact:
        return exact[0]
    partial = [c for c in cands if want in normalizeName(c.get(nameKey))]
    if len(partial) == 1:
        return partial[0]
    names = [c.get(nameKey) for c in cands]
    raise LookupError(f"'{name}' 수집 대상을 하나로 정할 수 없습니다. 후보: {names}")


# ============================================================
# 변경 계획
# ============================================================

def historyRow(src, changeType, oldContent, newContent):
    return {
        "source_key":  src.get("source_key"),
        "law_name":    src.get("law_name"),
        "article_no":  src.get("article_no"),
        "clause_no":   src.get("clause_no"),
        "change_type": changeType,
        "old_content": oldContent,
        "new_content": newContent,
    }


def planChanges(docs, existing):
    """
    docs     : 이번에 파싱한 문서 리스트
    existing : 같은 source_key로 이미 인덱스에 있는 문서 {_id: _source}
    반환     : toIndex(새로 넣을 문서), unchangedIds(그대로인 문서 id),
               removedIds(이번에 사라진 문서 id), history(law_history 로그 행)
    """
    toIndex   = []
    unchanged = []
    history   = []
    newIds    = set()
    for d in docs:
        newIds.add(d["_id"])
        src = d["_source"]
        old = existing.get(d["_id"])
        if old is None:
            toIndex.append(d)
            history.append(historyRow(src, "added", None, src["content"]))
        elif old.get("content_hash") != src["content_hash"]:
            toIndex.append(d)
            history.append(historyRow(src, "modified", old.get("content"), src["content"]))
        else:
            unchanged.append(d["_id"])

    removed = [docId for docId in existing if docId not in newIds]
    for docId in removed:
        old = dict(existing[docId])
        history.append(historyRow(old, "removed", old.get("content"), ""))
    return {"toIndex": toIndex, "unchangedIds": unchanged, "removedIds": removed, "history": history}
