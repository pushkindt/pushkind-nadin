from flask import Blueprint, current_app, g, jsonify, request
from flask_login import current_user, login_required

from nadin.api.auth import basic_auth
from nadin.api.errors import error_response
from nadin.extensions import db
from nadin.models import OrderLimit, Project, User, UserRoles

bp = Blueprint("api", __name__)


@bp.route("/daily/limits", methods=["GET"])
@basic_auth.login_required
def daily_update_limits_current():
    user = User.query.get_or_404(g.user_id)
    if user.role != UserRoles.admin:
        return error_response(403)
    OrderLimit.update_current(hub_id=user.hub_id)
    return "", 200


@bp.route("/projects/search", methods=["GET"])
@login_required
def search_projects():
    search_key = request.args.get("q", type=str)

    if search_key:
        projects, total = Project.search(search_key, page=1, per_page=current_app.config["MAX_PER_PAGE"])
        projects = db.paginate(projects, page=1)
        if search_key:
            projects.total = total
            projects.page = 1
            projects.max_per_page = current_app.config["MAX_PER_PAGE"]
    else:
        projects = Project.query
        projects = projects.filter_by(hub_id=current_user.hub_id)
        if current_user.role != UserRoles.admin:
            projects = projects.filter_by(enabled=True).order_by(Project.name)
        projects = db.paginate(projects, page=1, max_per_page=current_app.config["MAX_PER_PAGE"])
    projects = [p.to_dict() for p in projects]
    return jsonify(projects)
