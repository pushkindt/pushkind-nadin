import enum
import json
from datetime import datetime, timezone

from sqlalchemy.sql import expression, func

from nadin.extensions import db
from nadin.models.hub import AppSettings, Position, User, UserCategory, UserProject, UserRoles
from nadin.models.project import Project
from nadin.models.shopping_cart import ApiShoppingCartModel
from nadin.utils import get_filter_timestamps


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
            "отправлено поставщику",
            "экспорт в 1С",
            "объединение",
            "законтрактовано",
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
    not_approved = 1
    partly_approved = 2
    approved = 3
    modified = 4
    cancelled = 5

    def __str__(self):
        pretty = [
            "Новая",
            "Отклонена",
            "В работе",
            "Согласована",
            "Исправлена",
            "Аннулирована",
        ]
        return pretty[self.value]

    def color(self):
        colors = ["white", "danger", "warning", "success", "secondary", "danger"]
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


class OrderEvent(db.Model):
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


class Order(db.Model):
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
    income_id = db.Column(  # БДР
        db.Integer,
        db.ForeignKey("income_statement.id", ondelete="SET NULL"),
        nullable=True,
    )
    cashflow_id = db.Column(  # БДДС
        db.Integer,
        db.ForeignKey("cashflow_statement.id", ondelete="SET NULL"),
        nullable=True,
    )
    hub_id = db.Column(db.Integer, db.ForeignKey("vendor.id", ondelete="CASCADE"), nullable=False)
    purchased = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    exported = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    dealdone = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    over_limit = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    dealdone_responsible_name = db.Column(db.String(128))
    dealdone_responsible_comment = db.Column(db.String(128))
    categories = db.relationship("Category", secondary="order_category")
    vendors = db.relationship("Vendor", secondary="order_vendor")
    hub = db.relationship("Vendor", back_populates="orders")
    events = db.relationship(
        "OrderEvent",
        cascade="all, delete",
        back_populates="order",
        passive_deletes=True,
    )
    approvals = db.relationship("OrderPosition", backref="order")
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
    income_statement = db.relationship("IncomeStatement", back_populates="orders")
    cashflow_statement = db.relationship("CashflowStatement", back_populates="orders")
    initiative = db.relationship("User", back_populates="orders")
    project = db.relationship("Project", back_populates="orders")

    def update_status(self):
        if self.project is None or self.project.enabled is False or self.status == OrderStatus.cancelled:
            return
        approved = [p.approved for p in self.approvals]
        if all(approved):
            self.status = OrderStatus.approved
            return
        disapproved = OrderApproval.query.filter(
            OrderApproval.order_id == self.id, OrderApproval.product_id.isnot(None)
        ).all()
        if len(disapproved) > 0:
            self.status = OrderStatus.not_approved
            return
        self.status = OrderStatus.partly_approved
        return

    @property
    def dealdone_comment(self):
        if self.dealdone is False:
            return None
        event = (
            OrderEvent.query.filter_by(order_id=self.id, type=EventType.dealdone)
            .order_by(OrderEvent.timestamp.desc())
            .first()
        )
        return event.data if event else None

    @property
    def categories_list(self):
        return [c.id for c in self.categories]

    @property
    def validators(self):
        if self.project is None or len(self.categories) == 0:
            return []
        validators = (
            User.query.filter_by(role=UserRoles.validator)
            .join(UserCategory)
            .filter(UserCategory.category_id.in_(self.categories_list))
            .join(UserProject)
            .filter(UserProject.project_id == self.project_id)
            .join(Position)
            .join(OrderPosition)
            .filter_by(order_id=self.id)
        )
        return validators.all()

    @property
    def purchasers(self):
        if self.project is None or len(self.categories) == 0:
            return []
        purchasers = (
            User.query.filter_by(role=UserRoles.purchaser)
            .join(UserCategory)
            .filter(UserCategory.category_id.in_(self.categories_list))
            .join(UserProject)
            .filter(UserProject.project_id == self.project_id)
        )
        return purchasers.all()

    @property
    def reviewers(self):
        result = User.query.filter_by(id=self.initiative_id).all()
        if self.project is None or len(self.categories) == 0:
            return result
        result += self.validators + self.purchasers
        return result

    def update_positions(self, update_status=False):
        # Orders with no project and categories binding have no responsible positions
        if self.project is None or len(self.categories) == 0:
            return
        # Query positions which have validators with the same project
        # and categories bindings as the order
        # Update the order's responsible positions
        positions = (
            Position.query.filter_by(hub_id=self.hub_id)
            .join(User)
            .filter(User.role == UserRoles.validator)
            .join(UserCategory, User.id == UserCategory.user_id)
            .filter(UserCategory.category_id.in_(self.categories_list))
            .join(UserProject, User.id == UserProject.user_id)
            .filter(UserProject.project_id == self.project_id)
            .all()
        )

        old_approvals = {appr.position_id: appr for appr in self.approvals}

        OrderPosition.query.filter_by(order_id=self.id).delete()

        db.session.commit()

        approvals = []
        # Update those which have users approved the order

        for position in positions:
            old_approval = old_approvals.get(position.id)
            order_position = OrderPosition(order=self, position=position)
            if old_approval is None:
                user_approval = (
                    OrderApproval.query.filter(
                        OrderApproval.order_id == self.id,
                        OrderApproval.product_id.is_(None),
                    )
                    .join(User)
                    .filter(
                        User.position_id == position.id,
                        User.role == UserRoles.validator,
                    )
                    .first()
                )
                if user_approval is not None:
                    order_position.user_id = user_approval.user_id
                    order_position.approved = True
            else:
                order_position.user_id = old_approval.user_id
                order_position.approved = old_approval.approved
                order_position.timestamp = old_approval.timestamp
            approvals.append(order_position)
        self.approvals = approvals
        if update_status is True:
            self.update_status()
        db.session.commit()

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
    def from_api_request(cls, email: str, data: ApiShoppingCartModel):
        order = cls()
        order.create_timestamp = datetime.timestamp(datetime.now(tz=timezone.utc))
        order.status = OrderStatus.new
        order.products = []
        order.total = 0.0
        return order


