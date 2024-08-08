import enum
import json
from datetime import datetime, timezone
from hashlib import md5
from time import time

import jwt
import sqlalchemy as sa
from authlib.integrations.sqla_oauth2 import OAuth2AuthorizationCodeMixin, OAuth2ClientMixin, OAuth2TokenMixin
from flask import current_app
from flask_login import UserMixin
from sqlalchemy.sql import expression, func
from werkzeug.security import check_password_hash, generate_password_hash

from nadin import search
from nadin.extensions import db, login_manager
from nadin.utils import get_filter_timestamps


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class SearchableMixin:
    __searchable__: list = []

    @classmethod
    def search(cls, expr: str, page: int, per_page: int, fields: list = None):
        ids, total = search.query_index(cls.__tablename__, expr, page, per_page, fields=fields)
        query = sa.select(cls).where(cls.id.in_(ids))
        if total > 0:
            when = []
            for i, val in enumerate(ids):
                when.append((val, i))
            query = query.order_by(db.case(*when, value=cls.id))
        return query, total

    @classmethod
    def before_commit(cls, session):
        session._changes = {"add": list(session.new), "update": list(session.dirty), "delete": list(session.deleted)}

    @classmethod
    def after_commit(cls, session):
        for obj in session._changes["add"]:
            if isinstance(obj, SearchableMixin):
                search.add_to_index(obj.__tablename__, obj)
        for obj in session._changes["update"]:
            if isinstance(obj, SearchableMixin):
                search.add_to_index(obj.__tablename__, obj)
        for obj in session._changes["delete"]:
            if isinstance(obj, SearchableMixin):
                search.remove_from_index(obj.__tablename__, obj)
        session._changes = None

    @classmethod
    def reindex(cls):
        for obj in db.session.scalars(sa.select(cls)):
            search.add_to_index(cls.__tablename__, obj)


db.event.listen(db.session, "before_commit", SearchableMixin.before_commit)
db.event.listen(db.session, "after_commit", SearchableMixin.after_commit)


class ProjectPriceLevel(enum.IntEnum):
    online_store = 0
    marketplace = 1
    small_wholesale = 2
    large_wholesale = 3
    distributor = 4
    exclusive = 5
    retail = 6
    retail_promo = 7

    @staticmethod
    def pretty_names() -> dict[str, "ProjectPriceLevel"]:
        pretty = {
            "ИНТЕРНЕТ": ProjectPriceLevel.online_store,
            "МАРКЕТ": ProjectPriceLevel.marketplace,
            "МЕЛКИЙ ОПТ": ProjectPriceLevel.small_wholesale,
            "КРУПНЫЙ ОПТ": ProjectPriceLevel.large_wholesale,
            "ДИСТРИБЬЮТОР": ProjectPriceLevel.distributor,
            "ЭКСКЛЮЗИВ": ProjectPriceLevel.exclusive,
            "СЕТИ": ProjectPriceLevel.retail,
            "СЕТИ ПРОМО": ProjectPriceLevel.retail_promo,
        }
        return pretty

    @staticmethod
    def from_pretty(value: str) -> "ProjectPriceLevel":
        pretty = ProjectPriceLevel.pretty_names()
        return pretty.get(value.upper(), ProjectPriceLevel.online_store)

    def __str__(self):
        pretty = list(ProjectPriceLevel.pretty_names().keys())
        return pretty[self.value]


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


class UserRoles(enum.IntEnum):
    default = 0
    admin = 1
    initiative = 2
    validator = 3
    purchaser = 4
    supervisor = 5
    vendor = 6

    def __str__(self):
        pretty = [
            "Без роли",
            "Администратор",
            "Инициатор",
            "Валидатор",
            "Закупщик",
            "Наблюдатель",
            "Поставщик",
        ]
        return pretty[self.value]


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


