import io
import json
import re
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
from flask import current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from nadin.extensions import db
from nadin.main.forms import UploadImagesForm, UploadProductImageForm, UploadProductsForm
from nadin.main.routes import bp
from nadin.main.utils import role_forbidden
from nadin.models import Category, Product, ProductTag, UserRoles, Vendor
from nadin.utils import first

################################################################################
# Vendor products page
################################################################################


MANDATORY_COLUMNS = [
    "name",
    "sku",
    "price",
    "measurement",
    "category",
    "description",
]


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


def products_excel_to_df(df: pd.DataFrame, vendor_id: int, categories: "dict[str:int]") -> pd.DataFrame:
    df.columns = [clean_column_names(name) for name in df.columns]
    mandatory_columns_set = set(MANDATORY_COLUMNS)
    if not mandatory_columns_set.issubset(df.columns):
        missing_columns = mandatory_columns_set - df.columns
        raise KeyError(f"The following mandatory columns are missing: {missing_columns}")
    extra_columns = list(df.columns.difference(MANDATORY_COLUMNS))
    if "options" in extra_columns:
        extra_columns.remove("options")
    if "tags" in extra_columns:
        extra_columns.remove("tags")
    df["options"] = df[extra_columns].apply(product_columns_to_json, axis=1)
    df.drop(
        extra_columns,
        axis=1,
        inplace=True,
    )
    df["price"] = df["price"].apply(pd.to_numeric, errors="coerce")
    df["options"] = df["options"].replace("", None)

    df["vendor_id"] = vendor_id
    df["cat_id"] = df["category"].apply(lambda x: categories.get(x.lower()))
    df.drop(["category"], axis=1, inplace=True)
    df.dropna(subset=["cat_id", "name", "sku", "price", "measurement"], inplace=True)

    static_path = Path(f"nadin/static/upload/vendor{vendor_id}")
    static_path.mkdir(parents=True, exist_ok=True)
    image_list = {
        f.stem: url_for("static", filename=Path(*static_path.parts[2:]) / f.name)
        for f in static_path.glob("*")
        if not f.is_dir()
    }
    df["image"] = df["sku"].apply(image_list.get)

    string_columns = ["name", "sku", "measurement", "description"]
    for column in string_columns:
        df[column] = df[column].str.slice(0, 128) if column == "name" else df[column].str.slice(0, 512)
    return df


@bp.route("/products/", methods=["GET", "POST"])
@bp.route("/products/show", methods=["GET", "POST"])
@login_required
@role_forbidden([UserRoles.default, UserRoles.initiative, UserRoles.supervisor])
def ShowProducts():

    search_key = request.args.get("search", type=str)
    page = request.args.get("page", type=int, default=1)

    products_form = UploadProductsForm()
    images_form = UploadImagesForm()
    product_image_form = UploadProductImageForm()

    vendors = Vendor.query.filter_by(hub_id=current_user.hub_id)
    if current_user.role == UserRoles.vendor:
        vendors = vendors.filter_by(email=current_user.email)
    vendors = vendors.all()

    if not vendors:
        vendors.append(current_user.hub)

    vendor_id = request.args.get("vendor_id", type=int)
    if vendor_id is None or vendor_id not in (v.id for v in vendors):
        vendor_id = first(vendors).id

    category_id = request.args.get("category_id", type=int)
    categories = Category.query.filter_by(hub_id=current_user.hub_id)
    categories = categories.order_by(Category.name).all()

    if search_key:
        products, total = Product.search(search_key, page, current_app.config["MAX_PER_PAGE"])
    else:
        products = Product.query

    products = products.filter_by(vendor_id=vendor_id)
    if category_id:
        products = products.filter_by(cat_id=category_id)

    if search_key:
        products = db.paginate(products, page=1, max_per_page=current_app.config["MAX_PER_PAGE"])
        products.total = total
        products.page = page
    else:
        products = products.order_by(Product.name)
        products = db.paginate(products, page=page, max_per_page=current_app.config["MAX_PER_PAGE"])

    return render_template(
        "products.html",
        vendors=vendors,
        vendor_id=vendor_id,
        products=products,
        categories=categories,
        products_form=products_form,
        images_form=images_form,
        product_image_form=product_image_form,
        category_id=category_id,
        search_key=search_key,
    )


@bp.route("/products/upload", methods=["GET", "POST"])
@login_required
@role_forbidden([UserRoles.default, UserRoles.initiative, UserRoles.supervisor])
def UploadProducts():
    form = UploadProductsForm()
    vendor = _get_vendor(request.args.get("vendor_id", type=int))
    if vendor is None:
        flash("Такой поставщик не найден.")
        return redirect(url_for("main.ShowProducts"))

    category_id = request.args.get("category_id", type=int)

    if form.validate_on_submit():
        categories = Category.query.filter_by(hub_id=current_user.hub_id).all()
        categories = {c.name.lower(): c.id for c in categories}
        try:
            df = pd.read_excel(form.products.data, engine="openpyxl", dtype=str, keep_default_na=False)
        except ValueError as e:
            flash(str(e), category="error")
            return redirect(url_for("main.ShowProducts", vendor_id=vendor.id))
        try:
            df = products_excel_to_df(df, vendor.id, categories)
        except ValueError as e:
            flash(str(e), category="error")
            return redirect(url_for("main.ShowProducts", vendor_id=vendor.id))
        skus = df.sku.values.tolist()
        Product.query.filter_by(vendor_id=vendor.id).filter(Product.sku.in_(skus)).delete()
        db.session.commit()
        df_tags = df[["sku", "tags"]].dropna(subset=["tags"])
        df.drop(["tags"], axis=1, inplace=True)
        df.to_sql(name="product", con=db.engine, if_exists="append", index=False)
        db.session.commit()
        df_tags = process_product_tags(df_tags, vendor.id)
        ProductTag.query.filter(ProductTag.product_id.in_(df_tags["product_id"].to_list())).delete()
        db.session.commit()
        df_tags.to_sql(name="product_tag", con=db.engine, if_exists="append", index=False)
        db.session.commit()
        flash("Список товаров успешно обновлён.")
    else:
        for error in form.products.errors:
            flash(error)
    return redirect(url_for("main.ShowProducts", vendor_id=vendor.id, category_id=category_id))


