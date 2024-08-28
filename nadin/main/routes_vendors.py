from datetime import datetime, timezone

from flask import flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from nadin.extensions import db
from nadin.main.forms import AddVendorForm
from nadin.main.routes import bp
from nadin.models.hub import User, UserRoles, Vendor
from nadin.utils import flash_errors, role_forbidden, role_required

################################################################################
# Vendors page
################################################################################


@bp.route("/vendors/", methods=["GET", "POST"])
@login_required
@role_forbidden([UserRoles.default, UserRoles.vendor])
def show_vendors():
    store_form = AddVendorForm()
    stores = Vendor.query.filter(Vendor.hub_id == current_user.hub_id).all()
    if len(stores) == 0:
        flash("Ни один поставщик не зарегистрован в системе.")
    return render_template("vendors.html", store_form=store_form, stores=stores)


@bp.route("/vendors/add/", methods=["POST"])
@login_required
@role_required([UserRoles.admin])
def add_vendor():
    form = AddVendorForm()
    if form.validate_on_submit():
        store_name = form.name.data.strip()
        store_email = form.email.data.strip().lower()
        vendor_admin = User.query.filter_by(email=store_email).first()
        if vendor_admin:
            flash("Невозможно создать поставщика, так как электронный адрес занят.")
            return redirect(url_for("main.show_vendors"))
        vendor_admin = User(email=store_email, name=store_name, role=UserRoles.vendor, hub_id=current_user.hub_id)
        vendor_admin.set_password(form.password.data)
        vendor_admin.registered = datetime.now(tz=timezone.utc)
        db.session.add(vendor_admin)
        db.session.commit()
        store = Vendor(hub_id=current_user.hub_id, name=store_name, email=store_email)
        db.session.add(store)
        db.session.commit()
        flash("Магазин успешно добавлен.")
    else:
        flash_errors(form)
    return redirect(url_for("main.show_vendors"))


@bp.route("/vendors/remove/<int:store_id>")
@login_required
@role_required([UserRoles.admin])
def remove_vendor(store_id):
    store = Vendor.query.filter(Vendor.id == store_id, Vendor.hub_id == current_user.hub_id).first()
    if store is not None:
        vendor_admin = store.admin
        db.session.delete(store)
        if vendor_admin is not None:
            db.session.delete(vendor_admin)
        db.session.commit()
        flash("Поставщик успешно удалён.")
    else:
        flash("Этот поставщик не зарегистрован в системе.")
    return redirect(url_for("main.show_vendors"))


@bp.route("/vendors/activate/<int:store_id>")
@login_required
@role_required([UserRoles.admin])
def acrivate_vendor(store_id):
    store = Vendor.query.filter(Vendor.id == store_id, Vendor.hub_id == current_user.hub_id).first()
    if store is not None:
        store.enabled = not store.enabled
        db.session.commit()
        flash("Поставщик успешно изменён.")
    else:
        flash("Этот поставщик не зарегистрован в системе.")
    return redirect(url_for("main.show_vendors"))
