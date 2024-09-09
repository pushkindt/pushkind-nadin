import json

from nadin.extensions import db
from nadin.models.project import ProjectPriceLevel
from nadin.models.search import SearchableMixin


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


class Product(SearchableMixin, db.Model):

    __searchable__ = ["name", "sku", "description"]

    id = db.Column(db.Integer, primary_key=True, nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendor.id", ondelete="CASCADE"), nullable=False)
    name = db.Column(db.String(128), nullable=False, index=True)
    sku = db.Column(db.String(128), nullable=False, index=True)
    price = db.Column(db.Float, nullable=False)  # online_price
    prices = db.Column(db.JSON(), nullable=True)  # the rest of the price levels
    image = db.Column(db.String(128), nullable=True)
    images = db.Column(db.JSON(), nullable=True)
    measurement = db.Column(db.String(128), nullable=True)
    cat_id = db.Column(db.Integer, db.ForeignKey("category.id", ondelete="CASCADE"), nullable=False)
    description = db.Column(db.String(512), nullable=True)
    options = db.Column(db.JSON())
    vendor = db.relationship("Vendor", back_populates="products")
    category = db.relationship("Category", back_populates="products")
    tags = db.relationship("ProductTag", backref="product", cascade="all, delete-orphan")

    def tag_list(self):
        return [tag.tag for tag in self.tags]

    def images_list(self):
        return [image for image in (self.images or []) if image]

    def get_price(self, price_level: ProjectPriceLevel, discount: float = 0.0) -> float:
        if self.prices is not None and price_level.name in self.prices:
            try:
                price = float(self.prices[price_level.name])
            except ValueError:
                price = self.price
        else:
            price = self.price
        return max(price * (1 - discount / 100), 0.0)

    @property
    def get_prices(self):
        prices = self.prices if self.prices is not None else {}
        prices[ProjectPriceLevel.online_store.name] = self.price
        return prices

    def to_dict(self):
        return {
            "id": self.id,
            "vendor": self.vendor.name,
            "image": self.image,
            "name": self.name,
            "options": self.options,
            "cat_id": self.cat_id,
            "category": self.category.name,
            "description": self.description,
            "sku": self.sku,
            "price": self.price,
            "prices": self.get_prices,
            "measurement": self.measurement,
            "tags": self.tag_list(),
            "images": self.images,
        }


class ProductTag(db.Model):
    __tablename__ = "product_tag"
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), primary_key=True)
    tag = db.Column(db.String(128), nullable=False, index=True, primary_key=True)
