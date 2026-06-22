"""
Admin-only utility endpoints.

Endpoints
---------
GET  /api/admin/users              – list all users
PUT  /api/admin/users/<id>/role    – change user role
PUT  /api/admin/users/<id>/status  – activate / deactivate user
GET  /api/admin/audit-logs         – paginated audit trail
GET  /api/admin/dashboard          – summary stats
"""
from flask import Blueprint, jsonify, request
from marshmallow import Schema, fields, validate, ValidationError

from models import db, User, Order, Product, AuditLog
from utils import admin_required, audit

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


# ── Users ──────────────────────────────────────────────────────────────────────

def _user_to_dict(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "name": u.name,
        "role": u.role,
        "is_active": u.is_active,
        "created_at": u.created_at.isoformat(),
        "last_login": u.last_login.isoformat() if u.last_login else None,
        "failed_login_attempts": u.failed_login_attempts,
    }


@admin_bp.get("/users")
@admin_required
def list_users():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)
    pagination = User.query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return jsonify({
        "users": [_user_to_dict(u) for u in pagination.items],
        "total": pagination.total,
        "pages": pagination.pages,
        "page": page,
    }), 200


class RoleSchema(Schema):
    role = fields.Str(required=True, validate=validate.OneOf(["customer", "admin"]))


@admin_bp.put("/users/<int:user_id>/role")
@admin_required
def update_role(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404
    try:
        data = RoleSchema().load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": "Validation failed", "details": e.messages}), 422
    old_role = user.role
    user.role = data["role"]
    db.session.commit()
    audit("admin_role_change", {"user_id": user_id, "from": old_role, "to": data["role"]})
    return jsonify({"message": "Role updated.", "user": _user_to_dict(user)}), 200


class StatusSchema(Schema):
    is_active = fields.Bool(required=True)


@admin_bp.put("/users/<int:user_id>/status")
@admin_required
def update_user_status(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404
    try:
        data = StatusSchema().load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": "Validation failed", "details": e.messages}), 422
    user.is_active = data["is_active"]
    user.failed_login_attempts = 0
    user.locked_until = None
    db.session.commit()
    action = "admin_user_activate" if data["is_active"] else "admin_user_deactivate"
    audit(action, {"user_id": user_id})
    return jsonify({"message": "User status updated.", "user": _user_to_dict(user)}), 200


# ── Audit logs ─────────────────────────────────────────────────────────────────

@admin_bp.get("/audit-logs")
@admin_required
def get_audit_logs():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    pagination = AuditLog.query.order_by(AuditLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return jsonify({
        "logs": [
            {
                "id": log.id,
                "user_id": log.user_id,
                "action": log.action,
                "ip_address": log.ip_address,
                "details": log.details,
                "created_at": log.created_at.isoformat(),
            }
            for log in pagination.items
        ],
        "total": pagination.total,
        "pages": pagination.pages,
        "page": page,
    }), 200


# ── Dashboard stats ────────────────────────────────────────────────────────────

@admin_bp.get("/dashboard")
@admin_required
def dashboard():
    total_users = User.query.count()
    total_products = Product.query.filter_by(is_active=True).count()
    total_orders = Order.query.count()
    pending_orders = Order.query.filter_by(status="pending").count()
    paid_orders = Order.query.filter_by(status="paid").count()
    revenue = db.session.query(
        db.func.sum(Order.total)
    ).filter(Order.status.in_(["paid", "processing", "delivered"])).scalar() or 0

    return jsonify({
        "total_users": total_users,
        "total_products": total_products,
        "total_orders": total_orders,
        "pending_orders": pending_orders,
        "paid_orders": paid_orders,
        "total_revenue_vnd": str(revenue),
    }), 200
