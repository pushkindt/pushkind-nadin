from datetime import datetime, timezone
from urllib.parse import quote

from flask import current_app, flash, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import not_, or_

from nadin.extensions import db
from nadin.main.forms import CreateOrderForm
from nadin.main.routes import bp
from nadin.models.hub import UserRoles, Vendor
from nadin.models.order import AppSettings, EventType, Order, OrderEvent, OrderStatus
from nadin.models.product import Category, Product
from nadin.models.project import Project
from nadin.utils import SendEmailNotification, flash_errors, role_required


@bp.route("/shop/search")
@login_required
@role_required([UserRoles.initiative, UserRoles.purchaser, UserRoles.admin])
def shop_search():
    search_key = request.args.get("search", type=str)
    vendor_id = request.args.get("vendor_id", type=int)

    if not search_key:
        return redirect(url_for("main.shop_categories"))

    page = request.args.get("page", type=int, default=1)
    category = {
        "id": 0,
        "name": f"Поиск: {search_key}",
    }

    products, total = Product.search(search_key, page, current_app.config["MAX_PER_PAGE"])
    if vendor_id is not None:
        products = products.filter_by(vendor_id=vendor_id)
    products = products.join(Vendor, Product.vendor_id == Vendor.id).filter(
        or_(Vendor.hub_id == current_user.hub_id, Product.vendor_id == current_user.hub_id)
    )
    products = db.paginate(products, page=1, max_per_page=current_app.config["MAX_PER_PAGE"])
    products.total = total
    products.page = page
    categories = set(product.category for product in products)
    vendors = set(product.vendor for product in products)

    return render_template(
        "shop_products.html",
        search_key=search_key,
        category=category,
        categories=categories,
        vendors=vendors,
        products=products,
        vendor_id=vendor_id,
    )


@bp.route("/shop/")
@login_required
@role_required([UserRoles.initiative, UserRoles.purchaser, UserRoles.admin])
def shop_categories():

    categories = Category.query.filter(Category.hub_id == current_user.hub_id, not_(Category.name.like("%/%"))).all()
    response = make_response(render_template("shop_categories.html", categories=categories))
    if len(current_user.projects) == 1:
        response.set_cookie("project_id", str(current_user.projects[0].id))
        response.set_cookie("project_name", quote(current_user.projects[0].name))
    return response


@bp.route("/shop/<int:cat_id>", defaults={"vendor_id": None})
@bp.route("/shop/<int:cat_id>/<int:vendor_id>")
@login_required
@role_required([UserRoles.initiative, UserRoles.purchaser, UserRoles.admin])
def shop_products(cat_id, vendor_id):

    project_id = request.cookies.get("project_id", type=int)

    project = Project.query.filter_by(id=project_id, hub_id=current_user.hub_id).first()
    if not project:
        flash("Выберите клиента.")
        return redirect(url_for("main.shop_categories"))

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
    products = db.paginate(products.order_by(Product.name), max_per_page=current_app.config["MAX_PER_PAGE"])
    vendor_ids = {p.vendor_id for p in products}
    vendors = Vendor.query.filter(Vendor.id.in_(vendor_ids)).all()
    return render_template(
        "shop_products.html",
        category=category,
        categories=categories,
        vendors=vendors,
        products=products,
        vendor_id=vendor_id,
        project=project,
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
            project = Project.query.filter_by(id=form.project_id.data).first()
            if project is None:
                flash("Такого клиента не существует.")
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
            order_number = Order.new_order_number(current_user.hub_id)
            now = datetime.now(tz=timezone.utc)
            categories = Category.query.filter(Category.id.in_(categories)).all()
            cashflow_id, income_id = max((c.cashflow_id, c.income_id) for c in categories)
            order = Order(
                number=order_number,
                initiative_id=current_user.id,
                create_timestamp=int(now.timestamp()),
                project_id=project.id,
                hub_id=current_user.hub_id,
                products=order_products,
                vendors=list(set(order_vendors)),
                total=sum(p["quantity"] * p["price"] for p in order_products),
                status=OrderStatus.new,
                cashflow_id=cashflow_id,
                income_id=income_id,
            )
            db.session.add(order)
            order.categories = categories
            db.session.commit()
            order.update_positions()
            if form.comment.data:
                event = OrderEvent(
                    user_id=current_user.id,
                    order_id=order.id,
                    type=EventType.commented,
                    data=form.comment.data,
                    timestamp=datetime.now(tz=timezone.utc),
                )
                db.session.add(event)
                db.session.commit()
            flash("Заявка успешно создана.")
            SendEmailNotification("new", order)
            return redirect(url_for("main.ShowIndex"))

        flash_errors(form)
    return render_template("shop_cart.html", form=form)
