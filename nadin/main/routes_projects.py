from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from nadin.extensions import db
from nadin.main.forms import AddProjectForm, EditProjectForm
from nadin.main.routes import bp
from nadin.main.utils import role_forbidden
from nadin.models import Project, UserRoles


@bp.route("/projects/", methods=["GET"])
@bp.route("/projects/show", methods=["GET"])
@login_required
@role_forbidden([UserRoles.default, UserRoles.vendor])
def ShowProjects():
    projects = Project.query.filter_by(hub_id=current_user.hub_id)
    if current_user.role != UserRoles.admin:
        projects = projects.filter_by(enabled=True)
    projects = db.paginate(projects.order_by(Project.name))

    forms = {"add_project": AddProjectForm(), "edit_project": EditProjectForm()}

    return render_template("projects.html", projects=projects, forms=forms)


@bp.route("/project/add", methods=["POST"])
@login_required
@role_forbidden([UserRoles.default, UserRoles.vendor])
def AddProject():
    form = AddProjectForm()
    if form.validate_on_submit():
        project_name = form.project_name.data.strip()
        uid = form.uid.data.strip() if form.uid.data is not None else None
        project = Project.query.filter_by(hub_id=current_user.hub_id, name=project_name).first()
        if project is None:
            project = Project(
                name=project_name,
                uid=uid,
                hub_id=current_user.hub_id,
                tin=form.tin.data,
                phone=form.phone.data,
                email=form.email.data,
                contact=form.contact.data,
                legal_address=form.legal_address.data,
                shipping_address=form.shipping_address.data,
                note=form.note.data,
            )
            db.session.add(project)
            db.session.commit()
            flash(f"Клиент {project_name} добавлен.")
        else:
            flash(f"Клиент {project_name} уже существует.")
    else:
        for _, error in form.errors.items():
            flash(error)
    return redirect(url_for("main.ShowProjects"))


@bp.route("/project/remove/<int:project_id>")
@login_required
@role_forbidden([UserRoles.default, UserRoles.vendor])
def RemoveProject(project_id):
    project = Project.query.filter_by(id=project_id).first()
    if project is not None:
        db.session.delete(project)
        db.session.commit()
        flash(f"Клиент {project.name} удален.")
    else:
        flash("Такого клиента не существует.")
    return redirect(url_for("main.ShowProjects"))


@bp.route("/project/edit/", methods=["POST"])
@login_required
@role_forbidden([UserRoles.default, UserRoles.vendor])
def EditProject():
    form = EditProjectForm()
    if form.validate_on_submit():
        project = Project.query.filter_by(id=form.project_id.data).first()
        if project is not None:
            project_name = form.project_name.data.strip()
            existed = Project.query.filter_by(hub_id=current_user.hub_id, name=project_name).first()
            if existed is None or existed.id == project.id:
                project.name = project_name
                project.uid = form.uid.data.strip() if form.uid.data is not None else None
                project.enabled = form.enabled.data
                project.tin = form.tin.data
                project.phone = form.phone.data
                project.email = form.email.data
                project.contact = form.contact.data
                project.legal_address = form.legal_address.data
                project.shipping_address = form.shipping_address.data
                project.note = form.note.data
                db.session.commit()
                flash(f"Клиент {project_name} изменён.")
            else:
                flash(f"Клиент {project_name} уже существует.")
        else:
            flash("Такого клиента не существует.")
    else:
        for _, error in form.errors.items():
            flash(error)
    return redirect(url_for("main.ShowProjects"))
