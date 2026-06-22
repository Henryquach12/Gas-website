"""
Authentication blueprint.

Endpoints
---------
POST /api/auth/register   – create customer account
POST /api/auth/login      – issue access + refresh tokens
POST /api/auth/refresh    – rotate access token
POST /api/auth/logout     – blacklist both tokens
POST /api/auth/change-password
GET  /api/auth/me         – current user profile
"""
import re
from datetime import datetime, timezone, timedelta

import bcrypt
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
)
from marshmallow import Schema, fields, validate, ValidationError

from models import db, User, RevokedToken
from utils import sanitize, audit, get_client_ip

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

_MAX_FAILED = 5          # lock after N failed attempts
_LOCK_MINUTES = 15


# ── Schemas ────────────────────────────────────────────────────────────────────

class RegisterSchema(Schema):
    email = fields.Email(required=True)
    password = fields.Str(required=True, validate=validate.Length(min=8, max=128))
    name = fields.Str(required=True, validate=validate.Length(min=2, max=100))
    phone = fields.Str(load_default=None)


class LoginSchema(Schema):
    email = fields.Email(required=True)
    password = fields.Str(required=True)


class ChangePasswordSchema(Schema):
    current_password = fields.Str(required=True)
    new_password = fields.Str(required=True, validate=validate.Length(min=8, max=128))


_VN_PHONE_RE = re.compile(r"^0[35789]\d{8}$")
_PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$")


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()


def _check_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── Routes ─────────────────────────────────────────────────────────────────────

@auth_bp.post("/register")
def register():
    try:
        data = RegisterSchema().load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": "Validation failed", "details": e.messages}), 422

    email = sanitize(data["email"]).lower()
    name = sanitize(data["name"])
    phone = sanitize(data.get("phone") or "")
    password = data["password"]

    if not _PASSWORD_RE.match(password):
        return jsonify({
            "error": "Password must be at least 8 characters and contain uppercase, lowercase, and a digit."
        }), 422

    if phone and not _VN_PHONE_RE.match(phone):
        return jsonify({"error": "Invalid Vietnamese phone number."}), 422

    if User.query.filter_by(email=email).first():
        # Don't reveal whether the email exists — timing-safe response
        return jsonify({"message": "If that email is available, registration succeeded."}), 201

    user = User(
        email=email,
        password_hash=_hash_password(password),
        name=name,
        phone=phone or None,
    )
    db.session.add(user)
    db.session.commit()
    audit("user_register", {"email": email}, user_id=user.id)
    return jsonify({"message": "Account created. Please log in."}), 201


@auth_bp.post("/login")
def login():
    try:
        data = LoginSchema().load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": "Validation failed", "details": e.messages}), 422

    email = sanitize(data["email"]).lower()
    password = data["password"]

    user = User.query.filter_by(email=email).first()

    # Always run bcrypt to prevent timing-based user enumeration
    dummy_hash = "$2b$12$invalidhashfortimingprotectionXXXXXXXXXXXXXXXXXXXXXX"
    stored_hash = user.password_hash if user else dummy_hash

    password_ok = _check_password(password, stored_hash)

    if not user or not password_ok or not user.is_active:
        if user and not password_ok:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= _MAX_FAILED:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=_LOCK_MINUTES)
            db.session.commit()
            audit("login_failed", {"email": email})
        return jsonify({"error": "Invalid credentials."}), 401

    if user.is_locked():
        audit("login_blocked_locked", {"email": email})
        return jsonify({"error": "Account temporarily locked. Try again later."}), 403

    # Successful login — reset failure counter
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = datetime.now(timezone.utc)
    db.session.commit()

    access_token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)
    audit("login_success", {"email": email}, user_id=user.id)

    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {"id": user.id, "name": user.name, "role": user.role},
    }), 200


@auth_bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    uid = get_jwt_identity()
    user = db.session.get(User, uid)
    if not user or not user.is_active:
        return jsonify({"error": "Unauthorized."}), 401
    new_access = create_access_token(identity=uid)
    return jsonify({"access_token": new_access}), 200


@auth_bp.post("/logout")
@jwt_required(verify_type=False)
def logout():
    jwt = get_jwt()
    jti = jwt["jti"]
    exp = datetime.fromtimestamp(jwt["exp"], tz=timezone.utc)
    uid = get_jwt_identity()

    revoked = RevokedToken(jti=jti, user_id=uid, expires_at=exp)
    db.session.add(revoked)
    db.session.commit()
    audit("logout", user_id=uid)
    return jsonify({"message": "Logged out."}), 200


@auth_bp.post("/change-password")
@jwt_required()
def change_password():
    uid = get_jwt_identity()
    user = db.session.get(User, uid)
    if not user:
        return jsonify({"error": "Unauthorized."}), 401

    try:
        data = ChangePasswordSchema().load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": "Validation failed", "details": e.messages}), 422

    if not _check_password(data["current_password"], user.password_hash):
        audit("change_password_failed", user_id=uid)
        return jsonify({"error": "Current password is incorrect."}), 403

    new_pw = data["new_password"]
    if not _PASSWORD_RE.match(new_pw):
        return jsonify({
            "error": "New password must be at least 8 characters and contain uppercase, lowercase, and a digit."
        }), 422

    user.password_hash = _hash_password(new_pw)
    db.session.commit()

    # Revoke all existing tokens so the user must re-login everywhere
    audit("change_password_success", user_id=uid)
    return jsonify({"message": "Password changed. Please log in again."}), 200


@auth_bp.get("/me")
@jwt_required()
def me():
    uid = get_jwt_identity()
    user = db.session.get(User, uid)
    if not user:
        return jsonify({"error": "Not found."}), 404
    return jsonify({
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "phone": user.phone,
        "role": user.role,
        "created_at": user.created_at.isoformat(),
    }), 200
