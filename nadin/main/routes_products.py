import io
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
from nadin.products import process_product_tags, process_products
from nadin.utils import flash_errors, role_forbidden

################################################################################
# Vendor products page
################################################################################


def _get_vendor(vendor_id: int) -> Vendor:
    if current_user.role == UserRoles.vendor:
        return Vendor.query.filter_by(email=current_user.email).first()
    vendor = Vendor.query.filter_by(id=vendor_id).first()
    if not vendor:
        vendor = Vendor.query.filter_by().first()
    return vendor


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

    vendors = Vendor.query.filter_by()
    if current_user.role == UserRoles.vendor:
        vendors = vendors.filter_by(email=current_user.email)
    vendors = vendors.all()

    vendor_id = request.args.get("vendor_id", type=int)
    vendor_id = _get_vendor(vendor_id=vendor_id).id

    category_id = request.args.get("category_id", type=int)
    categories = Category.query
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
        categories = Category.query.all()
        categories = {c.name.lower(): c.id for c in categories}
        try:
            new_products = pd.read_excel(form.products.data, engine="openpyxl", dtype=str, keep_default_na=False)
        except ValueError as e:
            flash(str(e), category="error")
            return redirect(url_for("main.show_products", vendor_id=vendor.id))

        if "sku" not in new_products.columns:
            flash("Не найден столбец sku.", category="error")
            return redirect(url_for("main.show_products", vendor_id=vendor.id))

        if "tags" in new_products.columns:
            df_tags = new_products[["sku", "tags"]]
            new_products.drop(["tags"], axis=1, inplace=True)
        else:
            df_tags = None

        existing_products = pd.read_sql(sql=f"SELECT * FROM PRODUCT WHERE VENDOR_ID = {vendor.id}", con=db.engine)

        new_products = process_products(new_products, existing_products, categories)
        new_products["vendor_id"] = vendor.id

        Product.query.filter_by(vendor_id=vendor.id).delete()
        db.session.commit()
        new_products.to_sql(name="product", con=db.engine, if_exists="append", index=False)
        db.session.commit()

        if df_tags is not None:
            existing_products = Product.query.filter_by(vendor_id=vendor.id).all()
            product_ids = {p.sku: p.id for p in existing_products}
            df_tags = process_product_tags(product_ids, df_tags)
            ProductTag.query.filter(ProductTag.product_id.in_(df_tags["product_id"].to_list())).delete()
            db.session.commit()
            df_tags.to_sql(name="product_tag", con=db.engine, if_exists="append", index=False)
            db.session.commit()

        run_async(Product.reindex)
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
