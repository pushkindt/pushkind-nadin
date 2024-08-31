import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dynaconf import FlaskDynaconf
from elasticsearch import Elasticsearch
from flask import Flask, render_template, request

from nadin import admin, api, auth, oauth
from nadin.extensions import db, login_manager, mail, migrate, moment, oauth_ext
from nadin.main import routes as main_routes
from nadin.oauth.server import config_oauth_server
from nadin.oauth.yandex import YandexOauth2Config


def create_app(**config):
    app = Flask(__name__)
    FlaskDynaconf(app, **config)
    register_extensions(app)
    register_blueprints(app)
    register_errorhandlers(app)
    register_shellcontext(app)
    configure_logger(app)

    return app


def register_extensions(app):

    oauth_ext.register(
        name=YandexOauth2Config.NAME,
        client_cls=YandexOauth2Config,
    )
    oauth_ext.init_app(app)
    config_oauth_server(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = app.config["LOGIN_MESSAGE"]
    login_manager.init_app(app)
    db.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    moment.init_app(app)

    if app.config["ELASTICSEARCH_URL"]:
        app.elasticsearch = Elasticsearch([app.config["ELASTICSEARCH_URL"]])
    else:
        app.elasticsearch = None


def register_blueprints(app):
    app.register_blueprint(admin.routes.bp, url_prefix="/admin")
    app.register_blueprint(auth.routes.bp, url_prefix="/auth")
    app.register_blueprint(api.routes.bp, url_prefix="/api")
    app.register_blueprint(main_routes.bp, url_prefix="/")
    app.register_blueprint(oauth.routes.bp, url_prefix="/oauth")


def register_errorhandlers(app):
    """Register error handlers."""

    def wants_json_response():
        return request.accept_mimetypes["application/json"] >= request.accept_mimetypes["text/html"]

    def render_error(error):
        """Render error template."""
        # If a HTTPException, pull the `code` attribute; default to 500
        error_code = getattr(error, "code", 500)
        if wants_json_response():
            return {"error": error.description}, error_code
        return render_template(f"errors/{error_code}.html", error=error), error_code

    for errcode in [400, 401, 403, 404, 413, 500, 503]:
        app.errorhandler(errcode)(render_error)


def register_shellcontext(app):
    """Register shell context objects."""

    def shell_context():
        """Shell context objects."""
        return {"db": db}

    app.shell_context_processor(shell_context)


def configure_logger(app):
    """Configure loggers."""
    if not app.debug:
        Path("logs").mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(f"logs/{__name__}.log", maxBytes=10240, backupCount=10, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]")
        )
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
    stdout_handler = logging.StreamHandler(sys.stdout)
    if not app.logger.handlers:
        app.logger.addHandler(stdout_handler)
