import time
from pathlib import Path

from authlib.integrations.flask_oauth2 import current_token
from authlib.jose import JsonWebKey, KeySet
from authlib.oauth2 import OAuth2Error
from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.security import gen_salt

from nadin.extensions import db
from nadin.main.utils import role_required
from nadin.models import OAuth2Client, UserRoles
from nadin.oauth2 import JWT_CONFIG, authorization, generate_user_info, require_oauth

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
            grant = authorization.validate_consent_request(end_user=current_user)
        except OAuth2Error as error:
            return jsonify(dict(error.get_body()))
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
    return authorization.create_token_response()


@bp.route("/userinfo")
@require_oauth("profile")
def api_me():
    return jsonify(generate_user_info(current_token.user, current_token.scope))


@bp.route("/.well-known/openid-configuration")
def well_known_openid_configuration():

    return jsonify(
        {
            "authorization_endpoint": url_for("oauth.authorize", _external=True),
            "token_endpoint": url_for("oauth.issue_token", _external=True),
            "userinfo_endpoint": url_for("oauth.api_me", _external=True),
            "jwks_uri": url_for("oauth.jwks_endpoint", _external=True),
            # Do I even need this one?
            # IMO the OIDC server doesn't have a concept of a user being still logged in? --mh
            # "end_session_endpoint": "http://oidc:4000/openid/end-session",
            "id_token_signing_alg_values_supported": ["HS256", "RS256"],
            "issuer": JWT_CONFIG["iss"],
            "response_types_supported": [
                "code",
                # TODO check what it takes to support these too
                # "id_token",
                # "id_token token",
                # "code token",
                # "code id_token",
                # "code id_token token"
            ],
            "subject_types_supported": ["public"],
            "token_endpoint_auth_methods_supported": [
                # TODO is supporting both a good idea? --mh
                "client_secret_post",
                "client_secret_basic",
            ],
        }
    )


def load_public_keys():
    public_key_path = Path("public.pem")
    public_key = JsonWebKey.import_key(public_key_path.read_bytes())
    public_key["use"] = "sig"
    public_key["alg"] = "RS256"
    return KeySet([public_key])


@bp.route("/oauth/jwks")
def jwks_endpoint():
    return jsonify(load_public_keys().as_dict())
