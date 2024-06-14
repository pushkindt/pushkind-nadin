from datetime import datetime, timezone

from flask import flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import not_

from nadin.extensions import db
from nadin.main.forms import CreateOrderForm
from nadin.main.routes import bp
from nadin.main.utils import GetNewOrderNumber, SendEmailNotification, role_required
from nadin.models import (
    AppSettings,
    Category,
    Order,
    OrderLimit,
    OrderStatus,
    Product,
    Project,
    Site,
    UserRoles,
    Vendor,
)


@bp.route("/shop/")
@login_required
@role_required([UserRoles.initiative, UserRoles.purchaser, UserRoles.admin])
def shop_categories():
    projects = Project.query
    if current_user.role != UserRoles.admin:
        projects = projects.filter_by(enabled=True)
    projects = projects.filter_by(hub_id=current_user.hub_id)
    projects = projects.order_by(Project.name).all()
    limits = OrderLimit.query.filter_by(hub_id=current_user.hub_id).all()
    categories = Category.query.filter(Category.hub_id == current_user.hub_id, not_(Category.name.like("%/%"))).all()
    return render_template("shop_categories.html", projects=projects, limits=limits, categories=categories)


@bp.route("/shop/<int:cat_id>", defaults={"vendor_id": None})
@bp.route("/shop/<int:cat_id>/<int:vendor_id>")
@login_required
@role_required([UserRoles.initiative, UserRoles.purchaser, UserRoles.admin])
def shop_products(cat_id, vendor_id):
    category = Category.query.filter_by(id=cat_id, hub_id=current_user.hub_id).first()
    if category is None:
        return redirect(url_for("main.shop_categories"))
    if category.children:
        categories = Category.query.filter(
            Category.hub_id == current_user.hub_id, Category.id.in_(category.children)
        ).all()
    else:
        categories = []
    products = Product.query.filter_by(cat_id=cat_id)
    if vendor_id is not None:
        products = products.filter_by(vendor_id=vendor_id)
    products = products.join(Vendor).filter_by(enabled=True)
    products = products.order_by(Product.name).all()
    vendor_ids = {p.vendor_id for p in products}
    vendors = Vendor.query.filter(Vendor.id.in_(vendor_ids)).all()
    return render_template(
        "shop_products.html",
        category=category,
        categories=categories,
        vendors=vendors,
        products=products,
        vendor_id=vendor_id,
    )


@bp.route("/shop/order", methods=["GET", "POST"])
@login_required
@role_required([UserRoles.initiative, UserRoles.purchaser, UserRoles.admin])
def shop_cart():
    form = CreateOrderForm()
    if form.submit.data:
        if form.validate_on_submit():
            settings = AppSettings.query.filter_by(hub_id=current_user.hub_id).first()
            products = Product.query.filter(Product.id.in_(p["product"] for p in form.cart.data)).all()
            if len(products) == 0:
                flash("Заявка не может быть пуста.")
                return render_template("shop_cart.html", form=form)
            site = Site.query.filter_by(id=form.site_id.data, project_id=form.project_id.data).first()
            if site is None:
                flash("Такой площадки не существует.")
                return redirect(url_for("main.shop_cart"))
            order_products = []
            order_vendors = []
            categories = []
            products = {p.id: p for p in products}
            for cart_item in form.cart.data:
                product = products[cart_item["product"]]
                if product is None:
                    continue
                categories.append(product.cat_id)
                order_vendors.append(product.vendor)
                order_product = {
                    "id": product.id,
                    "sku": product.sku,
                    "price": product.price,
                    "name": product.name,
                    "imageUrl": product.image,
                    "categoryId": product.cat_id,
                    "vendor": product.vendor.name,
                    "category": product.category.name,
                    "quantity": cart_item["quantity"],
                    "selectedOptions": [{"name": "Единицы", "value": product.measurement}],
                }
                if cart_item["text"]:
                    order_product["selectedOptions"].append({"value": cart_item["text"], "name": "Комментарий"})
                if cart_item["options"] and product.options:
                    for opt, values in product.options.items():
                        if opt in cart_item["options"] and cart_item["options"][opt] in values:
                            order_product["selectedOptions"].append({"value": cart_item["options"][opt], "name": opt})
                order_products.append(order_product)
            categories = list(set(categories))
            if settings.single_category_orders and len(categories) > 1:
                flash("Заявки с более чем одной категорией не разрешены.")
                return redirect(url_for("main.shop_categories"))
            order_number = GetNewOrderNumber()
            now = datetime.now(tz=timezone.utc)
            categories = Category.query.filter(Category.id.in_(categories)).all()
            cashflow_id, income_id = max((c.cashflow_id, c.income_id) for c in categories)
            order = Order(
                number=order_number,
                initiative_id=current_user.id,
                create_timestamp=int(now.timestamp()),
                site_id=site.id,
                hub_id=current_user.hub_id,
                products=order_products,
                vendors=list(set(order_vendors)),
                total=sum([p["quantity"] * p["price"] for p in order_products]),
                status=OrderStatus.new,
                cashflow_id=cashflow_id,
                income_id=income_id,
            )
            db.session.add(order)
            order.categories = categories
            db.session.commit()
            order.update_positions()
            flash("Заявка успешно создана.")
            SendEmailNotification("new", order)
            return redirect(url_for("main.ShowIndex"))
        else:
            for _, errorMessages in form.errors.items():
                for err in errorMessages:
                    flash(err)
    return render_template("shop_cart.html", form=form)
