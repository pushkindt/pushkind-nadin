import io
import json
import re
from pathlib import Path

import pandas as pd
from flask import current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm.attributes import flag_modified

from nadin.email import run_async
from nadin.extensions import db
from nadin.main.forms import EditProductForm, UploadImagesForm, UploadProductsForm
from nadin.main.routes import bp
from nadin.models.hub import UserRoles, Vendor
from nadin.models.product import Category, Product, ProductTag
from nadin.models.project import ProjectPriceLevel
from nadin.utils import flash_errors, role_forbidden

################################################################################
# Vendor products page
################################################################################


INDEX_COLUMNS = ["sku"]
MANDATORY_COLUMNS = INDEX_COLUMNS + [
    "name",
    "price",
    "measurement",
    "category",
    "description",
]
MANDATORY_COLUMNS2 = INDEX_COLUMNS + ["name", "price", "cat_id", "description", "vendor_id"]
ADDITIONAL_COLUMNS = [
    "image",
    "images",
    "tags",
]
PRICE_COLUMNS = [
    "prices_online_store",
    "prices_marketplace",
    "prices_small_wholesale",
    "prices_large_wholesale",
    "prices_distributor",
    "prices_exclusive",
    "prices_chains_vat",
    "prices_chains_vat_promo",
    "prices_chains_no_vat",
    "prices_chains_no_vat_promo",
    "prices_msrp_chains",
    "prices_msrp_retail",
]
FULL_SET_COLLUMNS = MANDATORY_COLUMNS + PRICE_COLUMNS + ADDITIONAL_COLUMNS


def _get_vendor(vendor_id: int) -> Vendor:
    if current_user.role == UserRoles.vendor:
        return Vendor.query.filter_by(email=current_user.email).first()
    vendor = Vendor.query.filter_by(id=vendor_id).first()
    if not vendor:
        vendor = Vendor.query.filter_by(id=current_user.hub_id).first()
    return vendor


def product_columns_to_json(row: pd.Series) -> str:
    def parse_column(value: str) -> "list[str]":
        return sorted(list({s.strip() for s in str(value).split(",")})) if value else None

    result = {k: parse_column(v) for k, v in row.items() if v}
    return json.dumps(result, ensure_ascii=False) if result else ""


def price_columns_to_json(row: pd.Series) -> str:
    result = {}
    for col in PRICE_COLUMNS:
        price_col = "_".join(col.split("_")[1:])
        if col not in row:
            continue
        result[price_col] = float(row[col])
    return json.dumps(result)


def process_product_tags(df_tags: pd.DataFrame, vendor_id: int) -> pd.DataFrame:
    product_ids = {p.sku: p.id for p in Product.query.filter_by(vendor_id=vendor_id).all()}
    df_tags["product_id"] = df_tags["sku"].apply(product_ids.get)
    df_tags.drop(["sku"], axis=1, inplace=True)
    df_tags["tags"] = df_tags["tags"].str.split(",")
    df_tags = df_tags.explode("tags")
    df_tags = df_tags.drop_duplicates()
    df_tags.rename(columns={"tags": "tag"}, inplace=True)
    df_tags["tag"] = df_tags["tag"].apply(lambda x: x.lower().strip()[:128])
    return df_tags


def clean_column_names(name: str) -> str:
    return re.sub(r"[^\w]+", "_", name.lower())


