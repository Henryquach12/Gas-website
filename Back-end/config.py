import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── Core ──────────────────────────────────────────────────────────────────
    SECRET_KEY = os.environ["SECRET_KEY"]
    DEBUG = False
    TESTING = False

    # ── Database ──────────────────────────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///gas_store.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Encrypt column-level sensitive fields at rest
    FIELD_ENCRYPTION_KEY = os.environ["FIELD_ENCRYPTION_KEY"].encode()

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        seconds=int(os.environ.get("JWT_ACCESS_EXPIRES", 900))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        seconds=int(os.environ.get("JWT_REFRESH_EXPIRES", 604800))
    )
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"
    # Prevent JWT replay after logout
    JWT_BLACKLIST_ENABLED = True
    JWT_BLACKLIST_TOKEN_CHECKS = ["access", "refresh"]

    # ── Stripe ────────────────────────────────────────────────────────────────
    STRIPE_SECRET_KEY = os.environ["STRIPE_SECRET_KEY"]
    STRIPE_WEBHOOK_SECRET = os.environ["STRIPE_WEBHOOK_SECRET"]

    # ── CORS ──────────────────────────────────────────────────────────────────
    FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5500")

    # ── Rate limiting ─────────────────────────────────────────────────────────
    RATELIMIT_STORAGE_URL = os.environ.get("RATELIMIT_STORAGE_URL", "memory://")
    RATELIMIT_DEFAULT = "200 per hour"

    # ── Security headers ──────────────────────────────────────────────────────
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False   # allow HTTP in dev


class ProductionConfig(Config):
    pass


def get_config():
    env = os.environ.get("FLASK_ENV", "development")
    return ProductionConfig() if env == "production" else DevelopmentConfig()
