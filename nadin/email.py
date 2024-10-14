from threading import Thread

from flask import current_app
from flask_mail import Message

from nadin.extensions import mail


def _async_wrapper(app, func, *args, **kwargs):
    with app.app_context():
        func(*args, **kwargs)


def run_async(app, func, *args, **kwargs):
    Thread(target=_async_wrapper, args=(app, func, *args), kwargs=kwargs).start()


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
        run_async(current_app._get_current_object(), mail.send, msg)