def products_excel_to_df(
    df: pd.DataFrame, vendor_id: int, categories: "dict[str:int]"
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df.columns = [clean_column_names(name) for name in df.columns]
    mandatory_columns_set = set(INDEX_COLUMNS)
    if not mandatory_columns_set.issubset(df.columns):
        missing_columns = mandatory_columns_set - set(df.columns)
        raise KeyError(f"The following mandatory columns are missing: {missing_columns}")
    extra_columns = list(df.columns.difference(FULL_SET_COLLUMNS))

    df["options"] = df[extra_columns].apply(product_columns_to_json, axis=1)
    df.drop(
        extra_columns,
        axis=1,
        inplace=True,
    )
    df["options"] = df["options"].replace("", None)

    if "price" in df.columns:
        df["price"] = df["price"].apply(pd.to_numeric, errors="coerce")

    df["vendor_id"] = vendor_id

    if "images" in df.columns:
        df["images"] = df["images"].apply(lambda x: json.dumps(str(x).split(",")) if x else None)

    if "category" in df.columns:
        df["cat_id"] = df["category"].str.lower().map(categories)
        df.drop(["category"], axis=1, inplace=True)
    else:
        df.drop("cat_id", errors="ignore")

    for col in ["cat_id", "name", "sku", "price", "measurement"]:
        if col not in df.columns:
            continue
        df.dropna(subset=col, inplace=True)

    if any(col in df.columns for col in PRICE_COLUMNS):
        df["prices"] = df.apply(price_columns_to_json, axis=1)
        df.drop(PRICE_COLUMNS, axis=1, inplace=True, errors="ignore")

    string_columns = ["name", "sku", "measurement", "description"]
    for column in string_columns:
        if column not in df.columns:
            continue
        df[column] = df[column].str.slice(0, 128) if column == "name" else df[column].str.slice(0, 512)

    if "tags" in df.columns:
        df_tags = df[["sku", "tags"]].dropna(subset=["tags"])
        df.drop(["tags"], axis=1, inplace=True)
    else:
        df_tags = pd.DataFrame(columns=["sku", "tags"])

    existing_products = pd.read_sql(
        sql=f"SELECT * FROM PRODUCT WHERE VENDOR_ID = {vendor_id}", con=db.engine, index_col="sku"
    )
    if not existing_products.empty:
        df.drop_duplicates(subset=["sku"], inplace=True)
        df.set_index("sku", inplace=True)
        existing_products.update(df)
        existing_products.reset_index(inplace=True)
        existing_products.dropna(subset=["cat_id", "name", "sku", "price", "measurement"], inplace=True)
        return existing_products, df_tags
    else:
        mandatory_columns_set = set(MANDATORY_COLUMNS2)
        if not mandatory_columns_set.issubset(df.columns):
            missing_columns = mandatory_columns_set - set(df.columns)
            raise KeyError(f"The following mandatory columns are missing: {missing_columns}")
        return df, df_tags


@bp.route("/products/", methods=["GET", "POST"])
@bp.route("/products/show", methods=["GET", "POST"])
@login_required
@role_forbidden([UserRoles.default, UserRoles.initiative, UserRoles.supervisor])
def show_products():

    search_key = request.args.get("q", type=str)
    page = request.args.get("page", type=int, default=1)

    products_form = UploadProductsForm()
    images_form = UploadImagesForm()
    edit_product_form = EditProductForm()

    vendors = Vendor.query.filter_by(hub_id=current_user.hub_id)
    if current_user.role == UserRoles.vendor:
        vendors = vendors.filter_by(email=current_user.email)
    vendors = vendors.all()

    vendors.append(current_user.hub)

    vendor_id = request.args.get("vendor_id", type=int)
    vendor_id = _get_vendor(vendor_id=vendor_id).id

    category_id = request.args.get("category_id", type=int)
    categories = Category.query.filter_by(hub_id=current_user.hub_id)
    categories = categories.order_by(Category.name).all()

    if search_key:
        products, total = Product.search(search_key, page, current_app.config["MAX_PER_PAGE"])
    else:
        products = Product.query

    products = products.filter_by(vendor_id=vendor_id)
    if category_id:
        category = Category.query.get_or_404(category_id)
        products = products.join(Category, onclause=Category.id == Product.cat_id).filter(
            Category.name.startswith(category.name)
        )

    if search_key:
        products = db.paginate(products, page=1, max_per_page=current_app.config["MAX_PER_PAGE"])
        products.total = total
        products.page = page
    else:
        products = products.order_by(Product.id)
        products = db.paginate(products, page=page, max_per_page=current_app.config["MAX_PER_PAGE"])

    return render_template(
        "main/products/products.html",
        vendors=vendors,
        vendor_id=vendor_id,
        products=products,
        categories=categories,
        products_form=products_form,
        images_form=images_form,
        edit_product_form=edit_product_form,
        category_id=category_id,
        search_key=search_key,
    )


@bp.route("/products/upload", methods=["GET", "POST"])
@login_required
@role_forbidden([UserRoles.default, UserRoles.initiative, UserRoles.supervisor])
def upload_products():
    form = UploadProductsForm()
    vendor = _get_vendor(request.args.get("vendor_id", type=int))
    if vendor is None:
        flash("Такой поставщик не найден.")
        return redirect(url_for("main.show_products"))

    if form.validate_on_submit():
        categories = Category.query.filter_by(hub_id=current_user.hub_id).all()
        categories = {c.name.lower(): c.id for c in categories}
        try:
            new_products = pd.read_excel(form.products.data, engine="openpyxl", dtype=str, keep_default_na=False)
        except ValueError as e:
            flash(str(e), category="error")
            return redirect(url_for("main.show_products", vendor_id=vendor.id))

        try:
            new_products, df_tags = products_excel_to_df(new_products, vendor.id, categories)
        except (ValueError, KeyError) as e:
            flash(str(e), category="error")
            return redirect(url_for("main.show_products", vendor_id=vendor.id))

        Product.query.filter_by(vendor_id=vendor.id).delete()
        db.session.commit()
        new_products.to_sql(name="product", con=db.engine, if_exists="append", index=False)
        db.session.commit()

        df_tags = process_product_tags(df_tags, vendor.id)
        ProductTag.query.filter(ProductTag.product_id.in_(df_tags["product_id"].to_list())).delete()
        db.session.commit()
        df_tags.to_sql(name="product_tag", con=db.engine, if_exists="append", index=False)
        db.session.commit()
        run_async(current_app._get_current_object(), Product.reindex)
        flash("Список товаров успешно обновлён.")
    else:
        flash_errors(form)
    return redirect(url_for("main.show_products", vendor_id=vendor.id))


@bp.route("/products/remove", methods=["POST"])
@login_required
@role_forbidden([UserRoles.default, UserRoles.initiative, UserRoles.supervisor])
def remove_products():
    vendor = _get_vendor(request.args.get("vendor_id", type=int))
    if vendor is None:
        flash("Такой поставщик не найден.")
        return redirect(url_for("main.show_products"))
    products = Product.query.filter_by(vendor_id=vendor.id).all()
    ProductTag.query.filter(ProductTag.product_id.in_([p.id for p in products])).delete()
    Product.query.filter_by(vendor_id=vendor.id).delete()
    db.session.commit()
    flash("Список товаров успешно очищен.")
    return redirect(url_for("main.show_products", vendor_id=vendor.id))


@bp.route("/products/download", methods=["GET"])
@login_required
@role_forbidden([UserRoles.default, UserRoles.initiative, UserRoles.supervisor])
def download_products():
    vendor = _get_vendor(request.args.get("vendor_id", type=int))
    if vendor is None:
        flash("Такой поставщик не найден.")
        return redirect(url_for("main.show_products"))

    products = Product.query.filter_by(vendor_id=vendor.id).all()
    products = [p.to_dict() for p in products]
    df = pd.json_normalize(products)
    if len(df.index) > 0:
        df.drop(["id", "vendor", "options", "cat_id"], axis="columns", inplace=True, errors="ignore")
        for col in df.columns:
            if not any(col.startswith(column_with_lists) for column_with_lists in ["tags", "options", "images"]):
                continue
            df[col] = df[col].apply(
                lambda values: (
                    ", ".join(re.sub(r"\"|'", "", str(v)) for v in values) if isinstance(values, list) else None
                )
            )
        df.columns = [col.replace("options.", "") for col in df.columns]
    else:
        df[MANDATORY_COLUMNS] = None
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        download_name="products.xlsx",
    )


