from flask import g
from flask_httpauth import HTTPBasicAuth

from nadin.api.errors import error_response
from nadin.models.order import User

basic_auth = HTTPBasicAuth()


@basic_auth.verify_password
def verify_password(email, password):
    user = User.query.filter_by(email=email).first()
    if user is None:
        return False
    g.user_id = user.id
    return user.check_password(password)


@basic_auth.error_handler
def basic_auth_error():
    return error_response(401)
