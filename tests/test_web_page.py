import re
from pathlib import Path

PAGE = (Path(__file__).resolve().parents[1] / "web" / "index.html").read_text(encoding="utf-8")


def test_page_has_shop_steps_usage_and_composer():
    for elementId in ("shop-cafe", "shop-restaurant", "shop-banchan", "shop-online",
                      "mark-yes", "mark-no", "mark-unsure", "log", "q", "send", "clear"):
        assert f'id="{elementId}"' in PAGE
    assert 'role="radiogroup"' in PAGE
    for use in ("menu", "page", "sns"):
        assert f'data-use="{use}"' in PAGE


def test_page_keeps_recent_three_and_saved_results():
    assert "MAX_RECENT = 3" in PAGE
    for elementId in ("saved-box", "saved-list", "saved-count"):
        assert f'id="{elementId}"' in PAGE
    assert "localStorage" in PAGE and "try {" in PAGE      # 저장 실패해도 화면은 동작


def test_page_calls_api_and_has_four_verdict_labels():
    assert "postApi('/rag/query'" in PAGE
    for label in ("위반 소지 큼", "위반 소지 낮음", "판단 어려움", "범위 밖"):
        assert label in PAGE


def test_page_never_uses_innerHTML_for_answers():
    assert "innerHTML =" not in PAGE.replace("log.innerHTML = ''", "")


def test_demo_only_parts_removed():
    assert "미리 써 둔 예시" not in PAGE
    assert "식품 표시사항에 꼭 넣어야 하는 항목" not in PAGE
    assert re.search(r"function classify\(", PAGE) is None


def test_law_list_includes_health_functional_standard():
    assert "건강기능식품의 기준 및 규격" in PAGE


def test_suggest_button_only_for_high_or_unsure_next_to_save():
    assert "postApi('/rag/suggest'" in PAGE
    assert "✏️ 추천 문구 보기" in PAGE and "SUGGEST_FOR = ['high', 'unsure']" in PAGE
    assert PAGE.index("'sug-btn'") < PAGE.index("'⭐ 이 결과 저장'")    # 저장 버튼 왼쪽 (A안)


def test_suggest_panel_has_wait_success_and_fail_states():
    for text in ("고친 문구를 만들고 다시 점검하고 있어요", "✏️ 이렇게 수정해 보세요", "다시 점검: 위반 소지 낮음",
                 "안전한 문구를 자동으로 만들지 못했어요", "추천 문구를 받지 못했어요"):
        assert text in PAGE


def test_suggest_phrase_can_be_copied_and_is_saved_with_result():
    assert "📋 문구 복사" in PAGE and "navigator.clipboard" in PAGE
    assert "a.suggestion = s" in PAGE        # 추천을 받은 뒤 ⭐ 저장하면 같이 저장된다
