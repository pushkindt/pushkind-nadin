import os

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm.attributes import flag_modified

from nadin.admin.forms import AddHubForm, SelectHubForm
from nadin.extensions import db
from nadin.main.forms import AddCategoryForm, AppSettingsForm, CategoryResponsibilityForm
from nadin.models.hub import AppSettings, UserRoles, Vendor
from nadin.models.product import Category
from nadin.utils import flash_errors, role_required

bp = Blueprint("admin", __name__)


@bp.route("/", methods=["GET"])
@login_required
@role_required([UserRoles.admin])
def show_admin_page():
    forms = {
        "add_category": AddCategoryForm(),
        "edit_category": CategoryResponsibilityForm(),
        "add_hub": AddHubForm(),
        "select_hub": SelectHubForm(),
    }

    app_data = AppSettings.query.filter_by(hub_id=current_user.hub_id).first()
    if app_data is None:
        forms["app"] = AppSettingsForm(order_id_bias=0)
    else:
        forms["app"] = AppSettingsForm(
            enable=app_data.notify_1C,
            email=app_data.email_1C,
            order_id_bias=app_data.order_id_bias or 0,
            single_category_orders=app_data.single_category_orders,
            alert=app_data.alert,
        )

    categories = Category.query.filter(Category.hub_id == current_user.hub_id).all()

    forms["add_category"].parent.choices = [(c.id, c.name) for c in categories]
    forms["add_category"].parent.choices.insert(0, (0, "Выберите категорию..."))
    forms["add_category"].process()

    forms["select_hub"].hub_id.choices = [
        (hub.id, f"{hub.id}: {hub.name} ({hub.email})") for hub in Vendor.query.filter(Vendor.hub_id.is_(None)).all()
    ]
    forms["select_hub"].hub_id.default = current_user.hub_id
    forms["select_hub"].process()

    return render_template(
        "admin/admin.html",
        forms=forms,
        categories=categories,
    )


@bp.route("/app/save", methods=["POST"])
@login_required
@role_required([UserRoles.admin])
def SaveAppSettings():
    form = AppSettingsForm()
    if form.validate_on_submit():
        app_data = AppSettings.query.filter_by(hub_id=current_user.hub_id).first()
        if app_data is None:
            app_data = AppSettings(hub_id=current_user.hub_id)
            db.session.add(app_data)
        app_data.notify_1C = form.enable.data
        app_data.email_1C = form.email.data
        app_data.order_id_bias = form.order_id_bias.data
        app_data.single_category_orders = form.single_category_orders.data
        alert = form.alert.data.strip() if form.alert.data else None
        app_data.alert = alert if alert else None
        if form.image.data:
            f = form.image.data
            file_name, file_ext = os.path.splitext(f.filename)
            file_name = f"logo{current_user.hub_id}{file_ext}"
            full_path = os.path.join("nadin", "static", "upload", file_name)
            f.save(full_path)
        db.session.commit()
        flash("Настройки рассылки 1С успешно сохранены.")
    else:
        flash_errors(form)
    return redirect(url_for("admin.show_admin_page"))


@bp.route("/category/edit/", methods=["POST"])
@login_required
@role_required([UserRoles.admin])
def SaveCategoryResponsibility():
    form = CategoryResponsibilityForm()
    if form.validate_on_submit():
        category = Category.query.filter_by(id=form.category_id.data, hub_id=current_user.hub_id).first()
        if category is None:
            flash("Категория с таким идентификатором не найдена.")
        else:
            category.code = form.code.data.strip()
            if form.image.data:
                f = form.image.data
                file_name, file_ext = os.path.splitext(f.filename)
                file_name = f"category-{category.id}{file_ext}"
                full_path = os.path.join("nadin", "static", "upload", file_name)
                f.save(full_path)
                category.image = url_for("static", filename=os.path.join("upload", file_name))

            db.session.commit()
            flash("Категория успешно отредактирована.")
    else:
        flash_errors(form)
    return redirect(url_for("admin.show_admin_page"))


@bp.route("/category/add/", methods=["POST"])
@login_required
@role_required([UserRoles.admin])
def AddCategory():
    form = AddCategoryForm()
    categories = Category.query.filter(Category.hub_id == current_user.hub_id).all()
    form.parent.choices = [(c.id, c.name) for c in categories]
    form.parent.choices.insert(0, (0, ""))
    if form.validate_on_submit():
        category_name = form.category_name.data.strip().replace("/", "_")
        category = Category.query.filter_by(hub_id=current_user.hub_id, name=category_name).first()
        if category is None:
            if form.parent.data > 0:
                parent = Category.query.get(form.parent.data)
                category_name = parent.name + "/" + category_name
            else:
                parent = None
            category = Category(name=category_name, hub_id=current_user.hub_id, children=[])
            db.session.add(category)
            db.session.commit()
            if parent:
                parent.children.append(category.id)
                flag_modified(parent, "children")
                db.session.commit()
            flash(f"Категория {category_name} добавлена.")
        else:
            flash(f"Категория {category_name} уже существует.")
    else:
        flash_errors(form)
    return redirect(url_for("admin.show_admin_page"))


@bp.route("/category/remove/<int:category_id>")
@login_required
@role_required([UserRoles.admin])
def RemoveCategory(category_id):
    category = Category.query.filter_by(id=category_id).first()
    if category is not None:
        if category.children:
            flash("Невозможно удалить категорию, содержащую подкатегории.")
            return redirect(url_for("admin.show_admin_page"))
        db.session.delete(category)
        db.session.commit()
        parent = Category.query.filter(Category.children.contains([category_id])).first()
        if parent:
            parent.children.remove(category_id)
            flag_modified(parent, "children")
            db.session.commit()
        flash(f'Категория "{category.name}" удалена.')
    else:
        flash("Такой категории не существует.")
    return redirect(url_for("admin.show_admin_page"))


@bp.route("/hub/add", methods=["POST"])
@login_required
@role_required([UserRoles.admin])
def add_hub():

    form = AddHubForm()

    if form.validate_on_submit():
        hub = Vendor.query.filter_by(email=form.email.data).first()
        if hub is None:
            hub = Vendor(name=form.name.data, email=form.email.data)
            db.session.add(hub)
            db.session.commit()
            flash("Хаб добавлен.")
        else:
            flash("Хаб с таким электронным адресом уже существует.")
    else:
        flash_errors(form)

    return redirect(url_for("admin.show_admin_page"))


@bp.route("/hub/select", methods=["POST"])
@login_required
@role_required([UserRoles.admin, UserRoles.supervisor])
def select_hub():

    form = SelectHubForm()
    form.hub_id.choices = [(hub.id, hub.name) for hub in Vendor.query.filter(Vendor.hub_id.is_(None)).all()]
    if form.validate_on_submit():
        current_user.hub_id = form.hub_id.data
        db.session.commit()
        flash("Хаб изменен.")
    else:
        flash_errors(form)

    return redirect(url_for("main.ShowIndex"))
