import io

from flask import Response, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from openpyxl import Workbook
from sqlalchemy import and_, or_

from nadin.extensions import db
from nadin.main.forms import UserRolesForm, UserSettingsForm
from nadin.main.routes import bp
from nadin.main.utils import role_forbidden, role_required
from nadin.models import (
    Category,
    Order,
    OrderApproval,
    OrderCategory,
    OrderPosition,
    OrderStatus,
    Position,
    Project,
    User,
    UserRoles,
    Vendor,
)
from nadin.utils import flash_errors

################################################################################
# Settings page
################################################################################


def RemoveExcessivePosition():
    validators_positions = (
        Position.query.join(
            User,
            and_(Position.id == User.position_id, User.role == UserRoles.validator),
            isouter=True,
        )
        .filter(User.position_id.is_(None))
        .all()
    )
    position_ids = [p.id for p in validators_positions]
    OrderPosition.query.filter(OrderPosition.position_id.in_(position_ids)).delete()
    users_positions = (
        Position.query.join(User, Position.id == User.position_id, isouter=True)
        .filter(User.position_id.is_(None))
        .all()
    )
    position_ids = [p.id for p in users_positions]
    Position.query.filter(Position.id.in_(position_ids)).delete()
    db.session.commit()


@bp.route("/settings/", methods=["GET", "POST"])
@login_required
@role_forbidden([UserRoles.default, UserRoles.vendor])
def ShowSettings():
    projects = Project.query
    if current_user.role != UserRoles.admin:
        projects = projects.filter_by(enabled=True)
    projects = projects.filter_by(hub_id=current_user.hub_id)
    projects = projects.order_by(Project.name).all()

    categories = Category.query.filter(Category.hub_id == current_user.hub_id).all()
    if current_user.role == UserRoles.admin:
        user_form = UserRolesForm()
    else:
        user_form = UserSettingsForm()

    if current_user.role in [UserRoles.admin, UserRoles.purchaser, UserRoles.validator, UserRoles.initiative]:
        user_form.about_user.categories.choices = [(c.id, c.name) for c in categories]
    else:
        user_form.about_user.categories.choices = []
    user_form.about_user.projects.choices = [(p.id, p.name) for p in current_user.projects]

    if user_form.submit.data:
        user_form.about_user.projects.choices = [(p.id, p.name) for p in projects]
        if user_form.validate_on_submit():
            if current_user.role == UserRoles.admin:
                user = User.query.filter(User.id == user_form.user_id.data).first()
                if user is None:
                    flash("Пользователь не найден.")
                    return redirect(url_for("main.ShowSettings"))
                user.hub_id = current_user.hub_id
                user.role = user_form.role.data
                user.note = user_form.note.data
                user.birthday = user_form.birthday.data
                user.dashboard_url = user_form.dashboard_url.data
            else:
                user = current_user

            old_position = user.position
            old_role = user.role

            if user_form.about_user.position.data is not None and user_form.about_user.position.data != "":
                position_name = user_form.about_user.position.data.strip().lower()
                position = Position.query.filter_by(name=position_name, hub_id=user.hub_id).first()
                if position is None:
                    position = Position(name=position_name, hub_id=user.hub_id)
                user.position = position
            else:
                user.position = None

            if user.role in [UserRoles.purchaser, UserRoles.validator, UserRoles.initiative]:
                if user_form.about_user.categories.data is not None and len(user_form.about_user.categories.data) > 0:
                    user.categories = Category.query.filter(Category.id.in_(user_form.about_user.categories.data)).all()
                else:
                    user.categories = []
                if user_form.about_user.projects.data is not None and len(user_form.about_user.projects.data) > 0:
                    user.projects = Project.query.filter(Project.id.in_(user_form.about_user.projects.data)).all()
                else:
                    user.projects = []
            else:
                user.categories = []
                user.projects = []

            user.phone = user_form.about_user.phone.data
            user.location = user_form.about_user.location.data
            user.email_new = user_form.about_user.email_new.data
            user.email_modified = user_form.about_user.email_modified.data
            user.email_disapproved = user_form.about_user.email_disapproved.data
            user.email_approved = user_form.about_user.email_approved.data
            user.email_comment = user_form.about_user.email_comment.data
            user.name = user_form.about_user.full_name.data.strip()
            db.session.commit()

            if old_position != user.position:
                RemoveExcessivePosition()

            if UserRoles.validator in (user.role, old_role):
                for order in Order.query.filter(
                    Order.hub_id == current_user.hub_id,
                    Order.status != OrderStatus.approved,
                ).all():
                    order.update_positions()

            flash("Данные успешно сохранены.")
        else:
            flash_errors(user_form.about_user)
            if isinstance(user_form, UserRolesForm):
                flash_errors(user_form)
        return redirect(url_for("main.ShowSettings"))

    if current_user.role == UserRoles.admin:
        users = User.query.filter(or_(User.role == UserRoles.default, User.hub_id == current_user.hub_id))
        users = users.order_by(User.name, User.email).all()
        return render_template("settings.html", user_form=user_form, users=users)
    return render_template("settings.html", user_form=user_form)


