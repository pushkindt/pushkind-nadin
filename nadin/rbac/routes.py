from flask import Blueprint, flash, redirect, render_template, request, url_for

from nadin.extensions import db
from nadin.models.hub import Action, ActionRole, Role
from nadin.rbac.auth import rbac_required

bp = Blueprint("rbac", __name__)


@bp.route("/", methods=["GET"])
@rbac_required("rbac_show")
def show_rbac():
    roles = Role.query.all()
    actions = Action.query.all()
    return render_template("rbac/rbac.html", roles=roles, actions=actions)


@bp.route("/role/add", methods=["POST"])
@rbac_required("rbac_manage")
def add_role():
    name = request.form.get("name")
    if name:
        role = Role(name=name)
        db.session.add(role)
        db.session.commit()
        flash("Роль успешно добавлена.", "success")
    return redirect(url_for("rbac.show_rbac"))


@bp.route("/action/add", methods=["POST"])
@rbac_required("rbac_manage")
def add_action():
    name = request.form.get("name")
    if name:
        action = Action(name=name)
        db.session.add(action)
        db.session.commit()
        flash("Действие успешно добавлено.", "success")
    return redirect(url_for("rbac.show_rbac"))


@bp.route("/assign/action", methods=["POST"])
@rbac_required("rbac_manage")
def assign_action_to_role():
    role_id = request.form.get("role_id")
    action_id = request.form.get("action_id")

    if role_id and action_id:
        existing = ActionRole.query.filter_by(role_id=role_id, action_id=action_id).first()
        if not existing:
            db.session.add(ActionRole(role_id=role_id, action_id=action_id))
            db.session.commit()
            flash("Действие назначено для роли.", "success")

    return redirect(url_for("rbac.show_rbac"))


@bp.route("/role/delete/<int:role_id>", methods=["POST"])
@rbac_required("rbac_manage")
def delete_role(role_id):
    role = Role.query.get(role_id)
    if role and role.name != "Administrator":
        db.session.delete(role)
        db.session.commit()
        flash("Роль удалена.", "success")
    else:
        flash("Нельзя удалить эту роль.", "danger")
    return redirect(url_for("rbac.show_rbac"))


@bp.route("/action/delete/<int:action_id>", methods=["POST"])
@rbac_required("rbac_manage")
def delete_action(action_id):
    action = Action.query.get(action_id)
    if action and action.name not in ("rbac_show", "rbac_manage"):
        db.session.delete(action)
        db.session.commit()
        flash("Действие удалено.", "success")
    else:
        flash("Нельзя удалить это действие.", "danger")
    return redirect(url_for("rbac.show_rbac"))


@bp.route("/unassign/action", methods=["POST"])
@rbac_required("rbac_manage")
def unassign_action():
    role_id = request.form.get("role_id")
    action_id = request.form.get("action_id")

    mapping = ActionRole.query.filter_by(role_id=role_id, action_id=action_id).first()
    role = Role.query.get(role_id)
    action = Action.query.get(action_id)
    if mapping and (role.name != "Administrator" or action.name not in ("rbac_show", "rbac_manage")):
        db.session.delete(mapping)
        db.session.commit()
        flash("Действие запрещено для роли.", "success")
    else:
        flash("Нельзя запретить это действие для этой роли.", "danger")
    return redirect(url_for("rbac.show_rbac"))