@bp.route("/products/upload/images", methods=["GET", "POST"])
@login_required
@role_forbidden([UserRoles.default, UserRoles.initiative, UserRoles.supervisor])
def UploadImages():
    form = UploadImagesForm()
    vendor = _get_vendor(request.args.get("vendor_id", type=int))
    if vendor is None:
        flash("Такой поставщик не найден.")
        return redirect(url_for("main.ShowProducts"))
    if form.validate_on_submit():
        products = Product.query.filter_by(vendor_id=vendor.id).all()
        products = [p.sku for p in products]
        with ZipFile(form.images.data, "r") as zip_file:
            for zip_info in zip_file.infolist():
                if zip_info.is_dir() or zip_info.file_size > current_app.config["MAX_ZIP_FILE_SIZE"]:
                    continue
                file_name = Path(zip_info.filename)
                sku = file_name.stem
                if sku not in products:
                    continue
                zip_info.filename = sku + file_name.suffix
                static_path = Path(f"nadin/static/upload/vendor{vendor.id}")
                static_path.mkdir(parents=True, exist_ok=True)
                zip_file.extract(zip_info, static_path)
                static_path = static_path / zip_info.filename
                db.session.query(Product).filter_by(vendor_id=vendor.id, sku=sku).update(
                    {"image": url_for("static", filename=Path(*static_path.parts[2:]))}
                )
                db.session.commit()
        flash("Изображения товаров успешно загружены.")
    else:
        for error in form.images.errors:
            flash(error)
    return redirect(url_for("main.ShowProducts", vendor_id=vendor.id))


@bp.route("/products/remove", methods=["POST"])
@login_required
@role_forbidden([UserRoles.default, UserRoles.initiative, UserRoles.supervisor])
def remove_products():
    vendor = _get_vendor(request.args.get("vendor_id", type=int))
    if vendor is None:
        flash("Такой поставщик не найден.")
        return redirect(url_for("main.ShowProducts"))
    products = Product.query.filter_by(vendor_id=vendor.id).all()
    ProductTag.query.filter(ProductTag.product_id.in_([p.id for p in products])).delete()
    Product.query.filter_by(vendor_id=vendor.id).delete()
    db.session.commit()
    flash("Список товаров успешно очищен.")
    return redirect(url_for("main.ShowProducts", vendor_id=vendor.id))


@bp.route("/products/download", methods=["GET", "POST"])
@login_required
@role_forbidden([UserRoles.default, UserRoles.initiative, UserRoles.supervisor])
def DownloadProducts():
    vendor = _get_vendor(request.args.get("vendor_id", type=int))
    if vendor is None:
        flash("Такой поставщик не найден.")
        return redirect(url_for("main.ShowProducts"))

    products = Product.query.filter_by(vendor_id=vendor.id).all()
    products = [p.to_dict() for p in products]
    df = pd.json_normalize(products)
    if len(df.index) > 0:
        df.drop(["id", "image", "vendor"], axis="columns", inplace=True, errors="ignore")
        df.columns = [col.replace("options.", "") for col in df.columns]
        extra_columns = list(df.columns.difference(MANDATORY_COLUMNS))
        for col in extra_columns:
            df[col] = df[col].apply(
                lambda values: (
                    ", ".join(re.sub(r"\"|'", "", str(v)) for v in values) if isinstance(values, list) else None
                )
            )
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


@bp.route("/products/<int:product_id>/upload/image", methods=["GET", "POST"])
@login_required
@role_forbidden([UserRoles.default, UserRoles.initiative, UserRoles.supervisor])
def UploadProductImage(product_id):
    vendor = _get_vendor(request.args.get("vendor_id", type=int))
    if vendor is None:
        flash("Такой поставщик не найден.")
        return redirect(url_for("main.ShowProducts"))

    product = Product.query.filter_by(id=product_id, vendor_id=vendor.id).first()
    if product is None:
        flash("Такой товар не найден.")
        return redirect(url_for("main.ShowProducts"))

    form = UploadProductImageForm()
    if form.validate_on_submit():
        file_data = form.image.data
        file_name = Path(file_data.filename)
        file_name = Path(str(product.sku) + file_name.suffix)
        static_path = Path(f"nadin/static/upload/vendor{vendor.id}")
        static_path.mkdir(parents=True, exist_ok=True)
        full_path = static_path / file_name
        file_data.save(full_path)
        product.image = url_for("static", filename=Path(*full_path.parts[2:]))
        db.session.commit()
        flash("Изображение товара успешно загружено.")
    else:
        for error in form.image.errors:
            flash(error)
    return redirect(url_for("main.ShowProducts", vendor_id=vendor.id))
