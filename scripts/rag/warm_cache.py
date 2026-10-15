# -*- coding: utf-8 -*-
"""
warm_cache.py
자주 나올 문구(개요서 05장 대표 입력 + 화면 예시 칩)를 미리 /rag/query 에 보내 캐시를 채운다.
전제: rag_server.py 가 실행 중이어야 함 (포트 5000).

사용법:
  python scripts/rag/warm_cache.py
  python scripts/rag/warm_cache.py --base-url http://localhost:5000
"""

import argparse
import time

import requests

FAQS = [
    {"query": "SNS에 “면역력 강화에 좋아요”라고 올려도 되나요?",              "food_type": "general", "usage": "sns"},
    {"query": "상세페이지에 “다이어트 효과”라고 써도 되나요?",                 "food_type": "general", "usage": "page"},
    {"query": "메뉴판에 “혈당 관리 샐러드”라고 써도 되나요?",                  "food_type": "general", "usage": "menu"},
    {"query": "“천연 무첨가”라고 써도 되나요?",                               "food_type": "general", "usage": "page"},
    {"query": "우리 카페 홍삼차, 혈당 관리에 최고!",                           "food_type": "general", "usage": "sns"},
    {"query": "식품 제조업 영업신고는 어떻게 하나요?",                         "food_type": "general", "usage": None},
    {"query": "상세페이지에 “혈당 관리에 도움”이라고 써도 되나요?",            "food_type": "health",  "usage": "page"},
    {"query": "SNS에 “체지방 감소에 도움을 줄 수 있음”이라고 써도 되나요?",    "food_type": "health",  "usage": "sns"},
    {"query": "인정된 기능성 표현만 써야 하나요?",                             "food_type": "health",  "usage": "sns"},
    {"query": "“고혈압을 치료합니다”라고 써도 되나요?",                        "food_type": "health",  "usage": "page"},
    {"query": "우리 카페 홍삼차, 혈당 관리에 최고!",                           "food_type": "health",  "usage": "sns"},
    {"query": "식품 제조업 영업신고는 어떻게 하나요?",                         "food_type": "health",  "usage": None},
]


def warmFaqs(baseUrl):
    for i, item in enumerate(FAQS, start=1):
        start = time.time()
        try:
            resp = requests.post(f"{baseUrl}/rag/query", json=item, timeout=300)
            resp.raise_for_status()
            print(f"  [{i}/{len(FAQS)}] ({time.time() - start:5.1f}s) {resp.json()['verdict']:<12} {item['query']}")
        except Exception as e:
            print(f"  [{i}/{len(FAQS)}] 실패: {item['query']} — {e}")


def main():
    parser = argparse.ArgumentParser(description="FAQ 캐시 워밍업")
    parser.add_argument("--base-url", default="http://localhost:5000")
    warmFaqs(parser.parse_args().base_url)


if __name__ == "__main__":
    main()
