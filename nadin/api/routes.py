import math

import sqlalchemy as sa
from authlib.integrations.flask_oauth2 import current_token
from flask import Blueprint, current_app, flash, g, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from nadin.api.auth import basic_auth
from nadin.api.errors import error_response
from nadin.api.forms import OrderForm
from nadin.extensions import db
from nadin.models.hub import User, UserRoles, Vendor
from nadin.models.order import Order, OrderEvent, OrderLimit
from nadin.models.product import Category, Product, ProductTag
from nadin.models.project import Project, ProjectPriceLevel
from nadin.oauth.server import require_oauth
from nadin.utils import flash_errors

bp = Blueprint("api", __name__)


def get_hub_id() -> int:
    if current_token:
        return current_token.user.hub_id
    elif "hub_id" in request.args:
        return request.args.get("hub_id", type=int)
    else:
        hub = Vendor.query.filter(Vendor.hub_id == sa.null()).first()
        return hub.id if hub else None


def get_price_level() -> ProjectPriceLevel:
    if current_token:
        return current_token.user.price_level
    else:
        return ProjectPriceLevel.online_store


def get_discount() -> float:
    if current_token:
        return current_token.user.discount
    else:
        return 0.0


@bp.route("/daily/limits", methods=["GET"])
@basic_auth.login_required
def daily_update_limits_current():
    user = User.query.get_or_404(g.user_id)
    if user.role != UserRoles.admin:
        return error_response(403)
    OrderLimit.update_current(hub_id=user.hub_id)
    return "", 200


@bp.route("/tags", methods=["GET"])
@require_oauth(optional=True)
def get_tags():
    hub_id = get_hub_id()
    tags = (
        ProductTag.query.join(Product)
        .join(Vendor, Product.vendor_id == Vendor.id)
        .filter(or_(Vendor.hub_id == hub_id, Product.vendor_id == hub_id))
        .all()
    )
    tags = set(tag.tag for tag in tags if tag.tag)
    response = jsonify(list(tags))
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response


@bp.route("/category/<int:category_id>", methods=["GET"])
@require_oauth(optional=True)
def get_category(category_id: int):

    hub_id = get_hub_id()

    if category_id == 0:
        category = Category.get_root_category(hub_id=hub_id)
    else:
        category = Category.query.filter_by(hub_id=hub_id, id=category_id).first()
        if category is None:
            return error_response(404)
        category = category.to_dict()
    response = jsonify(category)
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response


@bp.route("/category/<int:category_id>/products", methods=["GET"])
@require_oauth(optional=True)
def get_category_products(category_id: int):

    tag = request.args.get("tag", type=str)
    page = request.args.get("page", default=1, type=int)
    sort_by = request.args.get("sort_by", default="name_asc", type=str)
    sort_by, order = sort_by.split("_", 1)

    hub_id = get_hub_id()
    price_level = get_price_level()
    discount = get_discount()

    products = Product.query.join(Vendor, Product.vendor_id == Vendor.id).filter(
        or_(Vendor.hub_id == hub_id, Product.vendor_id == hub_id)
    )

    if not tag and not category_id:
        page = 1
        pages = 1
        total = current_app.config["MAX_PER_PAGE"]
        products = products.order_by(Product.id).limit(total).all()

    else:

        if category_id != 0:
            category = Category.query.filter_by(hub_id=hub_id, id=category_id).first()
            if category is None:
                return error_response(404)
            products = products.join(Category, onclause=Category.id == Product.cat_id).filter(
                Category.name.startswith(category.name)
            )
        if tag:
            products = products.join(ProductTag, onclause=ProductTag.product_id == Product.id).filter(
                ProductTag.tag == tag
            )

        try:
            order_func = getattr(Product, sort_by)
        except AttributeError:
            order_func = Product.name
        if order == "desc":
            order_func = order_func.desc()
        else:
            order_func = order_func.asc()

        products = products.order_by(order_func)

        products = db.paginate(products, page=page, max_per_page=current_app.config["MAX_PER_PAGE"])
        pages = products.pages
        total = products.total

    products = {
        "total": total,
        "page": page,
        "pages": pages,
        "products": [p.to_dict(price_level, discount) for p in products],
    }
    response = jsonify(products)
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response


@bp.route("/projects/search", methods=["GET"])
@login_required
def search_projects():
    search_key = request.args.get("q", type=str)

    if search_key:
        projects, _ = Project.search(search_key, page=1, per_page=current_app.config["MAX_PER_PAGE"])
    else:
        projects = Project.query

    projects = projects.filter_by(hub_id=current_user.hub_id)

    if current_user.role != UserRoles.admin and current_user.projects:
        projects = projects.filter(Project.id.in_(p.id for p in current_user.projects))

    if current_user.role != UserRoles.admin:
        projects = projects.filter_by(enabled=True)
    if not search_key:
        projects = projects.order_by(Project.name)

    projects = db.paginate(projects, page=1, max_per_page=current_app.config["MAX_PER_PAGE"])
    projects = [p.to_dict() for p in projects]
    return jsonify(projects)


@bp.route("/products/search", methods=["GET"])
@require_oauth(optional=True)
def search_products():
    search_key = request.args.get("q", type=str, default="~")
    page = request.args.get("page", default=1, type=int)

    price_level = get_price_level()
    discount = get_discount()

    products, total = Product.search(search_key, page=page, per_page=current_app.config["MAX_PER_PAGE"])

    total_pages = math.ceil(total / current_app.config["MAX_PER_PAGE"])

    if page > total_pages:
        products = []
    else:
        products = db.session.scalars(products).all()
    products = {
        "total": total,
        "page": page,
        "pages": total_pages,
        "products": [p.to_dict(price_level, discount) for p in products],
    }
    response = jsonify(products)
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response


@bp.route("/product/<int:product_id>", methods=["GET"])
@require_oauth(optional=True)
def get_product(product_id: int):

    hub_id = get_hub_id()
    price_level = get_price_level()
    discount = get_discount()

    product = (
        Product.query.join(Vendor, Product.vendor_id == Vendor.id)
        .filter(or_(Vendor.hub_id == hub_id, Product.vendor_id == hub_id))
        .filter_by(id=product_id)
        .first()
    )
    if not product:
        return error_response(404)

    response = jsonify(product.to_dict(price_level, discount))
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response


@bp.route("/order", methods=["POST"])
def create_order():
    form = OrderForm()
    if form.validate_on_submit():

        user = User.query.filter_by(email=form.email.data.lower()).first()

        if not user:
            flash("Пользователь не найден.")
            return render_template("api/order_error.html", return_url=request.referrer)

        try:
            order = Order.from_api_request(form.email.data, form.cart.data)
        except ValueError as e:
            flash(str(e))
            return render_template("api/order_error.html", return_url=request.referrer)

        db.session.add(order)
        db.session.commit()

        if form.comment.data:
            comment = OrderEvent(data=form.comment.data, user_id=order.initiative_id, order_id=order.id)
            db.session.add(comment)
            db.session.commit()

        flash(f"Заказ #{order.number} успешно оформлен")
        return redirect(url_for("main.ShowIndex"))
    flash_errors(form)
    return render_template("api/order_error.html", return_url=request.referrer)