class Vendor(db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    hub_id = db.Column(db.Integer, db.ForeignKey("vendor.id", ondelete="CASCADE"), nullable=True)
    name = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(128), nullable=False, unique=True, index=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    users = db.relationship("User", back_populates="hub", cascade="all, delete", passive_deletes=True)
    positions = db.relationship("Position", back_populates="hub", cascade="all, delete", passive_deletes=True)
    categories = db.relationship("Category", back_populates="hub", cascade="all, delete", passive_deletes=True)
    settings = db.relationship("AppSettings", back_populates="hub", cascade="all, delete", passive_deletes=True)
    projects = db.relationship("Project", back_populates="hub", cascade="all, delete", passive_deletes=True)
    orders = db.relationship("Order", back_populates="hub", cascade="all, delete", passive_deletes=True)
    income_statements = db.relationship(
        "IncomeStatement",
        back_populates="hub",
        cascade="all, delete",
        passive_deletes=True,
    )
    cashflow_statements = db.relationship(
        "CashflowStatement",
        back_populates="hub",
        cascade="all, delete",
        passive_deletes=True,
    )
    order_limits = db.relationship("OrderLimit", back_populates="hub", cascade="all, delete", passive_deletes=True)
    products = db.relationship("Product", back_populates="vendor", cascade="all, delete", passive_deletes=True)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    email = db.Column(db.String(128), index=True, unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    role = db.Column(
        db.Enum(UserRoles),
        index=True,
        nullable=False,
        default=UserRoles.default,
        server_default="default",
    )
    name = db.Column(db.String(128), nullable=True)
    phone = db.Column(db.String(128), nullable=True)
    position_id = db.Column(db.Integer, db.ForeignKey("position.id", ondelete="SET NULL"), nullable=True)
    location = db.Column(db.String(512), nullable=True)
    hub_id = db.Column(db.Integer, db.ForeignKey("vendor.id", ondelete="CASCADE"), nullable=True)
    email_new = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    email_modified = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    email_disapproved = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    email_approved = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    email_comment = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    last_seen = db.Column(db.DateTime, nullable=True)
    note = db.Column(db.Text(), nullable=True)
    registered = db.Column(db.DateTime, nullable=True)
    birthday = db.Column(db.Date, nullable=True)
    dashboard_url = db.Column(db.String(512), nullable=True)
    categories = db.relationship("Category", secondary="user_category", backref="users")
    projects = db.relationship("Project", secondary="user_project", backref="users")
    events = db.relationship("OrderEvent", cascade="all, delete", back_populates="user", passive_deletes=True)
    approvals = db.relationship(
        "OrderApproval",
        cascade="all, delete",
        back_populates="user",
        lazy="dynamic",
        passive_deletes=True,
    )
    orders = db.relationship("Order", back_populates="initiative")
    hub = db.relationship("Vendor", back_populates="users", foreign_keys=[hub_id])
    position = db.relationship("Position", back_populates="users")

    @property
    def projects_list(self):
        return [p.id for p in self.projects]

    @property
    def categories_list(self):
        return [c.id for c in self.categories]

    @property
    def hub_list(self):
        if self.role in [UserRoles.admin, UserRoles.supervisor]:
            return Vendor.query.filter_by(hub_id=None).all()
        return [self.hub]

    def __hash__(self):
        return self.id

    def __eq__(self, another):
        return isinstance(another, User) and self.id == another.id

    def __repr__(self):
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def get_user_id(self):
        return self.id

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def get_avatar(self, size):
        digest = md5(self.email.lower().encode("utf-8")).hexdigest()
        return f"https://www.gravatar.com/avatar/{digest}?d=identicon&s={size}"

    def to_dict(self):
        data = {
            "id": self.id,
            "email": self.email,
            "phone": self.phone if self.phone is not None else "",
            "note": self.note,
            "birthday": self.birthday.isoformat() if self.birthday is not None else "",
            "role": self.role.name,
            "role_id": int(self.role),
            "position": self.position.name if self.position is not None else "",
            "name": self.name if self.name is not None else "",
            "hub_id": self.hub_id,
            "location": self.location if self.location is not None else "",
            "email_new": self.email_new,
            "email_modified": self.email_modified,
            "email_disapproved": self.email_disapproved,
            "email_approved": self.email_approved,
            "email_comment": self.email_comment,
            "projects": self.projects_list,
            "categories": self.categories_list,
            "dashboard_url": self.dashboard_url,
        }
        return data

    def get_jwt_token(self, expires_in=600):
        return jwt.encode(
            {"user_id": self.id, "exp": time() + expires_in},
            current_app.config["SECRET_KEY"],
            algorithm="HS256",
        )

    @staticmethod
    def verify_jwt_token(token):
        try:
            user_id = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])["user_id"]
        except ValueError:
            return None
        return User.query.get(user_id)


