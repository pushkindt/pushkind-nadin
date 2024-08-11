from datetime import datetime, timezone

from flask import Blueprint
from flask_login import current_user

from nadin.extensions import db

bp = Blueprint("main", __name__)


@bp.before_app_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.now(timezone.utc)
        db.session.commit()
