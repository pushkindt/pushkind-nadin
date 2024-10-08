import enum
from datetime import datetime, timezone

from sqlalchemy.sql import func

from nadin.extensions import db
from nadin.models.hub import AppSettings, User, UserProject, UserRoles, Vendor
from nadin.models.product import Product
from nadin.models.search import SearchableMixin
from nadin.models.shopping_cart import ApiShoppingCartModel


class EventType(enum.IntEnum):
    commented = 0
    approved = 1
    disapproved = 2
    quantity = 3
    duplicated = 4
    purchased = 5
    exported = 6
    merged = 7
    dealdone = 8
    income_statement = 9
    cashflow_statement = 10
    site = 11
    measurement = 12
    splitted = 13
    project = 14
    notification = 15
    cancelled = 16

    def __str__(self):
        pretty = [
            "комментарий",
            "согласование",
            "замечание",
            "изменение",
            "клонирование",
            "оплачена",
            "доставляется",
            "объединение",
            "выдана",
            "изменение",
            "изменение",
            "изменение",
            "изменение",
            "разделение",
            "изменение",
            "уведомление",
            "аннулирована",
        ]
        return pretty[self.value]

    def color(self):
        colors = [
            "warning",
            "success",
            "danger",
            "primary",
            "dark",
            "dark",
            "dark",
            "dark",
            "dark",
            "primary",
            "primary",
            "primary",
            "primary",
            "dark",
            "primary",
            "dark",
            "danger",
        ]
        return colors[self.value]


class OrderStatus(enum.IntEnum):
    new = 0
    unpayed = 1
    payed = 2
    delivering = 3
    delivered = 4
    fulfilled = 5
    cancelled = 6
    returned = 7
    clarification = 8
    authorized = 9

    def __str__(self):
        pretty = [
            "Обработка",
            "К оплате",
            "Оплачена",
            "Доставка",
            "Выдача",
            "Получена",
            "Отменёна",
            "Возврат",
            "Уточнение",
            "Авторизован",
        ]
        return pretty[self.value]

    def color(self):
        colors = ["white", "primary", "info", "info", "info", "success", "danger", "danger", "warning", "primary"]
        return colors[self.value]


