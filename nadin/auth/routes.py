from datetime import datetime, timezone
from urllib.parse import urlparse as url_parse

import sqlalchemy as sa
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from nadin.auth.email import send_password_reset_email, send_user_registered_email
from nadin.auth.forms import LoginForm, RegistrationForm, ResetPasswordForm, ResetPasswordRequestForm
from nadin.extensions import db, oauth_ext
from nadin.models.hub import User, UserRoles, Vendor
from nadin.models.oauth import OAuth2Client
from nadin.utils import flash_errors, get_escaped_url_parameter

bp = Blueprint("auth", __name__)


def update_user_hub_from_url(user: User, escaped_url: str) -> bool:
    if not escaped_url:
        return False
    client_id = get_escaped_url_parameter(escaped_url, "client_id")
    client = OAuth2Client.query.filter_by(client_id=client_id).first()
    if client:
        user.hub_id = client.hub_id
        return True
    return False


def update_initiative_hub_from_url(user: User, escaped_url: str) -> bool:
    user.role = UserRoles.initiative
    return update_user_hub_from_url(user, escaped_url)


@bp.route("/login_local/", methods=["GET", "POST"])
def login():

    next_page = request.args.get("next")
    if not next_page or url_parse(next_page).netloc != "":
        next_page = url_for("main.ShowIndex")

    if current_user.is_authenticated:
        return redirect(next_page)
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.lower()
        user = User.query.filter_by(email=email).first()
        if user is None or not user.check_password(form.password.data):
            flash("Некорректный логин или пароль.")
            return redirect(url_for("auth.login"))
        update_user_hub_from_url(user, next_page)
        user.set_initiative_project()
        db.session.commit()

        login_user(user, remember=form.remember_me.data)
        current_app.logger.info("%s logged", user.email)
        return redirect(next_page)

    flash_errors(form)
    return render_template("auth/login.html", form=form, next_page=next_page)


@bp.route("/login/<token>/", methods=["GET"])
def login_token(token):
    next_page = request.args.get("next")
    if not next_page or url_parse(next_page).netloc != "":
        next_page = url_for("main.ShowIndex")

    if not current_user.is_authenticated:

        user = User.verify_jwt_token(token)
        if not user:
            flash("Некорректный токен авторизации.")
            return redirect(url_for("auth.login"))

        login_user(user)
        current_app.logger.info("%s logged", user.email)

    return redirect(next_page)


@bp.route("/signup/", methods=["GET", "POST"])
def signup():
    next_page = request.args.get("next")
    if not next_page or url_parse(next_page).netloc != "":
        next_page = url_for("main.ShowIndex")

    if current_user.is_authenticated and current_user.role != UserRoles.admin:
        return redirect(next_page)

    form = RegistrationForm()
    if form.validate_on_submit():
        email = form.email.data.lower()
        user = User(email=email)
        user.set_password(form.password.data)
        user.registered = datetime.now(tz=timezone.utc)
        db.session.add(user)
        db.session.commit()

        if update_initiative_hub_from_url(user, next_page):
            user.set_initiative_project()
            db.session.commit()

        send_user_registered_email(user)
        flash("Теперь пользователь может войти.")
        current_app.logger.info("%s registered", user.email)
        if current_user.is_authenticated and current_user.role == UserRoles.admin:
            return redirect(url_for("main.show_settings"))
        return redirect(url_for("auth.login", next=next_page))

    flash_errors(form)
    return render_template("auth/register.html", form=form)


@bp.route("/logout/", methods=["POST"])
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@bp.route("/request/", methods=["GET", "POST"])
def request_password_reset():
    if current_user.is_authenticated:
        return redirect(url_for("main.ShowIndex"))
    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        email = form.email.data.lower()
        user = User.query.filter_by(email=email).first()
        if user:
            send_password_reset_email(user)
            flash("На вашу электронную почту отправлен запрос на сброс пароля.")
            return redirect(url_for("auth.login"))
        flash("Такой пользователь не обнаружен.")
    else:
        flash_errors(form)
    return render_template("auth/request.html", form=form)


@bp.route("/reset/<token>", methods=["GET", "POST"])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for("main.ShowIndex"))
    user = User.verify_jwt_token(token)
    if not user:
        return redirect(url_for("auth.login"))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash("Ваш пароль был изменён.")
        return redirect(url_for("auth.login"))

    flash_errors(form)
    return render_template("auth/reset.html", form=form)


@bp.route("/login/", defaults={"authenticator": "yandex"})
@bp.route("/login/<authenticator>")
def login_oauth(authenticator: str):

    next_page = request.args.get("next")
    if not next_page or url_parse(next_page).netloc != "":
        next_page = url_for("main.ShowIndex")

    if current_user.is_authenticated:
        return redirect(next_page)
    oauth_client = getattr(oauth_ext, authenticator)
    if not oauth_client:
        abort(404)
    redirect_uri = url_for("auth.callback_oauth", authenticator=authenticator, next=next_page, _external=True)
    return oauth_client.authorize_redirect(redirect_uri)


@bp.route("/callback/<authenticator>")
def callback_oauth(authenticator: str):

    next_page = request.args.get("next")
    if not next_page or url_parse(next_page).netloc != "":
        next_page = url_for("main.ShowIndex")

    if current_user.is_authenticated:
        return redirect(next_page)

    oauth_client = getattr(oauth_ext, authenticator)
    if not oauth_client:
        abort(404)
    try:
        token = oauth_client.authorize_access_token()
    except Exception:
        flash("Не удалось авторизоваться. Попробуйте позже.")
        return redirect(url_for("auth.login"))

    user_info = oauth_client.userinfo(token=token)
    profile = oauth_client.map_profile(user_info)
    if not profile["email"]:
        abort(400)
    user = User.query.filter_by(email=profile["email"]).first()
    if not user:
        user = User(email=profile["email"], password="")

        if not update_initiative_hub_from_url(user, next_page):
            user.hub = Vendor.query.filter(Vendor.hub_id == sa.null()).first()

        db.session.add(user)
    else:
        update_user_hub_from_url(user, next_page)
    user.name = profile["name"]
    user.set_initiative_project(phone=profile["phone_number"])
    db.session.commit()

    login_user(user, remember=True)
    current_app.logger.info("%s logged", user.email)
    return redirect(next_page)
