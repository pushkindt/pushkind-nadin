import math
from functools import wraps

from authlib.integrations.flask_oauth2 import current_token
from flask import Blueprint, current_app, jsonify, make_response, request
from flask_login import current_user, login_required
from pydantic import ValidationError

from nadin.api.errors import error_response
from nadin.extensions import db
from nadin.models.hub import UserRoles
from nadin.models.order import Order, OrderEvent
from nadin.models.product import Category, Product, ProductTag
from nadin.models.project import Project, ProjectPriceLevel
from nadin.models.shopping_cart import ApiShoppingCartModel
from nadin.oauth.server import require_oauth

bp = Blueprint("api", __name__)


def cors_preflight_response(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if request.method == "OPTIONS":
            response = make_response()
            response.headers.add("Access-Control-Allow-Origin", "*")
            response.headers.add("Access-Control-Allow-Headers", "*")
            response.headers.add("Access-Control-Allow-Methods", "*")
            return response
        response = fn(*args, **kwargs)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    return wrapper


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


@bp.route("/tags", methods=["GET", "OPTIONS"])
@require_oauth(optional=True)
@cors_preflight_response
def get_tags():

    tags = ProductTag.query.all()
    tags = set(tag.tag for tag in tags if tag.tag)
    response = jsonify(list(tags))
    return response


@bp.route("/category/<int:category_id>", methods=["GET", "OPTIONS"])
@require_oauth(optional=True)
@cors_preflight_response
def get_category(category_id: int):

    if category_id == 0:
        category = Category.get_root_category()
    else:
        category = Category.query.filter_by(id=category_id).first()
        if category is None:
            return error_response(404)
        category = category.to_dict()
    response = jsonify(category)
    return response


@bp.route("/category/<int:category_id>/products", methods=["GET", "OPTIONS"])
@require_oauth(optional=True)
@cors_preflight_response
def get_category_products(category_id: int):

    tag = request.args.get("tag", type=str)
    page = request.args.get("page", default=1, type=int)
    sort_by = request.args.get("sort_by", default="name_asc", type=str)
    sort_by, order = sort_by.split("_", 1)

    price_level = get_price_level()
    discount = get_discount()

    products = Product.query

    if not tag and not category_id:
        page = 1
        pages = 1
        total = current_app.config["MAX_PER_PAGE"]
        products = products.order_by(Product.id).limit(total).all()

    else:

        if category_id != 0:
            category = Category.query.filter_by(id=category_id).first()
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
    return response


@bp.route("/projects/search", methods=["GET", "OPTIONS"])
@login_required
@cors_preflight_response
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


@bp.route("/products/search", methods=["GET", "OPTIONS"])
@require_oauth(optional=True)
@cors_preflight_response
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
    return response


@bp.route("/product/<int:product_id>", methods=["GET", "OPTIONS"])
@require_oauth(optional=True)
@cors_preflight_response
def get_product(product_id: int):

    price_level = get_price_level()
    discount = get_discount()

    product = Product.query.filter_by(id=product_id).first()
    if not product:
        return error_response(404)

    response = jsonify(product.to_dict(price_level, discount))
    return response


@bp.route("/prices", methods=["GET", "OPTIONS"])
@require_oauth(optional=True)
@cors_preflight_response
def get_product_prices():
    # convert to int skipping ids that cannot be converted to int
    product_ids = [int(id) for id in request.args.getlist("ids") if id.isdigit()]
    products = Product.query.filter(Product.id.in_(product_ids)).all()

    price_level = get_price_level()
    discount = get_discount()
    products = {p.id: p.get_price(price_level, discount) for p in products}
    response = jsonify(products)
    return response


@bp.route("/order", methods=["POST", "OPTIONS"])
@cors_preflight_response
@require_oauth()
def create_order():

    try:
        cart = ApiShoppingCartModel.model_validate(request.get_json())
    except ValidationError as exc:
        return error_response(400, str(exc))

    try:
        order = Order.from_api_request(current_token.user, cart)
    except ValueError as exc:
        return error_response(400, str(exc))

    db.session.add(order)
    db.session.commit()

    if cart.comment:
        comment = OrderEvent(data=cart.comment, user_id=order.initiative_id, order_id=order.id)
        db.session.add(comment)
        db.session.commit()

    response = jsonify(
        {
            "id": order.id,
            "number": order.number,
            "status": order.status.name,
        }
    )
    return response
