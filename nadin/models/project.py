import enum
import json

from sqlalchemy.sql import expression

from nadin.extensions import db
from nadin.models.search import SearchableMixin


class ProjectPriceLevel(enum.IntEnum):
    online_store = 0
    marketplace = 1
    small_wholesale = 2
    large_wholesale = 3
    distributor = 4
    exclusive = 5
    chains_vat = 6
    chains_vat_promo = 7
    chains_no_vat = 8
    chains_no_vat_promo = 9
    msrp_chains = 10
    msrp_retail = 11

    @staticmethod
    def pretty_names() -> dict[str, "ProjectPriceLevel"]:
        pretty = {
            "ИНТЕРНЕТ": ProjectPriceLevel.online_store,
            "МАРКЕТ": ProjectPriceLevel.marketplace,
            "МЕЛКИЙ ОПТ": ProjectPriceLevel.small_wholesale,
            "КРУПНЫЙ ОПТ": ProjectPriceLevel.large_wholesale,
            "ДИСТРИБЬЮТОР": ProjectPriceLevel.distributor,
            "ЭКСКЛЮЗИВ": ProjectPriceLevel.exclusive,
            "СЕТИ С НДС": ProjectPriceLevel.chains_vat,
            "СЕТИ С НДС ПРОМО": ProjectPriceLevel.chains_vat_promo,
            "СЕТИ БЕЗ НДС": ProjectPriceLevel.chains_no_vat,
            "СЕТИ БЕЗ НДС ПРОМО": ProjectPriceLevel.chains_no_vat_promo,
            "РРЦ СЕТИ": ProjectPriceLevel.msrp_chains,
            "РРЦ РОЗНИЦА": ProjectPriceLevel.msrp_retail,
        }
        return pretty

    @staticmethod
    def from_pretty(value: str) -> "ProjectPriceLevel":
        pretty = ProjectPriceLevel.pretty_names()
        return pretty.get(value.upper(), ProjectPriceLevel.online_store)

    def __str__(self):
        pretty = list(ProjectPriceLevel.pretty_names().keys())
        return pretty[self.value]


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
    discount = db.Column(db.Float, nullable=False, default=0.0, server_default="0.0")

    hub = db.relationship("Vendor", back_populates="projects")
    orders = db.relationship("Order")
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
            "discount": self.discount,
            "last_order_date": self.last_order_date.isoformat() if self.last_order_date is not None else "",
            "order_history": {
                "year": [h.year for h in self.order_history],
                "total": [h.total for h in self.order_history],
            },
        }
        return data


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