class Position(db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    name = db.Column(db.String(128), nullable=False, index=True)
    hub_id = db.Column(db.Integer, db.ForeignKey("vendor.id", ondelete="CASCADE"), nullable=False)
    users = db.relationship("User", back_populates="position")
    hub = db.relationship("Vendor", back_populates="positions")

    def __eq__(self, other):
        if not isinstance(other, Position) or self.id != other.id:
            return False
        return True


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


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    name = db.Column(db.String(128), nullable=False, index=True)
    children = db.Column(db.JSON(), nullable=False)
    hub_id = db.Column(db.Integer, db.ForeignKey("vendor.id", ondelete="CASCADE"), nullable=False)
    responsible = db.Column(db.String(128), nullable=True)
    functional_budget = db.Column(db.String(128), nullable=True)
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
    code = db.Column(db.String(128), nullable=True)
    image = db.Column(db.String(128), nullable=True)
    income_statement = db.relationship("IncomeStatement")
    cashflow_statement = db.relationship("CashflowStatement")
    hub = db.relationship("Vendor", back_populates="categories")
    products = db.relationship(
        "Product",
        back_populates="category",
        cascade="all, delete",
        passive_deletes=True,
    )

    @property
    def short_name(self):
        return self.name.split("/")[-1]

    def __repr__(self):
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def to_dict(self):
        data = {
            "id": self.id,
            "name": self.name,
            "children": self.children,
            "responsible": self.responsible,
            "functional_budget": self.responsible,
            "income_id": self.income_id,
            "cashflow_id": self.cashflow_id,
            "code": self.code,
        }
        return data

    def __hash__(self):
        return self.id

    def __eq__(self, another):
        return isinstance(another, Category) and self.id == another.id


class AppSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    hub_id = db.Column(
        db.Integer,
        db.ForeignKey("vendor.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    notify_1C = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    email_1C = db.Column(db.String(128), nullable=True)
    order_id_bias = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    single_category_orders = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    alert = db.Column(db.String(512), nullable=True)
    hub = db.relationship("Vendor", back_populates="settings")


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


class Project(SearchableMixin, db.Model):

    __searchable__ = ["name", "uid", "tin", "phone", "email", "contact", "note", "legal_address", "shipping_address"]

    id = db.Column(db.Integer, primary_key=True, nullable=False)
    name = db.Column(db.String(128), nullable=False, index=True)
    hub_id = db.Column(db.Integer, db.ForeignKey("vendor.id", ondelete="CASCADE"), nullable=False)
    enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=expression.true(),
        index=True,
    )
    uid = db.Column(db.String(128), nullable=True)
    tin = db.Column(db.String(128), nullable=True)  # taxpayer identification number
    phone = db.Column(db.String(128), nullable=True)
    email = db.Column(db.String(128), nullable=True)
    contact = db.Column(db.String(128), nullable=True)
    note = db.Column(db.Text, nullable=True)
    legal_address = db.Column(db.Text, nullable=True)
    shipping_address = db.Column(db.Text, nullable=True)
    price_level = db.Column(
        db.Enum(ProjectPriceLevel),
        nullable=False,
        default=ProjectPriceLevel.online_store,
        server_default="online_store",
    )
    last_order_date = db.Column(db.Date, nullable=True)
    hub = db.relationship("Vendor", back_populates="projects")
    orders = db.relationship("Order", back_populates="project")

    order_limits = db.relationship(
        "OrderLimit",
        back_populates="project",
        cascade="all, delete",
        passive_deletes=True,
    )
    order_history = db.relationship(
        "ProjectOrderHistory",
        back_populates="project",
        cascade="all, delete",
        passive_deletes=True,
    )

    def __repr__(self):
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def to_dict(self):

        data = {
            "id": self.id,
            "name": self.name,
            "uid": self.uid,
            "tin": self.tin,
            "phone": self.phone,
            "email": self.email,
            "contact": self.contact,
            "note": self.note,
            "legal_address": self.legal_address,
            "shipping_address": self.shipping_address,
            "enabled": self.enabled,
            "price_level": self.price_level.name,
            "price_level_pretty": str(self.price_level),
            "price_level_id": int(self.price_level),
            "last_order_date": self.last_order_date.isoformat() if self.last_order_date is not None else "",
            "order_history": {
                "year": [h.year for h in self.order_history],
                "total": [h.total for h in self.order_history],
            },
        }
        return data


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


class UserCategory(db.Model):
    __tablename__ = "user_category"
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), primary_key=True)


