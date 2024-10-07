from datetime import datetime, timezone

from flask import flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.orm.attributes import flag_modified

from nadin.extensions import db
from nadin.main.forms import ChangeQuantityForm, InitiativeForm, LeaveCommentForm, OrderApprovalForm, SplitOrderForm
from nadin.main.routes import bp
from nadin.models.hub import User, UserRoles, Vendor
from nadin.models.order import EventType, Order, OrderApproval, OrderEvent, OrderStatus
from nadin.models.product import Category, Product
from nadin.models.project import Project
from nadin.utils import SendEmailNotification, flash_errors, role_forbidden, role_required

################################################################################
# Approve page
################################################################################


@bp.app_template_filter()
def intersect(a, b):
    return set(a).intersection(set(b))


def get_order(order_id):
    order = Order.get_by_access(current_user)
    order = order.filter(Order.id == order_id).first()
    return order


@bp.route("/orders/<int:order_id>")
@login_required
@role_forbidden([UserRoles.default])
def show_order(order_id):

    order = get_order(order_id)
    if order is None:
        flash("Заявка с таким номером не найдена.")
        return redirect(url_for("main.ShowIndex"))

    approval_form = OrderApprovalForm()
    quantity_form = ChangeQuantityForm()
    comment_form = LeaveCommentForm()
    initiative_form = InitiativeForm()

    comment_form.notify_reviewers.choices = [(r.id, r.name) for r in order.reviewers]

    if len(current_user.projects) > 0:
        projects = current_user.projects
        initiative_form.project.choices = [(p.id, p.name) for p in projects]
    else:
        initiative_form.project.choices = []

    if order.project:
        initiative_form.project.choices.append((order.project["id"], order.project["name"]))
        initiative_form.project.default = order.project["id"]
        initiative_form.process()

    split_form = SplitOrderForm()

    return render_template(
        "main/approve/approve.html",
        order=order,
        comment_form=comment_form,
        approval_form=approval_form,
        quantity_form=quantity_form,
        initiative_form=initiative_form,
        split_form=split_form,
    )


@bp.route("/orders/split/<int:order_id>", methods=["POST"])
@login_required
@role_required([UserRoles.admin, UserRoles.initiative, UserRoles.purchaser])
def split_order(order_id):

    order = get_order(order_id)
    if order is None:
        flash("Заявка с таким номером не найдена.")
        return redirect(url_for("main.ShowIndex"))

    if len(order.children) > 0:
        flash("Нельзя разделять заявки, которые были объединены или разделены.")
        return redirect(url_for("main.ShowIndex"))

    if order.status != OrderStatus.new:
        flash("Нельзя модифицировать согласованную или аннулированную заявку.")
        return redirect(url_for("main.show_order", order_id=order_id))

    form = SplitOrderForm()
    if form.validate_on_submit():
        product_ids = form.products.data
        if not isinstance(product_ids, list) or len(product_ids) == 0:
            flash("Некорректный список позиции.")
            return redirect(url_for("main.show_order", order_id=order_id))

        product_lists = [[], []]

        for product in order.products:
            if str(product["id"]) in product_ids:
                product_lists[0].append(product)
            else:
                product_lists[1].append(product)

        if len(product_lists[0]) == 0 or len(product_lists[1]) == 0:
            flash("Некорректный список позиции.")
            return redirect(url_for("main.show_order", order_id=order_id))

        message_flash = "заявка разделена на заявки"

        for product_list in product_lists:
            new_order_number = Order.new_order_number(current_user.hub_id)
            message_flash += f" {new_order_number}"
            new_order = Order(number=new_order_number)
            db.session.add(new_order)
            new_order.initiative_id = order.initiative_id
            new_order.initiative = order.initiative
            now = datetime.now(tz=timezone.utc)
            new_order.products = product_list
            new_order.total = sum(product["quantity"] * product["price"] for product in new_order.products)
            new_order.project_id = order.project_id
            new_order.project = order.project
            new_order.status = OrderStatus.new
            new_order.create_timestamp = int(now.timestamp())
            new_order.hub_id = order.hub_id
            categories = [product.get("categoryId", -1) for product in new_order.products]
            new_order.categories = Category.query.filter(
                Category.id.in_(categories), Category.hub_id == current_user.hub_id
            ).all()
            vendors = [product.get("vendor") for product in new_order.products]
            new_order.vendors = Vendor.query.filter(
                Vendor.name.in_(vendors), Vendor.hub_id == current_user.hub_id
            ).all()
            new_order.parents = [order]
            message = f"заявка получена разделением из заявки {order.number}"
            event = OrderEvent(
                user_id=current_user.id,
                order_id=new_order.id,
                type=EventType.splitted,
                data=message,
                timestamp=datetime.now(tz=timezone.utc),
            )
            db.session.add(event)
            db.session.commit()
            SendEmailNotification("new", new_order)

        order.total = 0.0
        event = OrderEvent(
            user_id=current_user.id,
            order_id=order_id,
            type=EventType.splitted,
            data=message_flash,
            timestamp=datetime.now(tz=timezone.utc),
        )
        db.session.add(event)
        db.session.commit()

        flash(message_flash)

    else:
        flash_errors(form)
    return redirect(url_for("main.ShowIndex"))