@bp.route("/users/remove/<int:user_id>")
@login_required
@role_required([UserRoles.admin])
def RemoveUser(user_id):
    user = User.query.filter(
        User.id == user_id,
        or_(User.role == UserRoles.default, User.hub_id == current_user.hub_id),
    ).first()
    if user is None:
        flash("Пользователь не найден.")
        return redirect(url_for("main.ShowSettings"))

    for order in user.orders:
        order.initiative_id = current_user.id
    db.session.commit()

    db.session.delete(user)
    db.session.commit()

    RemoveExcessivePosition()

    if user.role in [UserRoles.purchaser, UserRoles.validator]:
        for order in Order.query.filter(
            Order.hub_id == current_user.hub_id, Order.status != OrderStatus.approved
        ).all():
            order.update_positions()

    flash("Пользователь успешно удалён.")
    return redirect(url_for("main.ShowSettings"))


@bp.route("/users/download")
@login_required
@role_required([UserRoles.admin])
def DownloadUsers():
    users = (
        User.query.filter(or_(User.role == UserRoles.default, User.hub_id == current_user.hub_id))
        .order_by(User.name, User.email)
        .all()
    )
    wb = Workbook()
    ws = wb.active
    for i, header in enumerate(
        [
            "Имя",
            "Телефон",
            "Email",
            "Роль",
            "Площадка",
            "Права",
            "Заметка",
            "Активность",
            "Регистрация",
            "Согласованных заявок пользователя",
            "Сумма согласованных заявок пользователя",
            "Согласовал заявок",
            "Должен согласовать заявок",
            "Номер для согласования",
            "День рождения",
            "Ссылка на дашборд",
        ],
        start=1,
    ):
        ws.cell(1, i).value = header

    for i, user in enumerate(users, start=2):
        ws.cell(i, 1).value = user.name
        ws.cell(i, 2).value = user.phone
        ws.cell(i, 3).value = user.email
        ws.cell(i, 4).value = user.position.name if user.position is not None else ""
        ws.cell(i, 5).value = user.location
        ws.cell(i, 6).value = user.role
        ws.cell(i, 7).value = user.note
        ws.cell(i, 8).value = user.last_seen
        ws.cell(i, 9).value = user.registered
        ws.cell(i, 15).value = user.birthday
        ws.cell(i, 16).value = (
            f'=HYPERLINK("{user.dashboard_url}", "{url_for("main.dashboard_redirect", user_id=user.id)}")'
        )

        # Orders which user is initiative for
        orders = Order.query.filter_by(initiative_id=user.id, status=OrderStatus.approved).all()
        ws.cell(i, 10).value = len(orders)
        ws.cell(i, 11).value = sum(o.total for o in orders)

        if user.role in [UserRoles.purchaser, UserRoles.validator]:
            # Orders approved by user
            orders = (
                Order.query.filter_by(hub_id=current_user.hub_id)
                .join(OrderApproval)
                .filter_by(user_id=user.id, product_id=None)
                .all()
            )
            ws.cell(i, 12).value = len(orders)

            # Orders to be approved
            orders = Order.query.filter(
                Order.hub_id == current_user.hub_id,
                or_(
                    Order.status == OrderStatus.new,
                    Order.status == OrderStatus.partly_approved,
                    Order.status == OrderStatus.modified,
                ),
                ~Order.user_approvals.any(OrderApproval.user_id == user.id),
                ~Order.children.any(),
            )
            orders = orders.join(OrderPosition)
            orders = orders.filter_by(position_id=user.position_id)
            orders = orders.join(OrderCategory)
            orders = orders.filter(OrderCategory.category_id.in_([cat.id for cat in user.categories]))
            orders = orders.join(Project)
            orders = orders.filter(Project.id.in_([p.id for p in user.projects]))
            orders = orders.all()
            ws.cell(i, 13).value = len(orders)
            ws.cell(i, 14).value = ", ".join([o.number for o in orders])
        else:
            ws.cell(i, 12).value = 0
            ws.cell(i, 13).value = 0
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return Response(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment;filename=users.xlsx"},
    )


@bp.route("/settings/hub/<int:hub_id>", methods=["GET"])
@login_required
@role_required([UserRoles.admin, UserRoles.supervisor])
def SwitchHub(hub_id):
    hub = Vendor.query.filter_by(hub_id=None, id=hub_id).first()
    if hub is None:
        flash("Такого хаба не существует.")
    else:
        current_user.hub_id = hub_id
        db.session.commit()
    return redirect(url_for("main.ShowIndex"))
