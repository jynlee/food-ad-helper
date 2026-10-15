import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from run_monthly import STEPS  # noqa: E402
from warm_cache import FAQS  # noqa: E402


def test_faqs_are_valid_requests():
    assert len(FAQS) >= 10
    for f in FAQS:
        assert f["query"].strip()
        assert f["food_type"] in ("general", "health")
        assert f["usage"] in (None, "menu", "page", "sns")


def test_monthly_steps_order():
    names = [Path(step[0]).name for step in STEPS]
    assert names == ["collect_law.py", "collect_admrul.py", "index_materials.py", "embed_index.py"]