@bp.route("/orders/duplicate/<int:order_id>")
@login_required
@role_required([UserRoles.admin, UserRoles.initiative, UserRoles.purchaser])
def duplicate_order(order_id):
    order = get_order(order_id)
    if order is None:
        flash("Заявка с таким номером не найдена.")
        return redirect(url_for("main.ShowIndex"))

    order_number = Order.new_order_number(current_user.hub_id)
    new_order = Order(number=order_number)
    db.session.add(new_order)

    new_order.initiative = current_user.to_dict()
    new_order.initiative_id = current_user.id

    now = datetime.now(tz=timezone.utc)

    new_order.products = order.products
    new_order.total = order.total
    new_order.project_id = order.project_id
    new_order.project = order.project
    new_order.status = OrderStatus.new
    new_order.create_timestamp = int(now.timestamp())

    new_order.hub_id = current_user.hub_id
    new_order.categories = order.categories
    new_order.vendors = order.vendors

    message = f"заявка клонирована с номером {new_order.number}"
    event = OrderEvent(
        user_id=current_user.id,
        order_id=order.id,
        type=EventType.duplicated,
        data=message,
        timestamp=datetime.now(tz=timezone.utc),
    )
    db.session.add(event)
    message = f"заявка клонирована из заявки {order.number}"
    event = OrderEvent(
        user_id=current_user.id,
        order_id=new_order.id,
        type=EventType.duplicated,
        data=message,
        timestamp=datetime.now(tz=timezone.utc),
    )
    db.session.add(event)

    db.session.commit()

    flash(f"Заявка успешно клонирована. Номер новой заявки {new_order.number}. " "Вы перемещены в новую заявку.")

    SendEmailNotification("new", new_order)

    return redirect(url_for("main.show_order", order_id=new_order.id))


@bp.route("/orders/quantity/<int:order_id>", methods=["POST"])
@login_required
@role_required([UserRoles.admin, UserRoles.initiative, UserRoles.purchaser])
def save_quantity(order_id):

    order = get_order(order_id)
    if order is None:
        flash("Заявка с таким номером не найдена.")
        return redirect(url_for("main.ShowIndex"))

    if order.status != OrderStatus.new:
        flash("Нельзя модифицировать согласованную или аннулированную заявку.")
        return redirect(url_for("main.show_order", order_id=order_id))

    form = ChangeQuantityForm()
    if form.validate_on_submit():
        product = {}
        for idx, product in enumerate(order.products):
            if form.product_id.data == product["id"]:
                break
        else:
            idx = None
            product = (
                Product.query.filter_by(id=form.product_id.data)
                .join(Vendor, Product.vendor_id == Vendor.id)
                .filter(or_(Vendor.hub_id == current_user.hub_id, Product.vendor_id == current_user.hub_id))
                .first()
            )
            if not product:
                flash("Указанный товар не найден.")
                return redirect(url_for("main.show_order", order_id=order_id))
            product = product.to_dict(current_user.price_level, current_user.discount)
            product["categoryId"] = product["cat_id"]
            product["imageUrl"] = product["image"]
            product["quantity"] = 0
            product["selectedOptions"] = [{"name": "Единицы", "value": product["measurement"]}]
            order.products.append(product)

        if product["quantity"] != form.product_quantity.data:
            message = f"{product['sku']} количество было {product['quantity']} " f"стало {form.product_quantity.data}"
            product["quantity"] = form.product_quantity.data
            event = OrderEvent(
                user_id=current_user.id,
                order_id=order_id,
                type=EventType.quantity,
                data=message,
                timestamp=datetime.now(tz=timezone.utc),
            )
            db.session.add(event)

        approvals = (
            OrderApproval.query.join(User)
            .filter(OrderApproval.order_id == order_id, User.hub_id == current_user.hub_id)
            .all()
        )
        for approval in approvals:
            db.session.delete(approval)

        order.total = sum(p["quantity"] * p["price"] for p in order.products)
        order.status = OrderStatus.new

        if idx in range(len(order.products)) and form.product_quantity.data == 0:
            order.products.pop(idx)
        flag_modified(order, "products")

        db.session.commit()

        flash(f"Позиция {product['sku']} была изменена.")

    else:
        flash_errors(form)
    return redirect(url_for("main.show_order", order_id=order_id))


