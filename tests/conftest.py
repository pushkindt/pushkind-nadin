from datetime import datetime

import pytest
from pytz import timezone

from nadin import create_app
from nadin.extensions import db
from nadin.models import User


@pytest.fixture(scope="session")
def app():
    app = create_app(FORCE_ENV_FOR_DYNACONF="testing")
    with app.app_context():
        db.create_all()
        user = User(email="XXXXXXXXXXXXX")
        user.id = 1
        user.set_password("XXXXXXXXXXXXX")
        db.session.add(user)
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
    return test_client


@pytest.fixture()
def mock_datetime():
    return datetime(2023, 1, 1, 0, 0, 0, tzinfo=timezone("UTC"))
