import os

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm.attributes import flag_modified

from nadin.extensions import db
from nadin.main.forms import AddCategoryForm, AppSettingsForm, CategoryResponsibilityForm
from nadin.models.hub import AppSettings, UserRoles
from nadin.models.product import Category
from nadin.utils import flash_errors, role_required

bp = Blueprint("admin", __name__)


@bp.route("/", methods=["GET", "POST"])
@login_required
@role_required([UserRoles.admin])
def ShowAdminPage():
    forms = {
        "add_category": AddCategoryForm(),
        "edit_category": CategoryResponsibilityForm(),
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
    forms["edit_category"].process()

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
    return redirect(url_for("admin.ShowAdminPage"))


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
    return redirect(url_for("admin.ShowAdminPage"))


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
    return redirect(url_for("admin.ShowAdminPage"))


@bp.route("/category/remove/<int:category_id>")
@login_required
@role_required([UserRoles.admin])
def RemoveCategory(category_id):
    category = Category.query.filter_by(id=category_id).first()
    if category is not None:
        if category.children:
            flash("Невозможно удалить категорию, содержащую подкатегории.")
            return redirect(url_for("admin.ShowAdminPage"))
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
    return redirect(url_for("admin.ShowAdminPage"))
