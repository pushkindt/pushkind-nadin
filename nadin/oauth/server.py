from pathlib import Path

from authlib.integrations.flask_oauth2 import AuthorizationServer, ResourceProtector
from authlib.integrations.sqla_oauth2 import (
    create_bearer_token_validator,
    create_query_client_func,
    create_save_token_func,
)
from authlib.oauth2.rfc6749.grants import AuthorizationCodeGrant as _AuthorizationCodeGrant
from authlib.oidc.core import UserInfo
from authlib.oidc.core.grants import OpenIDCode as _OpenIDCode
from flask import current_app

from nadin.extensions import db
from nadin.models import OAuth2AuthorizationCode, OAuth2Client, OAuth2Token, User


def generate_user_info(user, scope):
    user_info = UserInfo(sub=str(user.id))
    if "profile" in scope:
        user_info["name"] = user.name
    if "email" in scope:
        user_info["email"] = user.email
    return user_info


class AuthorizationCodeGrant(_AuthorizationCodeGrant):

    TOKEN_ENDPOINT_AUTH_METHODS = ["client_secret_basic", "client_secret_post", "none"]

    def save_authorization_code(self, code, request):
        code_challenge = request.data.get("code_challenge")
        code_challenge_method = request.data.get("code_challenge_method")
        nonce = request.data.get("nonce")
        auth_code = OAuth2AuthorizationCode(
            code=code,
            client_id=request.client.client_id,
            redirect_uri=request.redirect_uri,
            scope=request.scope,
            user_id=request.user.id,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            nonce=nonce,
        )
        db.session.add(auth_code)
        db.session.commit()
        return auth_code

    def query_authorization_code(self, code, client):
        auth_code = OAuth2AuthorizationCode.query.filter_by(code=code, client_id=client.client_id).first()
        if auth_code and not auth_code.is_expired():
            return auth_code
        return None

    def delete_authorization_code(self, authorization_code):
        db.session.delete(authorization_code)
        db.session.commit()

    def authenticate_user(self, authorization_code):
        return User.query.get(authorization_code.user_id)


class OpenIDCode(_OpenIDCode):
    def exists_nonce(self, nonce, request):
        exists = OAuth2AuthorizationCode.query.filter_by(client_id=request.client_id, nonce=nonce).first()
        return bool(exists)

    def get_jwt_config(self, grant):
        private_key_path = Path(current_app.config["OPENID_PRIVATE_KEY"])
        JWT_CONFIG = {
            "alg": "RS256",
            "iss": current_app.config["OPENID_ISS"],
            "exp": 3600,
            "key": private_key_path.read_text(encoding="ASCII"),
        }
        return JWT_CONFIG

    def generate_user_info(self, user, scope):
        return generate_user_info(user, scope)


authorization = AuthorizationServer()
require_oauth = ResourceProtector()


def config_oauth_server(app):
    query_client = create_query_client_func(db.session, OAuth2Client)
    save_token = create_save_token_func(db.session, OAuth2Token)
    authorization.init_app(app, query_client=query_client, save_token=save_token)

    # support all openid grants
    authorization.register_grant(
        AuthorizationCodeGrant,
        [
            OpenIDCode(require_nonce=True),
        ],
    )

    # protect resource
    bearer_cls = create_bearer_token_validator(db.session, OAuth2Token)
    require_oauth.register_token_validator(bearer_cls())
