"""
Orders blueprint.

Endpoints
---------
GET  /api/orders             – list orders for logged-in customer
GET  /api/orders/<ref>       – single order by reference
-- Admin --
GET  /api/orders/admin/all   – all orders (admin)
PUT  /api/orders/admin/<ref>/status  – update order status (admin)
"""
from flask import Blueprint, jsonify, request, g
from flask_jwt_extended import jwt_required, get_jwt_identity
from marshmallow import Schema, fields, validate, ValidationError

from models import db, Order
from utils import audit, admin_required, login_required

orders_bp = Blueprint("orders", __name__, url_prefix="/api/orders")

VALID_STATUSES = ["pending", "paid", "processing", "delivered", "cancelled"]


# ── Serializer ─────────────────────────────────────────────────────────────────

def _order_to_dict(order: Order, include_pii: bool = False) -> dict:
    """
    Serialize an order.
    PII fields (phone, address) are only included for the order owner or an admin.
    """
    base = {
        "id": order.id,
        "reference": order.reference,
        "status": order.status,
        "total": str(order.total),
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
        "items": [
            {
                "product_id": i.product_id,
                "product_name": i.product_name_snapshot,
                "unit_price": str(i.unit_price_snapshot),
                "quantity": i.quantity,
                "subtotal": str(i.subtotal),
            }
            for i in order.items
        ],
    }
    if include_pii:
        base["customer_name"] = order.customer_name
        base["customer_phone"] = order.customer_phone
        base["customer_address"] = order.customer_address
        base["notes"] = order.notes
    return base


# ── Customer routes ────────────────────────────────────────────────────────────

@orders_bp.get("/")
@login_required
def list_my_orders():
    orders = (
        Order.query
        .filter_by(user_id=g.current_user.id)
        .order_by(Order.created_at.desc())
        .all()
    )
    return jsonify({"orders": [_order_to_dict(o, include_pii=True) for o in orders]}), 200


@orders_bp.get("/<string:ref>")
@login_required
def get_order(ref: str):
    order = Order.query.filter_by(reference=ref).first_or_404()
    # Customers may only view their own orders
    if order.user_id != g.current_user.id and g.current_user.role != "admin":
        return jsonify({"error": "Forbidden."}), 403
    return jsonify(_order_to_dict(order, include_pii=True)), 200


# ── Admin routes ───────────────────────────────────────────────────────────────

@orders_bp.get("/admin/all")
@admin_required
def admin_list_orders():
    status = request.args.get("status")
    query = Order.query.order_by(Order.created_at.desc())
    if status and status in VALID_STATUSES:
        query = query.filter_by(status=status)
    orders = query.all()
    return jsonify({"orders": [_order_to_dict(o, include_pii=True) for o in orders]}), 200


class UpdateStatusSchema(Schema):
    status = fields.Str(required=True, validate=validate.OneOf(VALID_STATUSES))


@orders_bp.put("/admin/<string:ref>/status")
@admin_required
def admin_update_status(ref: str):
    order = Order.query.filter_by(reference=ref).first_or_404()

    try:
        data = UpdateStatusSchema().load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": "Validation failed", "details": e.messages}), 422

    old_status = order.status
    order.status = data["status"]
    db.session.commit()
    audit("order_status_update", {"ref": ref, "from": old_status, "to": data["status"]})
    return jsonify({"message": "Status updated.", "order": _order_to_dict(order, include_pii=True)}), 200
