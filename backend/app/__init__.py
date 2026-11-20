import logging
import os
from logging.handlers import RotatingFileHandler

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from .config import Config, DEFAULT_JWT, DEFAULT_SECRET
from .extensions import cors, db, jwt, migrate


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    if app.config["ENV_NAME"] == "production" and not app.config.get("TESTING"):
        if app.config["SECRET_KEY"] == DEFAULT_SECRET or app.config["JWT_SECRET_KEY"] == DEFAULT_JWT:
            raise RuntimeError("Set SECRET_KEY and JWT_SECRET_KEY in the environment for production.")

    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)
    _setup_logging(app)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})

    from . import models  # noqa: F401
    from .routes import register_blueprints
    register_blueprints(app)
    _register_handlers(app)

    @app.get("/uploads/<path:filename>")
    def uploads(filename):
        return send_from_directory(app.config["UPLOAD_DIR"], filename, max_age=3600)

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    @app.cli.command("init-db")
    def init_db():
        db.create_all()
        print("Database tables created.")

    return app


def _setup_logging(app):
    if app.config.get("TESTING"):
        return
    log_dir = os.path.join(app.config["DATA_DIR"], "logs")
    os.makedirs(log_dir, exist_ok=True)
    handler = RotatingFileHandler(os.path.join(log_dir, "shopsphere.log"), maxBytes=1_000_000, backupCount=3)
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    handler.setFormatter(fmt)
    logger = logging.getLogger("shopsphere")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    logger.addHandler(stream)


def _register_handlers(app):
    from .models import RevokedToken

    @jwt.token_in_blocklist_loader
    def is_revoked(_header, payload):
        return RevokedToken.query.filter_by(jti=payload["jti"]).first() is not None

    @jwt.unauthorized_loader
    def missing(msg):
        return jsonify({"error": "Authentication required"}), 401

    @jwt.invalid_token_loader
    def invalid(msg):
        return jsonify({"error": "Invalid token"}), 401

    @jwt.expired_token_loader
    def expired(_h, _p):
        return jsonify({"error": "Session expired, please log in again", "expired": True}), 401

    @jwt.revoked_token_loader
    def revoked(_h, _p):
        return jsonify({"error": "Session has been logged out"}), 401

    @app.errorhandler(HTTPException)
    def http_error(e):
        return jsonify({"error": e.description or e.name}), e.code

    @app.errorhandler(Exception)
    def server_error(e):
        db.session.rollback()
        logging.getLogger("shopsphere").exception("Unhandled error on %s %s", request.method, request.path)
        return jsonify({"error": "Something went wrong on our side"}), 500
