import markdown
from flask import current_app, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from nadin.email import SendEmail
from nadin.main.forms import SendMessageForm
from nadin.main.routes import bp
from nadin.models.hub import User, UserRoles
from nadin.utils import flash_errors, role_forbidden


def get_email_recipients(users: list[User]):
    recipients = []
    for role in UserRoles:
        if role == UserRoles.default:
            continue
        recipients.append((role.value, f"Роль: {role}"))
    for user in users:
        if user.role == UserRoles.default:
            continue
        recipients.append((user.email, user.name))
    return recipients


@bp.route("/messages", methods=["GET", "POST"])
@login_required
@role_forbidden([UserRoles.default])
def send_message():
    form = SendMessageForm()
    form.recipients.choices = get_email_recipients(current_user.hub.users)
    if form.validate_on_submit():
        recipients = []
        for recipient in form.recipients.data:
            if "@" in recipient:
                user = User.query.filter_by(email=recipient).first()
                if user:
                    recipients.append(user.email)
            else:
                role = UserRoles(int(recipient))
                users = User.query.filter_by(role=role, hub_id=current_user.hub_id).all()
                for user in users:
                    recipients.append(user.email)

        SendEmail(
            subject=current_app.config["title"],
            sender=(current_user.name, current_app.config["mail_username"]),
            recipients=recipients,
            text_body=form.message.data,
            html_body=markdown.markdown(form.message.data),
        )
        flash("Сообщение отправлено.", "success")
        return redirect(url_for("main.send_message"))

    flash_errors(form)
    return render_template("main/messages/messages.html", form=form)