@bp.route("/orders/approval/<int:order_id>", methods=["POST"])
@login_required
@role_required([UserRoles.validator, UserRoles.warehouse])
def SaveApproval(order_id):
    order = get_order(order_id)
    if order is None:
        flash("Заявка с таким номером не найдена.")
        return redirect(url_for("main.ShowIndex"))

    if order.status == OrderStatus.cancelled:
        flash("Нельзя модифицировать аннулированную заявку.")
        return redirect(url_for("main.show_order", order_id=order_id))

    form = OrderApprovalForm()
    if form.validate_on_submit():

        message = form.comment.data.strip() or None

        user_approval = OrderApproval.query.filter_by(
            user_id=current_user.id,
            order_id=order.id,
            product_id=form.product_id.data,
            remark=message,
        ).first()

        if user_approval is not None:
            flash("Вы уже выполнили это действие.")
            return redirect(url_for("main.show_order", order_id=order_id))

        last_status = order.status

        if form.product_id.data is None:
            OrderApproval.query.filter_by(order_id=order_id, user_id=current_user.id).delete()

            position_disapprovals = OrderApproval.query.filter_by(order_id=order_id)
            position_disapprovals = position_disapprovals.join(User)

            for disapproval in position_disapprovals:
                db.session.delete(disapproval)

            order_approval = OrderApproval(
                order_id=order_id,
                product_id=None,
                user_id=current_user.id,
                remark=message,
            )
            db.session.add(order_approval)
            event = OrderEvent(
                user_id=current_user.id,
                order_id=order_id,
                type=EventType.approved,
                data=message,
                timestamp=datetime.now(tz=timezone.utc),
            )
            if current_user.role == UserRoles.validator:
                order.status = OrderStatus.authorized
            else:
                order.status = OrderStatus.unpayed
        else:
            OrderApproval.query.filter_by(order_id=order_id, user_id=current_user.id, product_id=None).delete()
            if form.product_id.data == 0:
                event = OrderEvent(
                    user_id=current_user.id,
                    order_id=order_id,
                    type=EventType.disapproved,
                    data=message,
                    timestamp=datetime.now(tz=timezone.utc),
                )
                product_approval = OrderApproval(
                    order_id=order_id,
                    product_id=0,
                    user_id=current_user.id,
                    remark=message,
                )
                db.session.add(product_approval)
                order.status = OrderStatus.cancelled
            else:
                product = {}
                for product in order.products:
                    if form.product_id.data == product["id"]:
                        break
                else:
                    flash("Указанный позиция не найдена в заявке.")
                    return redirect(url_for("main.show_order", order_id=order_id))
                product_approval = OrderApproval.query.filter_by(
                    order_id=order_id,
                    user_id=current_user.id,
                    product_id=form.product_id.data,
                ).first()
                if product_approval is None:
                    product_approval = OrderApproval(
                        order_id=order_id,
                        product_id=form.product_id.data,
                        user_id=current_user.id,
                    )
                    db.session.add(product_approval)
                product_approval.remark = message
                message = f"к позиции \"{product['name']}\" {message or ''}"
                event = OrderEvent(
                    user_id=current_user.id,
                    order_id=order_id,
                    type=EventType.disapproved,
                    data=message,
                    timestamp=datetime.now(tz=timezone.utc),
                )
                order.status = OrderStatus.clarification
        db.session.add(event)
        db.session.commit()
        flash("Согласование сохранено.")

        if order.status != last_status:
            if order.status == OrderStatus.new:
                SendEmailNotification("approved", order)

            elif order.status in [OrderStatus.cancelled, OrderStatus.clarification]:
                SendEmailNotification("disapproved", order)

    else:
        flash_errors(form)
    return redirect(url_for("main.show_order", order_id=order_id))


