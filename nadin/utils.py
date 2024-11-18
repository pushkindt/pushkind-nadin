from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from functools import wraps
from html import unescape
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from flask import current_app, flash, jsonify, render_template, url_for
from flask_login import current_user
from flask_wtf import FlaskForm

from nadin.email import SendEmail

IMAGES = list("jpg jpe jpeg png gif svg bmp webp".split())


def get_filter_timestamps():
    now = datetime.now(tz=timezone.utc)
    today = datetime(now.year, now.month, now.day)
    week = today - timedelta(days=today.weekday())
    month = datetime(now.year, now.month, 1)
    recently = today - timedelta(days=42)
    quarter = datetime(now.year, 3 * ((now.month - 1) // 3) + 1, 1)
    year = datetime(now.year, 1, 1)
    dates = {
        "daily": int(today.timestamp()),
        "weekly": int(week.timestamp()),
        "monthly": int(month.timestamp()),
        "recently": int(recently.timestamp()),
        "quarterly": int(quarter.timestamp()),
        "annually": int(year.timestamp()),
    }
    return dates


def first(items: Optional[Iterable]) -> Any:
    return next(iter(items or []), None)


def flash_errors(form: FlaskForm, category: str = "warning"):
    """Flash all errors for a form."""
    for field, errors in form.errors.items():
        for error in errors:
            flash(f"{getattr(form, field).label.text} - {error}", category)


def role_required(roles_list):
    def decorator(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            if current_user.role not in roles_list:
                return render_template("errors/403.html"), 403
            return function(*args, **kwargs)

        return wrapper

    return decorator


def role_forbidden(roles_list):
    def decorator(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            if current_user.role in roles_list:
                return render_template("errors/403.html"), 403
            return function(*args, **kwargs)

        return wrapper

    return decorator


def role_required_ajax(roles_list):
    def decorator(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            if current_user.role not in roles_list:
                return jsonify({"status": False, "flash": ["У вас нет соответствующих полномочий."]}), 403
            return function(*args, **kwargs)

        return wrapper

    return decorator


def role_forbidden_ajax(roles_list):
    def decorator(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            if current_user.role in roles_list:
                return jsonify({"status": False, "flash": ["У вас нет соответствующих полномочий."]}), 403
            return function(*args, **kwargs)

        return wrapper

    return decorator


def SendEmailNotification(kind, order, recipients_id=None, data=None):
    if not recipients_id:
        recipients_id = []
    recipients = (
        r
        for r in order.reviewers
        if (getattr(r, f"email_{kind}", False) is True and (r.id in recipients_id or len(recipients_id) == 0))
    )
    for recipient in recipients:
        current_app.logger.info('"%s" email about order %s has been sent to %s', kind, order.number, recipient.email)
        token = recipient.get_jwt_token(expires_in=86400)
        next_page = url_for("main.show_order", order_id=order.id)
        SendEmail(
            f"Уведомление по заявке #{order.number}",
            sender=(current_app.config["MAIL_SENDERNAME"], current_app.config["ADMINS"][0]),
            recipients=[recipient.email],
            text_body=render_template(f"email/{kind}.txt", next_page=next_page, token=token, order=order, data=data),
            html_body=render_template(f"email/{kind}.html", next_page=next_page, token=token, order=order, data=data),
        )


def SendEmail1C(recipients, order, data):
    current_app.logger.info('"export1C" email about order %s has been sent to %s', order.number, recipients)

    if order.project is not None:
        subject = f"{order.project.name}. (pushkind_{order.number})"
    else:
        subject = f"pushkind_{order.number}"

    data = (f"pushkind_{order.number}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", data)

    SendEmail(
        subject,
        sender=(current_app.config["MAIL_SENDERNAME"], current_app.config["ADMINS"][0]),
        recipients=recipients,
        text_body=render_template("email/export1C.txt", order=order),
        html_body=render_template("email/export1C.html", order=order),
        attachments=[data],
    )


def get_escaped_url_parameter(escaped_url: str, param: str, default: Optional[str] = None) -> str:
    unescaped_url = unescape(escaped_url)
    parsed_url = urlparse(unescaped_url)
    result = parse_qs(parsed_url.query).get(param, [None])[0]
    return result if result is not None else default
