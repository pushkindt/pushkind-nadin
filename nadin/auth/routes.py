from datetime import datetime, timezone
from urllib.parse import urlparse as url_parse

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from nadin.auth.email import send_password_reset_email, send_user_registered_email
from nadin.auth.forms import LoginForm, RegistrationForm, ResetPasswordForm, ResetPasswordRequestForm
from nadin.extensions import db
from nadin.models.hub import User, UserRoles, Vendor
from nadin.utils import flash_errors

bp = Blueprint("auth", __name__)


@bp.route("/login/", methods=["GET", "POST"])
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
        if user.role == UserRoles.initiative:
            user.set_default_project()
            db.session.commit()
        login_user(user, remember=form.remember_me.data)
        current_app.logger.info("%s logged", user.email)
        return redirect(next_page)

    flash_errors(form)
    return render_template("auth/login.html", form=form)


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
    if current_user.is_authenticated and current_user.role != UserRoles.admin:
        return redirect(url_for("main.ShowIndex"))
    form = RegistrationForm()
    if form.validate_on_submit():
        email = form.email.data.lower()
        user = User(email=email)
        user.set_password(form.password.data)
        user.registered = datetime.now(tz=timezone.utc)
        db.session.add(user)
        db.session.commit()
        send_user_registered_email(user)
        flash("Теперь пользователь может войти.")
        current_app.logger.info("%s registered", user.email)
        if current_user.is_authenticated and current_user.role == UserRoles.admin:
            return redirect(url_for("main.ShowSettings"))
        return redirect(url_for("auth.login"))

    flash_errors(form)
    return render_template("auth/register.html", form=form)


@bp.route("/logout/")
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


@bp.route("/login/<authenticator>")
def login_oauth(authenticator: str):
    if current_user.is_authenticated:
        return redirect(url_for("main.ShowIndex"))
    oauth_ext = current_app.extensions["authlib.integrations.flask_client"]
    oauth_client = oauth_ext.create_client(authenticator)
    if not oauth_client:
        abort(404)
    redirect_uri = url_for("auth.callback_oauth", authenticator=authenticator, _external=True)
    return oauth_client.authorize_redirect(redirect_uri)


@bp.route("/callback/<authenticator>")
def callback_oauth(authenticator: str):
    if current_user.is_authenticated:
        return redirect(url_for("main.ShowIndex"))
    oauth_ext = current_app.extensions["authlib.integrations.flask_client"]
    oauth_client = oauth_ext.create_client(authenticator)
    if not oauth_client:
        abort(404)
    try:
        token = oauth_client.authorize_access_token()
    except:
        flash("Не удалось авторизоваться. Попробуйте позже.")
        return redirect(url_for("auth.login"))
    user_info = oauth_client.userinfo(token=token)
    profile = oauth_client.map_profile(user_info)
    if not profile["email"]:
        abort(400)
    user = User.query.filter_by(email=profile["email"]).first()
    if not user:
        user = User(email=profile["email"], role=UserRoles.initiative, password="")
        user.hub = Vendor.query.first()
        db.session.add(user)
    user.name = profile["name"]
    user.phone = profile["phone_number"]
    if user.role == UserRoles.initiative:
        user.set_default_project()
    db.session.commit()
    login_user(user)
    current_app.logger.info("%s logged", user.email)
    return redirect(url_for("main.ShowIndex"))