@bp.route("/orders/parameters/<int:order_id>", methods=["POST"])
@login_required
@role_required([UserRoles.admin, UserRoles.initiative, UserRoles.purchaser])
def SaveParameters(order_id):
    order = get_order(order_id)
    if order is None:
        flash("Заявка с таким номером не найдена.")
        return redirect(url_for("main.ShowIndex"))

    if order.status != OrderStatus.new:
        flash("Нельзя модифицировать согласованную или аннулированную заявку.")
        return redirect(url_for("main.show_order", order_id=order_id))

    form = InitiativeForm()

    projects = Project.query.filter(Project.hub_id == current_user.hub_id).order_by(Project.name).all()

    form.project.choices = [(p.id, p.name) for p in projects]

    if form.validate_on_submit() is True:
        new_project = Project.query.filter_by(id=form.project.data, hub_id=current_user.hub_id).first()
        if new_project is not None and (order.project is None or order.project_id != new_project.id):
            message = f'Клиент изменён «{order.project['name'] if order.project else ""}» на «{new_project.name}»'
            event = OrderEvent(
                user_id=current_user.id,
                order_id=order_id,
                type=EventType.project,
                data=message,
                timestamp=datetime.now(tz=timezone.utc),
            )
            db.session.add(event)
            order.project = new_project.to_dict()
            order.project_id = new_project.id

        OrderApproval.query.filter_by(order_id=order.id).delete()
        db.session.commit()

        flash("Параметры заявки успешно сохранены.")
    else:
        flash_errors(form)
    return redirect(url_for("main.show_order", order_id=order_id))


@bp.route("/orders/comment/<int:order_id>", methods=["POST"])
@login_required
def LeaveComment(order_id):
    order = get_order(order_id)
    if order is None:
        flash("Заявка с таким номером не найдена.")
        return redirect(url_for("main.ShowIndex"))
    form = LeaveCommentForm()
    form.notify_reviewers.choices = [(r.id, r.name) for r in order.reviewers]
    if form.validate_on_submit():
        form.comment_and_send_email(order, EventType.commented)
        db.session.commit()
    else:
        flash_errors(form)
    return redirect(url_for("main.show_order", order_id=order_id))


@bp.route("/orders/process/<int:order_id>")
@login_required
@role_required([UserRoles.admin, UserRoles.purchaser])
def ProcessHubOrder(order_id):
    order = get_order(order_id)
    if order is None:
        flash("Заявка с таким номером не найдена.")
        return redirect(url_for("main.ShowIndex"))

    if order.status == OrderStatus.cancelled:
        flash("Нельзя отправить поставщику аннулированную заявку.")
        return redirect(url_for("main.show_order", order_id=order_id))

    message = "Заявка была отправлена поставщикам: "
    message += ", ".join(vendor.name for vendor in order.vendors)

    event = OrderEvent(
        user_id=current_user.id,
        order_id=order_id,
        type=EventType.purchased,
        data=message,
        timestamp=datetime.now(tz=timezone.utc),
    )
    db.session.add(event)

    db.session.commit()

    flash(message)

    return redirect(url_for("main.show_order", order_id=order_id))


@bp.route("/orders/cancel/<int:order_id>", methods=["POST"])
@login_required
@role_required([UserRoles.admin, UserRoles.initiative, UserRoles.purchaser])
def cancel_order(order_id):
    order = get_order(order_id)
    if order is None:
        flash("Заявка с таким номером не найдена.")
        return redirect(url_for("main.ShowIndex"))

    if order.status == OrderStatus.cancelled:
        flash("Нельзя аннулировать аннулированную заявку.")
        return redirect(url_for("main.show_order", order_id=order_id))

    form = LeaveCommentForm()
    form.notify_reviewers.choices = [(r.id, r.name) for r in order.reviewers]
    if form.validate_on_submit():
        order.status = OrderStatus.cancelled
        order.total = 0
        form.comment_and_send_email(order, EventType.cancelled)
        db.session.commit()
        flash("Заявка аннулирована.")
    else:
        flash_errors(form)
    return redirect(url_for("main.show_order", order_id=order_id))
