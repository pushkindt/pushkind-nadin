import time
from pathlib import Path

from authlib.jose import JsonWebKey, KeySet
from authlib.oauth2 import OAuth2Error
from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.security import gen_salt

from nadin.extensions import db
from nadin.main.utils import role_required
from nadin.models import OAuth2Client, UserRoles
from nadin.oauth.server import authorization

bp = Blueprint("oauth", __name__)


@bp.route("/", methods=("GET",))
@login_required
@role_required([UserRoles.admin])
def home():
    clients = OAuth2Client.query.all()
    return render_template("oauth/home.html", clients=clients)


def split_by_crlf(s):
    return [v for v in s.splitlines() if v]


@bp.route("/create_client", methods=("POST",))
@login_required
@role_required([UserRoles.admin])
def create_client():
    form = request.form
    client_id = gen_salt(24)
    client = OAuth2Client(client_id=client_id, user_id=current_user.id)
    # Mixin doesn't set the issue_at date
    client.client_id_issued_at = int(time.time())
    if client.token_endpoint_auth_method == "none":
        client.client_secret = ""
    else:
        client.client_secret = gen_salt(48)
    client_metadata = {
        "client_name": form["client_name"],
        "client_uri": form["client_uri"],
        "grant_types": split_by_crlf(form["grant_type"]),
        "redirect_uris": split_by_crlf(form["redirect_uri"]),
        "response_types": split_by_crlf(form["response_type"]),
        "scope": form["scope"],
        "token_endpoint_auth_method": form["token_endpoint_auth_method"],
    }
    client.set_client_metadata(client_metadata)
    db.session.add(client)
    db.session.commit()
    return redirect(url_for("oauth.home"))


@bp.route("/authorize", methods=("GET", "POST"))
@login_required
def authorize():
    if request.method == "GET":
        try:
            grant = authorization.get_consent_grant(end_user=current_user)
        except OAuth2Error as error:
            flash(error.description, category="error")
            return redirect(url_for("main.ShowIndex"))
        return render_template("oauth/authorize.html", user=current_user, grant=grant)
    if request.form["confirm"]:
        grant_user = current_user
    else:
        grant_user = None
    return authorization.create_authorization_response(grant_user=grant_user)


@bp.route("/remove_client/<int:client_id>", methods=("POST",))
@login_required
@role_required([UserRoles.admin])
def remove_client(client_id):
    client = OAuth2Client.query.filter_by(id=client_id).first_or_404()
    db.session.delete(client)
    db.session.commit()
    return redirect(url_for("oauth.home"))


@bp.route("/token", methods=("POST",))
def issue_token():
    response = authorization.create_token_response()
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response


@bp.route("/.well-known/openid-configuration")
def well_known_openid_configuration():

    response = jsonify(
        {
            "authorization_endpoint": url_for("oauth.authorize", _external=True),
            "token_endpoint": url_for("oauth.issue_token", _external=True),
            "userinfo_endpoint": url_for("oauth.userinfo", _external=True),
            "jwks_uri": url_for("oauth.jwks", _external=True),
            "end_session_endpoint": url_for("oauth.logout", _external=True),
            "id_token_signing_alg_values_supported": ["RS256"],
            "issuer": current_app.config["OPENID_ISS"],
            "scopes_supported": [
                "openid",
                "profile",
                "email",
            ],
            "grant_types_supported": [
                "authorization_code",
                "refresh_token",
            ],
            "response_types_supported": [
                "code",
                "token",
                "id_token",
                "code token",
                "code id_token",
                "token id_token",
                "code token id_token",
                "none",
            ],
            "subject_types_supported": ["public"],
            "token_endpoint_auth_methods_supported": [
                "client_secret_post",
                "client_secret_basic",
                "none",
            ],
            "code_challenge_methods_supported": ["S256"],
        }
    )
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response


def load_public_keys():
    public_key_path = Path(current_app.config["OPENID_PUBLIC_KEY"])
    public_key = JsonWebKey.import_key(public_key_path.read_bytes(), {"use": "sig", "alg": "RS256"})
    return KeySet([public_key])


@bp.route("/jwks")
def jwks():
    response = jsonify(load_public_keys().as_dict())
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response


@bp.route("/logout")
def logout():
    return jsonify({"result": "ok"})
