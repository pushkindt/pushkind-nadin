import pytest

from nadin.models.project import ProjectPriceLevel


def test_can_calculate_price(app, product):
    assert product.get_price(ProjectPriceLevel.online_store, 5.0) == pytest.approx(232.1429975)


def test_can_calculate_price_non_default(app, product):
    assert product.get_price(ProjectPriceLevel.small_wholesale) == pytest.approx(2.0)


def test_can_calculate_price_non_existent(app, product):
    assert product.get_price(ProjectPriceLevel.exclusive) == pytest.approx(244.36105)