@bp.route("/products/<int:product_id>/edit", methods=["POST"])
@login_required
@role_forbidden([UserRoles.default, UserRoles.initiative, UserRoles.supervisor])
def edit_product(product_id):
    vendor = _get_vendor(request.args.get("vendor_id", type=int))
    if vendor is None:
        flash("Такой поставщик не найден.")
        return redirect(url_for("main.show_products"))

    product = Product.query.filter_by(id=product_id, vendor_id=vendor.id).first()
    if product is None:
        flash("Такой товар не найден.")
        return redirect(url_for("main.show_products"))

    form = EditProductForm()
    if form.validate_on_submit():

        if form.delete.data:
            db.session.delete(product)
            db.session.commit()
            flash("Товар успешно удалён.")
            return redirect(url_for("main.show_products", vendor_id=vendor.id))

        product.name = form.name.data.strip()[:128]
        product.sku = form.sku.data.strip()[:128]
        price_level = ProjectPriceLevel[form.price_level.data]
        if price_level == ProjectPriceLevel.online_store:
            product.price = form.price.data
        if product.prices is None:
            product.prices = {}
        product.prices[price_level.name] = float(form.price.data)
        flag_modified(product, "prices")
        product.measurement = form.measurement.data.strip()[:128]
        product.description = form.description.data.strip()[:512]
        if form.images.data:
            product.images = [image.strip() for image in form.images.data.split()]

        if form.image.data:
            file_data = form.image.data
            file_name = Path(file_data.filename)
            file_name = Path(str(product.sku) + file_name.suffix)
            static_path = Path(current_app.config["STATIC_UPLOAD_PATH"])
            static_path = static_path / f"vendor{vendor.id}"
            static_path.mkdir(parents=True, exist_ok=True)
            full_path = static_path / file_name
            file_data.save(full_path)
            product.image = url_for("static", filename=Path(*full_path.parts[2:]))

        if form.tags.data:
            ProductTag.query.filter_by(product_id=product.id).delete()
            tags = [ProductTag(tag=tag.strip(), product_id=product.id) for tag in form.tags.data.split(" ")]
            for tag in tags:
                db.session.add(tag)
            product.tags = tags

        db.session.commit()
        flash("Товар успешно сохранён.")
    else:
        flash_errors(form)
    return redirect(url_for("main.show_products", vendor_id=vendor.id))