class OrderApproval(db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id", ondelete="CASCADE"), nullable=False)
    product_id = db.Column(db.Integer, index=True, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    remark = db.Column(db.String(512), nullable=True)
    user = db.relationship("User", back_populates="approvals")
    order = db.relationship("Order", back_populates="user_approvals")

    def __bool__(self):
        return self.product_id is None


class OrderEvent(SearchableMixin, db.Model):

    __searchable__ = ["data", "type"]

    id = db.Column(db.Integer, primary_key=True, nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id", ondelete="CASCADE"), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    timestamp = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.now(tz=timezone.utc),
        server_default=func.current_timestamp(),
    )
    type = db.Column(db.Enum(EventType), nullable=False, default=EventType.commented)
    data = db.Column(db.String(512), nullable=True)
    user = db.relationship("User", back_populates="events")
    order = db.relationship("Order", back_populates="events")


OrderRelationship = db.Table(
    "order_relationship",
    db.Model.metadata,
    db.Column("order_id", db.Integer, db.ForeignKey("order.id"), primary_key=True),
    db.Column("child_id", db.Integer, db.ForeignKey("order.id"), primary_key=True),
)


class Order(SearchableMixin, db.Model):

    __searchable__ = ["number", "initiative", "project", "products"]

    id = db.Column(db.Integer, primary_key=True, nullable=False)
    number = db.Column(db.String(128), nullable=False)
    initiative_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    create_timestamp = db.Column(db.Integer, nullable=False)
    products = db.Column(db.JSON(), nullable=False)
    total = db.Column(db.Float, nullable=False)
    status = db.Column(
        db.Enum(OrderStatus),
        nullable=False,
        default=OrderStatus.new,
        server_default="new",
    )
    project_id = db.Column(db.Integer, db.ForeignKey("project.id", ondelete="SET NULL"), nullable=True)
    hub_id = db.Column(db.Integer, db.ForeignKey("vendor.id", ondelete="CASCADE"), nullable=False)

    categories = db.relationship("Category", secondary="order_category")
    vendors = db.relationship("Vendor", secondary="order_vendor")
    hub = db.relationship("Vendor", back_populates="orders")
    events = db.relationship(
        "OrderEvent",
        cascade="all, delete",
        back_populates="order",
        passive_deletes=True,
    )
    user_approvals = db.relationship("OrderApproval", back_populates="order", viewonly=True)
    children = db.relationship(
        "Order",
        secondary=OrderRelationship,
        primaryjoin=id == OrderRelationship.c.order_id,
        secondaryjoin=id == OrderRelationship.c.child_id,
        viewonly=True,
    )
    parents = db.relationship(
        "Order",
        secondary=OrderRelationship,
        primaryjoin=id == OrderRelationship.c.child_id,
        secondaryjoin=id == OrderRelationship.c.order_id,
    )
    initiative = db.Column(db.JSON(), nullable=False)
    project = db.Column(db.JSON(), nullable=False)

    @property
    def categories_list(self):
        return [c.id for c in self.categories]

    @property
    def validators(self):
        if self.project is None:
            return []
        validators = (
            User.query.filter_by(role=UserRoles.validator, hub_id=self.hub_id)
            .join(UserProject)
            .filter(UserProject.project_id == self.project_id)
        )
        return validators.all()

    @property
    def purchasers(self):
        if self.project is None:
            return []
        purchasers = (
            User.query.filter_by(role=UserRoles.purchaser, hub_id=self.hub_id)
            .join(UserProject)
            .filter(UserProject.project_id == self.project_id)
        )
        return purchasers.all()

    @property
    def reviewers(self):
        result = User.query.filter_by(id=self.initiative_id).all()
        if self.project is None:
            return result
        result += self.validators + self.purchasers
        return result

    @property
    def create_date(self):
        return datetime.fromtimestamp(self.create_timestamp, tz=timezone.utc)

    @create_date.setter
    def create_date(self, dt):
        self.create_timestamp = int(dt.timestamp())

    @classmethod
    def new_order_number(cls, hub_id):
        settings = AppSettings.query.filter_by(hub_id=hub_id).first()
        order_id_bias = settings.order_id_bias if settings is not None else 0
        count = db.session.query(Order).count() + order_id_bias
        return f"{count}"

    @classmethod
    def from_api_request(cls, user: User, cart: ApiShoppingCartModel):

        order = cls()
        order.number = cls.new_order_number(user.hub_id)
        order.initiative_id = user.id
        order.initiative = user.to_dict()
        order.hub_id = user.hub_id
        order.create_timestamp = datetime.timestamp(datetime.now(tz=timezone.utc))
        order.status = OrderStatus.new
        if len(user.projects) == 1:
            order.project = user.projects[0].to_dict()
            order.project_id = user.projects[0].id
        else:
            order.project = {}
            order.project_id = None

        products = Product.query.filter(Product.id.in_(int(p_id) for p_id in cart.items.keys())).all()
        if not products:
            raise ValueError("Products not found")

        order.products = []
        order_categories = set()
        order_vendors = set()
        for product in products:
            order_categories.add(product.cat_id)
            order_vendors.add(product.vendor_id)
            cart_item = cart.items[str(product.id)]
            order_product = {
                "id": product.id,
                "quantity": cart_item.quantity,
                "sku": product.sku,
                "price": product.get_price(user.price_level, user.discount),
                "name": product.name,
                "imageUrl": product.image,
                "categoryId": product.cat_id,
                "vendor": product.vendor.name,
                "category": product.category.name,
                "selectedOptions": [
                    {"name": "Единицы", "value": product.measurement},
                ],
            }
            if cart_item.comment:
                order_product["selectedOptions"].append({"value": cart_item.comment, "name": "Комментарий"})
            if cart_item.options and product.options:
                for opt, values in product.options.items():
                    if opt in cart_item.options and cart_item.options[opt] in values:
                        order_product["selectedOptions"].append({"value": cart_item.options[opt], "name": opt})
            order.products.append(order_product)

        order.total = sum(p["price"] * p["quantity"] for p in order.products)
        return order

    @classmethod
    def get_by_access(cls, user: User, query=None):
        if query is None:
            query = Order.query
        orders = query.filter_by(hub_id=user.hub_id)
        if user.role == UserRoles.vendor:
            vendor = Vendor.query.filter_by(hub_id=user.hub_id, email=user.email).first()
            vendor_id = vendor.id if vendor else None
            orders = orders.filter(Order.vendors.any(OrderVendor.vendor_id == vendor_id))
        elif user.projects:
            orders = orders.filter(Order.project_id.in_(user.projects_list))
        elif user.role == UserRoles.initiative:
            orders = orders.filter(Order.initiative_id == user.id)
        return orders


class OrderCategory(db.Model):
    __tablename__ = "order_category"
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), primary_key=True)


class OrderVendor(db.Model):
    __tablename__ = "order_vendor"
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendor.id"), primary_key=True)
