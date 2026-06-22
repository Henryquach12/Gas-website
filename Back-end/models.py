"""
SQLAlchemy models.
Sensitive fields (phone, address) are encrypted at rest using Fernet symmetric
encryption so raw PII is never stored as plaintext in the database.
"""
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from cryptography.fernet import Fernet
from flask import current_app

db = SQLAlchemy()


# ── Encrypted field helper ─────────────────────────────────────────────────────

class EncryptedType(db.TypeDecorator):
    """Transparently encrypts/decrypts TEXT columns at rest."""
    impl = db.Text
    cache_ok = True

    def _fernet(self):
        return Fernet(current_app.config["FIELD_ENCRYPTION_KEY"])

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return self._fernet().encrypt(value.encode()).decode()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return self._fernet().decrypt(value.encode()).decode()


# ── Models ─────────────────────────────────────────────────────────────────────

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    phone = db.Column(EncryptedType, nullable=True)          # PII — encrypted
    role = db.Column(db.String(20), nullable=False, default="customer")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime, nullable=True)

    orders = db.relationship("Order", back_populates="user", lazy="dynamic")
    token_revocations = db.relationship("RevokedToken", back_populates="user", lazy="dynamic")

    def is_locked(self):
        if self.locked_until is None:
            return False
        return datetime.now(timezone.utc) < self.locked_until.replace(tzinfo=timezone.utc)


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Numeric(12, 0), nullable=False)   # VND — no decimals
    stock = db.Column(db.Integer, nullable=True)
    description = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(512), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=lambda: datetime.now(timezone.utc))

    order_items = db.relationship("OrderItem", back_populates="product", lazy="dynamic")


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(32), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    # Customer snapshot (encrypted PII)
    customer_name = db.Column(db.String(255), nullable=False)
    customer_phone = db.Column(EncryptedType, nullable=False)       # encrypted
    customer_address = db.Column(EncryptedType, nullable=False)     # encrypted
    notes = db.Column(db.Text, nullable=True)

    status = db.Column(
        db.String(50), nullable=False, default="pending",
        # pending → paid → processing → delivered → cancelled
    )
    total = db.Column(db.Numeric(14, 0), nullable=False)

    # Stripe references — never store raw card data
    stripe_payment_intent_id = db.Column(db.String(255), nullable=True, unique=True)

    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", back_populates="orders")
    items = db.relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=True)

    # Price/name snapshot at time of purchase — never rely on live product data
    product_name_snapshot = db.Column(db.String(255), nullable=False)
    unit_price_snapshot = db.Column(db.Numeric(12, 0), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    subtotal = db.Column(db.Numeric(14, 0), nullable=False)

    order = db.relationship("Order", back_populates="items")
    product = db.relationship("Product", back_populates="order_items")


class RevokedToken(db.Model):
    """JWT blacklist — tokens added here are rejected even if not expired."""
    __tablename__ = "revoked_tokens"

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    revoked_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime, nullable=False)

    user = db.relationship("User", back_populates="token_revocations")


class AuditLog(db.Model):
    """Immutable audit trail — never update or delete rows."""
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)   # IPv6-safe
    details = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
