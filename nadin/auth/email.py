from flask import current_app, render_template

from nadin.email import SendEmail


def send_password_reset_email(user):
    token = user.get_jwt_token()
    SendEmail(
        'Сброс пароля для "Согласования заявок"',
        sender=(current_app.config["MAIL_SENDERNAME"], current_app.config["ADMINS"][0]),
        recipients=[user.email],
        text_body=render_template("email/reset.txt", token=token),
        html_body=render_template("email/reset.html", token=token),
    )


def send_user_registered_email(user):
    SendEmail(
        "Зарегистрирован новый пользователь",
        sender=(current_app.config["MAIL_SENDERNAME"], current_app.config["ADMINS"][0]),
        recipients=[current_app.config["ADMINS"][0]],
        text_body=render_template("email/registered.txt", user=user),
        html_body=render_template("email/registered.html", user=user),
    )
