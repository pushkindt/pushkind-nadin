import enum
import json
from hashlib import md5
from time import time
from typing import Optional

import jwt
import sqlalchemy as sa
from flask import current_app
from flask_login import UserMixin
from sqlalchemy.sql import expression
from werkzeug.security import check_password_hash, generate_password_hash

from nadin.extensions import db, login_manager
from nadin.models.project import Project, ProjectPriceLevel


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class UserRoles(enum.IntEnum):
    default = 0
    admin = 1
    initiative = 2
    validator = 3
    purchaser = 4
    supervisor = 5
    vendor = 6
    warehouse = 7
    delivery = 8
    finance = 9

    def __str__(self):
        pretty = [
            "Без роли",
            "Администратор",
            "Клиент",
            "Менеджер",
            "Оператор",
            "Руководитель",
            "Поставщик",
            "Склад",
            "Логистика",
            "Бухгалтерия",
        ]
        return pretty[self.value]


class Vendor(db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    hub_id = db.Column(db.Integer, db.ForeignKey("vendor.id", ondelete="CASCADE"), nullable=True)
    name = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(128), nullable=False, unique=True, index=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    users = db.relationship("User", back_populates="hub", cascade="all, delete", passive_deletes=True)
    categories = db.relationship("Category", back_populates="hub", cascade="all, delete", passive_deletes=True)
    settings = db.relationship("AppSettings", back_populates="hub", cascade="all, delete", passive_deletes=True)
    projects = db.relationship("Project", back_populates="hub", cascade="all, delete", passive_deletes=True)
    orders = db.relationship("Order", back_populates="hub", cascade="all, delete", passive_deletes=True)
    products = db.relationship("Product", back_populates="vendor", cascade="all, delete", passive_deletes=True)


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
    hub_id = db.Column(db.Integer, db.ForeignKey("vendor.id", ondelete="CASCADE"), nullable=True)
    email_new = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    email_modified = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    email_disapproved = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    email_approved = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    email_comment = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    last_seen = db.Column(db.DateTime, nullable=True)
    registered = db.Column(db.DateTime, nullable=True)
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

    @property
    def projects_list(self):
        return [p.id for p in self.projects]

    @property
    def hub_list(self):
        if self.role in [UserRoles.admin]:
            return Vendor.query.filter_by(hub_id=None).all()
        return [self.hub]

    def set_default_project(self, phone: str = None) -> Optional[Project]:
        """
        Sets the user's project to be the one with the same email or phone
        Should only be used for initiatives
        """
        if len(self.projects) > 0:
            return None
        if phone:
            check_condition = sa.or_(Project.email == self.email, Project.phone == phone)
        else:
            check_condition = Project.email == self.email
        project = Project.query.filter_by(hub_id=self.hub_id).filter(check_condition).first()
        if not project:
            project = Project(hub_id=self.hub_id, email=self.email, phone=phone, name=self.name, contact=self.name)
        self.projects = [project]
        return project

    @property
    def default_project(self) -> Optional[Project]:
        return self.projects[0] if len(self.projects) > 0 else None

    @property
    def price_level(self) -> ProjectPriceLevel:
        default_project = self.default_project
        return default_project.price_level if default_project else ProjectPriceLevel.online_store

    @property
    def discount(self) -> float:
        default_project = self.default_project
        return default_project.discount if default_project else 0.0

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
            "role": self.role.name,
            "role_id": int(self.role),
            "name": self.name if self.name is not None else "",
            "hub_id": self.hub_id,
            "email_new": self.email_new,
            "email_modified": self.email_modified,
            "email_disapproved": self.email_disapproved,
            "email_approved": self.email_approved,
            "email_comment": self.email_comment,
            "projects": [p.to_dict() for p in self.projects],
            "project_ids": self.projects_list,
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


class UserProject(db.Model):
    __tablename__ = "user_project"
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), primary_key=True)
