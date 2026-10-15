import pytest

from embed_index import EMBED_FIELD, embedFieldFor


def test_embed_field_per_index():
    assert embedFieldFor("food-law-articles") == "content"
    assert embedFieldFor("food-materials") == "text"
    assert set(EMBED_FIELD) == {"food-law-articles", "food-materials"}


def test_embed_field_rejects_unknown_index():
    with pytest.raises(ValueError):
        embedFieldFor("law-articles")
