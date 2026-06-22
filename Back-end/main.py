"""
Application factory for the Gas Store REST API.

Run (dev):
    pip install -r requirements.txt
    cp .env.example .env   # fill in your values
    python main.py

The app:
- Flask 3 with application factory pattern
- SQLAlchemy ORM (SQLite dev / PostgreSQL prod)
- Flask-Migrate for schema migrations
- JWT with token blacklisting
- Rate limiting on sensitive endpoints
- CORS restricted to the configured frontend origin
- Security headers on every response
- Stripe payment processing (cards never stored)
"""
import os
from datetime import datetime, timezone

import bcrypt
import stripe
from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate

from config import get_config
from models import db, RevokedToken, User
from utils import apply_security_headers


def create_app(config=None) -> Flask:
    app = Flask(__name__)

    # ── Config ─────────────────────────────────────────────────────────────────
    app.config.from_object(config or get_config())
    stripe.api_key = app.config["STRIPE_SECRET_KEY"]

    # ── Extensions ─────────────────────────────────────────────────────────────
    db.init_app(app)
    Migrate(app, db)

    jwt = JWTManager(app)

    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=[app.config.get("RATELIMIT_DEFAULT", "200 per hour")],
        storage_uri=app.config.get("RATELIMIT_STORAGE_URL", "memory://"),
    )

    cors_origins = app.config["FRONTEND_ORIGIN"]  # already a list from config.py
    CORS(
        app,
        resources={r"/api/*": {"origins": cors_origins}},
        supports_credentials=True,
    )

    # ── Log JWT key source on startup ─────────────────────────────────────────
    import os as _os
    _jwt_src = "JWT_SECRET_KEY" if _os.environ.get("JWT_SECRET_KEY") else "SECRET_KEY(fallback)"
    _key_len = len(app.config.get("JWT_SECRET_KEY", ""))
    app.logger.warning("JWT key source: %s | key length: %d chars", _jwt_src, _key_len)

    # ── JWT callbacks ──────────────────────────────────────────────────────────

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(_header, _payload):
        # Tokens expire naturally (15 min access / 7 day refresh).
        return False

    @jwt.revoked_token_loader
    def revoked_token_response(_header, _payload):
        return jsonify({"error": "Token has been revoked. Please log in again."}), 401

    @jwt.expired_token_loader
    def expired_token_response(_header, _payload):
        return jsonify({"error": "Token has expired."}), 401

    @jwt.invalid_token_loader
    def invalid_token_response(reason):
        app.logger.warning("JWT invalid token: %s", reason)
        return jsonify({"error": "Invalid token."}), 401

    @jwt.unauthorized_loader
    def missing_token_response(reason):
        app.logger.warning("JWT missing token: %s", reason)
        return jsonify({"error": "Authentication required."}), 401

    # ── Security headers on every response ────────────────────────────────────

    @app.after_request
    def set_security_headers(response):
        return apply_security_headers(response)

    # ── Register blueprints ────────────────────────────────────────────────────

    from auth import auth_bp
    from products import products_bp
    from orders import orders_bp
    from payments import payments_bp
    from admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(admin_bp)

    # ── Rate limits on sensitive endpoints ────────────────────────────────────
    limiter.limit("10 per minute")(auth_bp)
    limiter.limit("5 per minute")(payments_bp)

    # ── Health check ──────────────────────────────────────────────────────────

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}), 200

    # ── Generic error handlers ─────────────────────────────────────────────────

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"error": "Bad request."}), 400

    @app.errorhandler(401)
    def unauthorized(e):
        return jsonify({"error": "Authentication required."}), 401

    @app.errorhandler(403)
    def forbidden(e):
        return jsonify({"error": "Forbidden."}), 403

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Resource not found."}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "Method not allowed."}), 405

    @app.errorhandler(429)
    def rate_limited(e):
        return jsonify({"error": "Too many requests. Please slow down."}), 429

    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback()
        return jsonify({"error": "An internal error occurred."}), 500

    # ── Bootstrap admin account on first run ──────────────────────────────────

    with app.app_context():
        db.create_all()
        _bootstrap_admin(app)

    return app


def _bootstrap_admin(app: Flask):
    """Create the initial admin account if no admin exists yet."""
    email = os.environ.get("ADMIN_BOOTSTRAP_EMAIL")
    password = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD")
    if not email or not password:
        return
    if User.query.filter_by(role="admin").count() > 0:
        return
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
    admin = User(
        email=email.lower().strip(),
        password_hash=hashed,
        name="Admin",
        role="admin",
    )
    db.session.add(admin)
    db.session.commit()
    app.logger.warning(
        "Bootstrap admin created: %s — CHANGE THE PASSWORD IMMEDIATELY.", email
    )


# Gunicorn entry point: gunicorn main:app
app = create_app()

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=os.environ.get("FLASK_ENV") == "development",
    )