class OrderCategory(db.Model):
    __tablename__ = "order_category"
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), primary_key=True)


class OrderVendor(db.Model):
    __tablename__ = "order_vendor"
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendor.id"), primary_key=True)


class OrderPosition(db.Model):
    __tablename__ = "order_position"
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), primary_key=True)
    position_id = db.Column(db.Integer, db.ForeignKey("position.id"), primary_key=True)
    approved = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    timestamp = db.Column(db.DateTime, nullable=True)
    user = db.relationship("User")
    position = db.relationship("Position")


class IncomeStatement(db.Model):
    __tablename__ = "income_statement"
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    name = db.Column(db.String(128), nullable=False, index=True)
    hub_id = db.Column(db.Integer, db.ForeignKey("vendor.id", ondelete="CASCADE"), nullable=False)
    hub = db.relationship("Vendor", back_populates="income_statements")
    orders = db.relationship("Order", back_populates="income_statement")

    def __repr__(self):
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def to_dict(self):
        data = {"id": self.id, "name": self.name}
        return data


class CashflowStatement(db.Model):
    __tablename__ = "cashflow_statement"
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    name = db.Column(db.String(128), nullable=False, index=True)
    hub_id = db.Column(db.Integer, db.ForeignKey("vendor.id", ondelete="CASCADE"), nullable=False)
    hub = db.relationship("Vendor", back_populates="cashflow_statements")
    order_limits = db.relationship(
        "OrderLimit",
        back_populates="cashflow_statement",
        cascade="all, delete",
        passive_deletes=True,
    )
    orders = db.relationship("Order", back_populates="cashflow_statement")

    def __repr__(self):
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def to_dict(self):
        data = {"id": self.id, "name": self.name}
        return data


class OrderLimitsIntervals(enum.IntEnum):
    daily = 0
    weekly = 1
    monthly = 2
    quarterly = 3
    annually = 4
    all_time = 5

    def __str__(self):
        pretty = ["День", "Неделя", "Месяц", "Квартал", "Год", "Всё время"]
        return pretty[self.value]


class OrderLimit(db.Model):
    __tablename__ = "order_limit"
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    hub_id = db.Column(db.Integer, db.ForeignKey("vendor.id", ondelete="CASCADE"), nullable=False)
    value = db.Column(db.Float, nullable=False, default=0.0, server_default="0.0")
    current = db.Column(db.Float, nullable=False, default=0.0, server_default="0.0")
    cashflow_id = db.Column(
        db.Integer,
        db.ForeignKey("cashflow_statement.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id = db.Column(db.Integer, db.ForeignKey("project.id", ondelete="CASCADE"), nullable=False)
    interval = db.Column(
        db.Enum(OrderLimitsIntervals),
        index=True,
        nullable=False,
        default=OrderLimitsIntervals.monthly,
        server_default="monthly",
    )
    cashflow_statement = db.relationship("CashflowStatement", back_populates="order_limits")
    project = db.relationship("Project", back_populates="order_limits")
    hub = db.relationship("Vendor", back_populates="order_limits")

    @classmethod
    def update_current(cls, hub_id, project_id=None, cashflow_id=None):
        limits = OrderLimit.query.filter_by(hub_id=hub_id)

        if project_id is not None and cashflow_id is not None:
            limits = limits.filter_by(project_id=project_id, cashflow_id=cashflow_id)

        limits = limits.all()

        filters = get_filter_timestamps()
        for limit in limits:
            orders = Order.query

            if limit.interval == OrderLimitsIntervals.daily:
                orders = orders.filter(Order.create_timestamp > filters["daily"])
            elif limit.interval == OrderLimitsIntervals.weekly:
                orders = orders.filter(Order.create_timestamp > filters["weekly"])
            elif limit.interval == OrderLimitsIntervals.monthly:
                orders = orders.filter(Order.create_timestamp > filters["monthly"])
            elif limit.interval == OrderLimitsIntervals.quarterly:
                orders = orders.filter(Order.create_timestamp > filters["quarterly"])
            elif limit.interval == OrderLimitsIntervals.annually:
                orders = orders.filter(Order.create_timestamp > filters["annually"])

            orders = orders.filter(Order.cashflow_id == limit.cashflow_id)
            orders = orders.join(Project)
            orders = orders.filter(Project.id == limit.project_id).all()
            limit.current = sum(o.total for o in orders if o.status == OrderStatus.approved)
            if limit.current > 0.95 * limit.value:
                for order in orders:
                    order.over_limit = order.status != OrderStatus.approved

        db.session.commit()
