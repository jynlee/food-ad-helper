# -*- coding: utf-8 -*-
"""
answer_format.py
검색 결과 → Context·프롬프트, LLM 출력 → 응답 dict 로 바꾸는 순수 함수 모음.

근거 표기 방식: LLM은 Context의 [번호]만 적고, 법령명·조문 번호·인정번호는 서버가
검색 결과(refTable)에서 채운다. LLM이 없는 번호를 적으면 버린다.
"""

# ============================================================
# 라이브러리 임포트
# ============================================================

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from food_common import FOOD_TYPE_MAP


# ============================================================
# 상수 정의
# ============================================================

DISCLAIMER = "법령 정보 안내이며 법률 자문이 아닙니다. 확신이 없으면 관할 기관이나 전문가에게 확인하세요."

USAGE_HINT = {
    "menu": "메뉴판 — 메뉴 이름과 메뉴 설명에도 같은 기준이 적용됩니다.",
    "page": "상세페이지 — 제품명, 이미지 속 글자, 후기 문구에도 같은 기준이 적용됩니다.",
    "sns":  "SNS 홍보 문구 — 게시글 본문, 해시태그, 이미지 속 글자에도 같은 기준이 적용됩니다.",
}

SYSTEM_PROMPT = """당신은 카페·음식점·반찬가게 운영자와 온라인 식품 판매자를 돕는 식품 표시·광고 점검 도우미입니다.
사용자가 쓰려는 광고 문구가 부당한 표시·광고에 해당할 소지가 있는지, 아래 [법령 조문]과 [인정 기능성 문구]만 근거로 판단합니다.

규칙:
1. Context에 있는 내용만 근거로 사용하고 추측하지 않습니다.
2. 근거는 Context의 대괄호 번호로만 적습니다. 법령명이나 조문 번호를 직접 쓰지 않습니다.
3. "위법입니다", "불법입니다", "위반입니다"처럼 단정하지 않습니다. 판단은 큼, 낮음, 어려움 중 하나입니다.
4. 질문이 식품·건강기능식품의 표시·광고 문구 점검이 아니면 [판단] 범위밖, [범위밖사유] 주제 로 답합니다.
   (예: 표시사항에 넣어야 하는 항목 안내, 영업 신고·인허가, 시설·위생 기준, 세금, 화장품·의약품 광고, 행정처분 결과 예측, 소송)
5. Context의 조문이 질문과 관련이 없으면 [판단] 범위밖, [범위밖사유] 근거없음 으로 답합니다.
6. "위법인가요?", "처벌받나요?"처럼 단정을 요구하면 위반 소지 수준과 근거만 답하고, 해야 할 일에 관할 기관이나 전문가 확인을 넣습니다.
7. 질문 내용이 선택한 식품 종류와 다르면(예: 일반식품을 골랐는데 "건강기능식품인데"라고 함) [식품종류] 불일치, 아니면 일치로 답합니다.
8. 건강기능식품은 [인정 기능성 문구]와 같은 범위의 표현만 쓸 수 있습니다. 인정 문구를 넘어서는 표현이나 질병 예방·치료 표현은 큼입니다.
   맞는 인정 문구를 찾지 못하면 어려움으로 하고, 해야 할 일에 "인정된 기능성인지 식약처 확인 필요"를 넣습니다.
9. 일반식품이 질병 예방·치료 효과나 건강기능식품으로 오인될 기능성을 표방하면 큼입니다.
10. "최고", "100%", "무첨가" 같은 단정·과장 표현은 근거 자료에 따라 달라지므로 보통 어려움이고, 해야 할 일에 근거 자료 확인을 넣습니다.

반드시 아래 형식 그대로 답합니다. 형식 밖의 말은 쓰지 않습니다.
[판단] 큼 또는 낮음 또는 어려움 또는 범위밖
[판단이유] 판단의 이유를 한두 문장으로
[해야할일]
1. 할 일
2. 할 일
[근거]
번호 | 이 근거가 문구와 어떻게 관련되는지 한 문장
[범위밖사유] 주제 또는 근거없음 (범위밖일 때만)
[식품종류] 일치 또는 불일치"""


# ============================================================
# Context / 프롬프트
# ============================================================

def formatArticle(articleNo, clauseNo):
    """화면·근거 표시용 조문 표기. 별표는 그대로, 항 번호가 0이거나 없으면 생략."""
    articleNo = str(articleNo or "")
    if articleNo.startswith("별표"):
        return articleNo
    main, _, branch = articleNo.partition("의")      # "3의2" → 제3조의2
    text = f"제{main}조" + (f"의{branch}" if branch else "")
    if clauseNo and str(clauseNo) != "0":
        text += f" {clauseNo}항"
    return text


def buildContext(lawHits, materialHits):
    """
    법령 결과에 [1]~, 인정 문구에 이어지는 번호를 붙인 Context 문자열과
    {번호: 검색 결과 + type} 표를 만든다.
    """
    lines    = []
    refTable = {}
    n        = 0
    if lawHits:
        lines.append("[법령 조문]")
        for hit in lawHits:
            n += 1
            refTable[n] = dict(hit, type="law")
            lines.append(f"[{n}] {hit['law_name']} {formatArticle(hit['article_no'], hit['clause_no'])} "
                         f"({hit.get('title', '')})\n{hit.get('content', '')}")
    if materialHits:
        lines.append("\n[인정 기능성 문구]")
        for hit in materialHits:
            n += 1
            refTable[n] = dict(hit, type="material")
            claims = " / ".join(hit.get("claims") or [])
            lines.append(f"[{n}] 원료: {hit['material']} (인정번호 {hit['recog_no']}) / 인정 문구: {claims}")
    return "\n".join(lines), refTable


def buildPrompt(foodType, usage, context, query):
    """시스템 프롬프트 + 점검 조건(식품 종류·사용처) + Context + 질문."""
    usageLine = USAGE_HINT.get(usage, "지정 안 함")
    return f"""{SYSTEM_PROMPT}

[점검 조건]
식품 종류: {FOOD_TYPE_MAP[foodType]}
사용처: {usageLine}

{context}

[질문]
{query}

[답변]"""


# ============================================================
# LLM 출력 보정
# ============================================================

_BYTE_TOKEN_RE = re.compile(r'(?:<0x[0-9A-Fa-f]{2}>)+')


def fixByteFallbackTokens(text):
    """
    Ollama/llama.cpp가 병합하지 못한 byte-fallback 토큰(예: <0xEB><0x89><0xBC>)을
    UTF-8 문자로 복원한다. (에스테틱 rag_pipeline.py 에서 가져옴)
    """
    def repl(m):
        raw = bytes(int(h, 16) for h in re.findall(r'0x([0-9A-Fa-f]{2})', m.group(0)))
        return raw.decode("utf-8", errors="replace")
    return _BYTE_TOKEN_RE.sub(repl, text)
