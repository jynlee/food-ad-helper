# -*- coding: utf-8 -*-
"""
law_map.py
수집 대상 표 (개요서 03장 체크리스트 1~10번).
법제처 ID는 이름으로 목록 조회해 자동으로 찾고 data/law/resolved_ids.json 에 저장한다.

키:
- name      : 법제처 현행 명칭 (목록 조회에 사용)
- kind      : 법률 / 시행령 / 시행규칙 / 고시
- food_type : 공통 / 일반식품 / 건강기능식품 (검색 필터)
- articles  : (선택) 넣을 조문 번호 목록. 없으면 전체
- annexes   : (선택) 넣을 별표 번호 목록. 없으면 전체, 빈 리스트면 별표 없음
"""

LAW_TARGETS = [
    {"name": "식품 등의 표시·광고에 관한 법률",          "kind": "법률",     "food_type": "공통"},
    {"name": "식품 등의 표시·광고에 관한 법률 시행령",   "kind": "시행령",   "food_type": "공통"},
    {"name": "식품 등의 표시·광고에 관한 법률 시행규칙", "kind": "시행규칙", "food_type": "공통"},
    {"name": "건강기능식품에 관한 법률",                 "kind": "법률",     "food_type": "건강기능식품"},
    {"name": "건강기능식품에 관한 법률 시행령",          "kind": "시행령",   "food_type": "건강기능식품"},
    {"name": "건강기능식품에 관한 법률 시행규칙",        "kind": "시행규칙", "food_type": "건강기능식품"},
    {"name": "식품위생법",          "kind": "법률",     "food_type": "일반식품", "articles": ["44"], "annexes": []},
    {"name": "식품위생법 시행규칙", "kind": "시행규칙", "food_type": "일반식품", "articles": ["57"], "annexes": ["17"]},
]

ADMRUL_TARGETS = [
    {"name": "부당한 표시 또는 광고의 내용 기준", "kind": "고시", "food_type": "공통"},
    {"name": "건강기능식품의 기준 및 규격",       "kind": "고시", "food_type": "건강기능식품"},
]
