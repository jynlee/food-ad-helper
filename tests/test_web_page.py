import re
from pathlib import Path

PAGE = (Path(__file__).resolve().parents[1] / "web" / "index.html").read_text(encoding="utf-8")


def test_page_has_toggle_usage_and_composer():
    for elementId in ("kind-general", "kind-health", "log", "q", "send", "clear"):
        assert f'id="{elementId}"' in PAGE
    assert 'role="radiogroup"' in PAGE
    for use in ("menu", "page", "sns"):
        assert f'data-use="{use}"' in PAGE


def test_page_calls_api_and_has_four_verdict_labels():
    assert "fetch('/rag/query'" in PAGE
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