class UserProject(db.Model):
    __tablename__ = "user_project"
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), primary_key=True)


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


class Product(SearchableMixin, db.Model):

    __searchable__ = ["name", "sku", "description"]

    id = db.Column(db.Integer, primary_key=True, nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendor.id", ondelete="CASCADE"), nullable=False)
    name = db.Column(db.String(128), nullable=False, index=True)
    sku = db.Column(db.String(128), nullable=False, index=True)
    price = db.Column(db.Float, nullable=False)  # online_price
    prices = db.Column(db.JSON(), nullable=True)  # the rest of the price levels
    image = db.Column(db.String(128), nullable=True)
    measurement = db.Column(db.String(128), nullable=True)
    cat_id = db.Column(db.Integer, db.ForeignKey("category.id", ondelete="CASCADE"), nullable=False)
    description = db.Column(db.String(512), nullable=True)
    options = db.Column(db.JSON())
    vendor = db.relationship("Vendor", back_populates="products")
    category = db.relationship("Category", back_populates="products")
    tags = db.relationship("ProductTag", backref="product", cascade="all, delete-orphan")

    def get_price(self, price_level: ProjectPriceLevel) -> float:
        if self.prices is not None and price_level.name in self.prices:
            try:
                level_price = float(self.prices[price_level.name])
            except ValueError:
                level_price = 0.0
            if level_price > 0.0:
                return level_price
        return self.price

    def to_dict(self):
        return {
            "id": self.id,
            "vendor": self.vendor.name,
            "image": self.image,
            "name": self.name,
            "options": self.options,
            "category": self.category.name,
            "description": self.description,
            "sku": self.sku,
            "price": self.price,
            "prices": self.prices,
            "measurement": self.measurement,
            "tags": [tag.tag for tag in self.tags],
        }


class ProductTag(db.Model):
    __tablename__ = "product_tag"
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), primary_key=True)
    tag = db.Column(db.String(128), nullable=False, index=True, primary_key=True)


class OAuth2Client(db.Model, OAuth2ClientMixin):
    __tablename__ = "oauth2_client"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"))
    user = db.relationship("User")


class OAuth2AuthorizationCode(db.Model, OAuth2AuthorizationCodeMixin):
    __tablename__ = "oauth2_code"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"))
    user = db.relationship("User")


class OAuth2Token(db.Model, OAuth2TokenMixin):
    __tablename__ = "oauth2_token"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"))
    user = db.relationship("User")


class ProjectOrderHistory(db.Model):
    __tablename__ = "project_order_history"
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id", ondelete="CASCADE"), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    active_months = db.Column(db.Integer, nullable=False)
    total = db.Column(db.Float, nullable=False)

    project = db.relationship("Project", back_populates="order_history")

    def to_dict(self):
        return {
            "id": self.id,
            "project": self.project.name,
            "year": self.year,
            "active_months": self.active_months,
            "total": self.total,
        }
