from datetime import datetime

import pytest
from pytz import timezone

from nadin import create_app
from nadin.extensions import db
from nadin.models.hub import User, UserRoles, Vendor
from nadin.models.product import Category, Product


@pytest.fixture(scope="session")
def hub():
    hub = Vendor(id=1, name="Nadin", email="nadin@example.com")
    return hub


@pytest.fixture(scope="session")
def user(hub):
    user = User(id=1, email="admin@example.com", role=UserRoles.admin)
    user.set_password("123456")
    user.hub = hub
    return user


@pytest.fixture(scope="session")
def category(hub):
    category = Category(id=1, name="Купажи/Травы", children=[])
    category.hub = hub
    return category


@pytest.fixture(scope="session")
def product(category, hub):
    product = Product(
        id=1,
        name="Ромашка упак. 100гр.",
        sku="1КМДОБ00-000001-01",
        price=244.36105,
        prices={
            "small_wholesale": 2.0,
            "distributor": 4.0,
            "large_wholesale": 3.0,
            "marketplace": 1.0,
            "chains_vat": 6.0,
            "chains_vat_promo": 7.0,
            "chains_no_vat": 8.0,
            "chains_no_vat_promo": 9.0,
            "msrp_chains": 10.0,
            "msrp_retail": 11.0,
        },
        image=None,
        measurement="ШТ.",
        description=None,
        options=None,
    )
    product.category = category
    product.vendor = hub
    return product


@pytest.fixture(scope="session")
def app(hub, user, category, product):
    app = create_app(FORCE_ENV_FOR_DYNACONF="testing")
    with app.app_context():
        db.create_all()
        db.session.add(hub)
        db.session.add(user)
        db.session.add(category)
        db.session.add(product)
        db.session.commit()
        yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    test_client = app.test_client()
    with test_client.session_transaction() as session:
        session["user_id"] = 1
        yield test_client


@pytest.fixture()
def mock_datetime():
    return datetime(2023, 1, 1, 0, 0, 0, tzinfo=timezone("UTC"))


@pytest.fixture()
def shopping_cart():
    return (
        '{"items":{"1":{"product":{"id":1,"vendor":"Nadin","name":"Ромашка '
        'упак. 100гр.","sku":"1КМДОБ00-000001-01","price":244.36105,"prices'
        '":{"exclusive":5.0,"small_wholesale":2.0,"online_store":244.36105,'
        '"distributor":4.0,"large_wholesale":3.0,"marketplace":1.0,"retail"'
        ':6.0,"retail_promo":7.0},"image":null,"measurement":"ШТ.","cat_id"'
        ':1,"category":"Купажи/Травы","description":"","options":null,"tags'
        '":["ромашка","чай"]},"quantity":10,"comment":"asdf"}}}'
    )
