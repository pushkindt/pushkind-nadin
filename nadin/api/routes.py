from flask import Blueprint, current_app, g, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import not_, or_
from sqlalchemy.sql.expression import func

from nadin.api.auth import basic_auth
from nadin.api.errors import error_response
from nadin.extensions import db
from nadin.models import Category, OrderLimit, Product, Project, User, UserRoles, Vendor

bp = Blueprint("api", __name__)


@bp.route("/daily/limits", methods=["GET"])
@basic_auth.login_required
def daily_update_limits_current():
    user = User.query.get_or_404(g.user_id)
    if user.role != UserRoles.admin:
        return error_response(403)
    OrderLimit.update_current(hub_id=user.hub_id)
    return "", 200


@bp.route("/category/<int:category_id>", methods=["GET"])
def get_category(category_id: int):
    if category_id == 0:
        category = {
            "name": "",
            "id": category_id,
            "children": [(c.id, c.name) for c in Category.query.filter(not_(Category.name.like("%/%"))).all()],
        }
    else:
        category = Category.query.get_or_404(category_id).to_dict()
        category["children"] = [(c.id, c.name) for c in Category.query.filter(Category.id.in_(category["children"]))]
    response = jsonify(category)
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response


@bp.route("/category/<int:category_id>/products", methods=["GET"])
def get_category_products(category_id: int):
    if category_id != 0:
        category = Category.query.get_or_404(category_id)
        products = Product.query.filter_by(cat_id=category.id)
        products = db.paginate(products, max_per_page=current_app.config["MAX_PER_PAGE"])
    else:
        products = Product.query.order_by(func.random()).limit(current_app.config["MAX_PER_PAGE"]).all()

    products = [p.to_dict() for p in products]
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
@login_required
def search_products():
    search_key = request.args.get("q", type=str)

    if search_key:
        products, _ = Product.search(search_key, page=1, per_page=current_app.config["MAX_PER_PAGE"])
    else:
        products = Product.query

    products = products.join(Vendor, Product.vendor_id == Vendor.id).filter(
        or_(Vendor.hub_id == current_user.hub_id, Product.vendor_id == current_user.hub_id)
    )
    if not search_key:
        products = products.order_by(Product.name)

    products = db.paginate(products, page=1, max_per_page=current_app.config["MAX_PER_PAGE"])
    products = [p.to_dict() for p in products]
    return jsonify(products)
