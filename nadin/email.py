from threading import Thread

from flask import current_app
from flask_mail import Message

from nadin.extensions import mail


def SendEmailAsync(app, msg):
    with app.app_context():
        mail.send(msg)


def SendEmail(subject, sender, recipients, text_body, html_body, attachments=None, sync=False):
    if not current_app.config.get("MAIL_SERVER"):
        return
    msg = Message(subject, sender=sender, recipients=recipients)
    msg.body = text_body
    msg.html = html_body
    if attachments is not None:
        for attachment in attachments:
            msg.attach(*attachment)
    if sync is True:
        mail.send(msg)
    else:
        Thread(target=SendEmailAsync, args=(current_app._get_current_object(), msg)).start()
