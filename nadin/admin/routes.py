import os

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm.attributes import flag_modified

from nadin.extensions import db
from nadin.main.forms import (
    AddCashflowForm,
    AddCategoryForm,
    AddIncomeForm,
    AppSettingsForm,
    CategoryResponsibilityForm,
    EditCashflowForm,
    EditIncomeForm,
)
from nadin.models.hub import AppSettings, UserRoles
from nadin.models.order import CashflowStatement, IncomeStatement
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
        "add_income": AddIncomeForm(),
        "add_cashflow": AddCashflowForm(),
        "edit_income": EditIncomeForm(),
        "edit_cashflow": EditCashflowForm(),
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

    incomes = IncomeStatement.query.filter(IncomeStatement.hub_id == current_user.hub_id)
    incomes = incomes.order_by(IncomeStatement.name).all()
    cashflows = CashflowStatement.query.filter(CashflowStatement.hub_id == current_user.hub_id)
    cashflows = cashflows.order_by(CashflowStatement.name).all()

    forms["add_category"].parent.choices = [(c.id, c.name) for c in categories]
    forms["add_category"].parent.choices.insert(0, (0, "Выберите категорию..."))
    forms["edit_category"].income_statement.choices = [(i.id, i.name) for i in incomes]
    forms["edit_category"].cashflow_statement.choices = [(c.id, c.name) for c in cashflows]
    forms["edit_category"].income_statement.choices.append((0, "Выберите БДР..."))
    forms["edit_category"].cashflow_statement.choices.append((0, "Выберите БДДС..."))
    forms["edit_category"].process()

    return render_template(
        "admin.html",
        forms=forms,
        categories=categories,
        incomes=incomes,
        cashflows=cashflows,
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
    incomes = IncomeStatement.query.filter_by(id=form.income_statement.data, hub_id=current_user.hub_id).all()
    cashflows = CashflowStatement.query.filter_by(id=form.cashflow_statement.data, hub_id=current_user.hub_id).all()
    form.income_statement.choices = [(i.id, i.name) for i in incomes]
    form.cashflow_statement.choices = [(c.id, c.name) for c in cashflows]
    if form.validate_on_submit():
        category = Category.query.filter_by(id=form.category_id.data, hub_id=current_user.hub_id).first()
        if category is None:
            flash("Категория с таким идентификатором не найдена.")
        else:
            category.responsible = form.responsible.data.strip()
            category.functional_budget = form.functional_budget.data.strip()
            category.code = form.code.data.strip()
            category.income_id = form.income_statement.data
            category.cashflow_id = form.cashflow_statement.data
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


@bp.route("/income/add", methods=["POST"])
@login_required
@role_required([UserRoles.admin])
def AddIncome():
    form = AddIncomeForm()
    if form.validate_on_submit():
        income_name = form.income_name.data.strip()
        income = IncomeStatement.query.filter_by(name=income_name, hub_id=current_user.hub_id).first()
        if income is None:
            income = IncomeStatement(name=income_name, hub_id=current_user.hub_id)
            db.session.add(income)
            db.session.commit()
            flash(f'БДР "{income_name}" добавлен.')
        else:
            flash(f'БДР "{income_name}" уже существует.')
    else:
        flash_errors(form)
    return redirect(url_for("admin.ShowAdminPage"))


@bp.route("/cashflow/add", methods=["POST"])
@login_required
@role_required([UserRoles.admin])
def AddCashflow():
    form = AddCashflowForm()
    if form.validate_on_submit():
        cashflow_name = form.cashflow_name.data.strip()
        cashflow = CashflowStatement.query.filter_by(name=cashflow_name, hub_id=current_user.hub_id).first()
        if cashflow is None:
            cashflow = CashflowStatement(name=cashflow_name, hub_id=current_user.hub_id)
            db.session.add(cashflow)
            db.session.commit()
            flash(f'БДДС "{cashflow_name}" добавлен.')
        else:
            flash(f'БДДС "{cashflow_name}" уже существует.')
    else:
        flash_errors(form)
    return redirect(url_for("admin.ShowAdminPage"))


@bp.route("/income/remove/<int:income_id>")
@login_required
@role_required([UserRoles.admin])
def RemoveIncome(income_id):
    income = IncomeStatement.query.filter_by(id=income_id).first()
    if income is not None:
        db.session.delete(income)
        db.session.commit()
        flash(f'БДР "{income.name}" удален.')
    else:
        flash("Такой БДР не существует.")
    return redirect(url_for("admin.ShowAdminPage"))


@bp.route("/cashflow/remove/<int:cashflow_id>")
@login_required
@role_required([UserRoles.admin])
def RemoveCashflow(cashflow_id):
    cashflow = CashflowStatement.query.filter_by(id=cashflow_id).first()
    if cashflow is not None:
        db.session.delete(cashflow)
        db.session.commit()
        flash(f'БДДС "{cashflow.name}" удален.')
    else:
        flash("Такой БДДС не существует.")
    return redirect(url_for("admin.ShowAdminPage"))


@bp.route("/income/edit/", methods=["POST"])
@login_required
@role_required([UserRoles.admin])
def EditIncome():
    form = EditIncomeForm()
    if form.validate_on_submit():
        income = IncomeStatement.query.filter_by(id=form.income_id.data).first()
        if income is not None:
            income_name = form.income_name.data.strip()
            existed = IncomeStatement.query.filter_by(name=income_name, hub_id=current_user.hub_id).first()
            if existed is None or existed.id == income.id:
                income.name = income_name
                db.session.commit()
                flash(f'БДР "{income_name}" изменён.')
            else:
                flash(f'БДР "{income_name}" уже существует.')
        else:
            flash("Такой БДР не существует.")
    else:
        flash_errors(form)
    return redirect(url_for("admin.ShowAdminPage"))


@bp.route("/cashflow/edit/", methods=["POST"])
@login_required
@role_required([UserRoles.admin])
def EditCashflow():
    form = EditCashflowForm()
    if form.validate_on_submit():
        cashflow = CashflowStatement.query.filter_by(id=form.cashflow_id.data).first()
        if cashflow is not None:
            cashflow_name = form.cashflow_name.data.strip()
            existed = CashflowStatement.query.filter_by(name=cashflow_name, hub_id=current_user.hub_id).first()
            if existed is None or existed.id == cashflow.id:
                cashflow.name = cashflow_name
                db.session.commit()
                flash(f'БДДС "{cashflow_name}" изменён.')
            else:
                flash(f'БДДС "{cashflow_name}" уже существует.')
        else:
            flash("Такой БДДС не существует.")
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
