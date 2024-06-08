from flask import Blueprint, g

from nadin.api.auth import basic_auth
from nadin.api.errors import error_response
from nadin.models import OrderLimit, User, UserRoles

bp = Blueprint("api", __name__)


@bp.route("/daily/limits", methods=["GET"])
@basic_auth.login_required
def daily_update_limits_current():
    user = User.query.get_or_404(g.user_id)
    if user.role != UserRoles.admin:
        return error_response(403)
    OrderLimit.update_current(hub_id=user.hub_id)
    return "", 200
