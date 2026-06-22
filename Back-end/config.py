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
    _db_url = os.environ.get("DATABASE_URL", "sqlite:///gas_store.db")
    # Đổi sang pg8000 driver (thuần Python, hỗ trợ mọi Python version)
    if _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql+pg8000://", 1)
    elif _db_url.startswith("postgresql://"):
        _db_url = _db_url.replace("postgresql://", "postgresql+pg8000://", 1)
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
        **({"connect_args": {"ssl_context": True}} if "pg8000" in _db_url else {}),
    }
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

    # ── Stripe (tùy chọn — chỉ cần nếu dùng thanh toán thẻ) ─────────────────
    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    # ── CORS — hỗ trợ nhiều origins, phân cách bằng dấu phẩy ────────────────
    _raw_origin = os.environ.get("FRONTEND_ORIGIN", "https://levantien3.netlify.app")
    FRONTEND_ORIGIN = [o.strip() for o in _raw_origin.split(",") if o.strip()]

    # ── SpeedSMS.vn notifications ─────────────────────────────────────────────
    SPEEDSMS_ACCESS_TOKEN = os.environ.get("SPEEDSMS_ACCESS_TOKEN", "")
    SPEEDSMS_PHONE_NUMBERS = os.environ.get("SPEEDSMS_PHONE_NUMBERS", "")

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
