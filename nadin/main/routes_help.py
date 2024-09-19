from flask import render_template
from flask_login import current_user, login_required

from nadin.main.routes import bp
from nadin.models.hub import User, UserProject, UserRoles
from nadin.models.project import Project
from nadin.utils import role_forbidden

################################################################################
# Responibility page
################################################################################


@bp.route("/help/", methods=["GET", "POST"])
@login_required
@role_forbidden([UserRoles.default, UserRoles.vendor])
def ShowHelp():
    project_responsibility = {}
    projects = Project.query.filter_by(hub_id=current_user.hub_id).join(UserProject)
    projects = projects.join(User).filter_by(role=UserRoles.validator).order_by(Project.name).all()

    for project in projects:
        project_responsibility[project.name] = {
            "users": project.users,
        }

    return render_template("main/help/help.html", projects=project_responsibility)
