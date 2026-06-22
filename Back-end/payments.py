"""
Payment blueprint — Stripe integration.

Security model
--------------
* Raw card data NEVER touches this server.
* Stripe.js (frontend) tokenises the card and returns a PaymentMethod ID.
* We call Stripe server-side to create/confirm a PaymentIntent using that ID.
* On success, Stripe sends a webhook; we mark the order as paid there.
* The PaymentMethod is used once and NOT stored.

Endpoints
---------
POST /api/payments/create-intent   – create Stripe PaymentIntent for a pending order
POST /api/payments/webhook         – Stripe webhook (payment_intent.succeeded / failed)
"""
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone

import stripe
from flask import Blueprint, request, jsonify, current_app
from marshmallow import Schema, fields, validate, ValidationError

from models import db, Order, OrderItem, Product
from utils import sanitize, audit, is_valid_vn_phone, is_long_xuyen_address, login_required

payments_bp = Blueprint("payments", __name__, url_prefix="/api/payments")


# ── Schemas ────────────────────────────────────────────────────────────────────

class CartItemSchema(Schema):
    product_id = fields.Int(required=True)
    quantity = fields.Int(required=True, validate=validate.Range(min=1, max=99))


class CheckoutSchema(Schema):
    customer_name = fields.Str(required=True, validate=validate.Length(min=2, max=100))
    customer_phone = fields.Str(required=True)
    customer_address = fields.Str(required=True, validate=validate.Length(min=10, max=500))
    notes = fields.Str(load_default="", validate=validate.Length(max=500))
    items = fields.List(fields.Nested(CartItemSchema), required=True, validate=validate.Length(min=1))
    # payment_method_id comes from Stripe.js — it is NOT a raw card number
    payment_method_id = fields.Str(required=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _generate_order_ref() -> str:
    return "ORD-" + secrets.token_hex(6).upper()


def _build_order_items(cart: list[dict]) -> tuple[list[OrderItem], int]:
    """
    Validate cart against live product data and return (items, total_vnd).
    Raises ValueError if any product is unavailable or stock is insufficient.
    """
    items = []
    total = 0
    for entry in cart:
        product = Product.query.filter_by(id=entry["product_id"], is_active=True).first()
        if not product:
            raise ValueError(f"Product {entry['product_id']} is not available.")
        qty = entry["quantity"]
        if product.stock is not None and product.stock < qty:
            raise ValueError(f"Insufficient stock for '{product.name}'.")
        subtotal = int(product.price) * qty
        total += subtotal
        items.append(OrderItem(
            product_id=product.id,
            product_name_snapshot=product.name,
            unit_price_snapshot=product.price,
            quantity=qty,
            subtotal=subtotal,
        ))
    return items, total


# ── Routes ─────────────────────────────────────────────────────────────────────

@payments_bp.post("/create-intent")
def create_payment_intent():
    """
    1. Validate cart + customer details.
    2. Build order record (status='pending').
    3. Create Stripe PaymentIntent server-side.
    4. Return client_secret to frontend — Stripe.js confirms it there.
    Card data never reaches this endpoint.
    """
    stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]

    try:
        data = CheckoutSchema().load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": "Validation failed", "details": e.messages}), 422

    phone = sanitize(data["customer_phone"])
    if not is_valid_vn_phone(phone):
        return jsonify({"error": "Invalid phone number."}), 422

    address = sanitize(data["customer_address"])
    if not is_long_xuyen_address(address):
        return jsonify({
            "error": "Chúng tôi chỉ giao hàng trong TP. Long Xuyên, An Giang. "
                     "Vui lòng nhập địa chỉ có 'Long Xuyên' hoặc 'Long Xuyen'."
        }), 422

    try:
        order_items, total_vnd = _build_order_items(data["items"])
    except ValueError as e:
        return jsonify({"error": str(e)}), 422

    # Create pending order before charging — we'll confirm on webhook
    order = Order(
        reference=_generate_order_ref(),
        customer_name=sanitize(data["customer_name"]),
        customer_phone=phone,
        customer_address=sanitize(data["customer_address"]),
        notes=sanitize(data.get("notes") or ""),
        total=total_vnd,
        status="pending",
    )
    # Attach authenticated user if present
    try:
        from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
        verify_jwt_in_request(optional=True)
        uid = get_jwt_identity()
        if uid:
            order.user_id = uid
    except Exception:
        pass

    db.session.add(order)
    db.session.flush()   # get order.id without committing

    for item in order_items:
        item.order_id = order.id
        db.session.add(item)

    # Create Stripe PaymentIntent — amount in VND (smallest unit = 1 VND, no subunit)
    try:
        intent = stripe.PaymentIntent.create(
            amount=total_vnd,
            currency="vnd",
            payment_method=data["payment_method_id"],
            confirm=True,
            # Use once and discard — do NOT save the payment method
            setup_future_usage=None,
            metadata={
                "order_reference": order.reference,
                "order_id": str(order.id),
            },
            return_url="about:blank",   # required for 3DS redirect flows
        )
    except stripe.error.CardError as e:
        db.session.rollback()
        audit("payment_card_error", {"error": str(e.user_message)})
        return jsonify({"error": e.user_message or "Card declined."}), 402
    except stripe.error.StripeError as e:
        db.session.rollback()
        audit("payment_stripe_error", {"error": str(e)})
        return jsonify({"error": "Payment service error. Please try again."}), 502

    order.stripe_payment_intent_id = intent.id
    db.session.commit()
    audit("payment_intent_created", {"order_ref": order.reference, "intent_id": intent.id})

    # Return client_secret only — never return card details
    return jsonify({
        "client_secret": intent.client_secret,
        "order_reference": order.reference,
        "requires_action": intent.status == "requires_action",
    }), 201


@payments_bp.post("/webhook")
def stripe_webhook():
    """
    Stripe calls this endpoint to confirm payment outcomes.
    We verify the webhook signature to prevent spoofed events.
    """
    stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]
    webhook_secret = current_app.config["STRIPE_WEBHOOK_SECRET"]

    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except stripe.error.SignatureVerificationError:
        audit("webhook_invalid_signature")
        return jsonify({"error": "Invalid signature."}), 400

    intent = event["data"]["object"]
    order = Order.query.filter_by(stripe_payment_intent_id=intent["id"]).first()

    if event["type"] == "payment_intent.succeeded":
        if order and order.status == "pending":
            order.status = "paid"
            # Decrement stock
            for item in order.items:
                if item.product and item.product.stock is not None:
                    item.product.stock = max(0, item.product.stock - item.quantity)
            db.session.commit()
            audit("payment_succeeded", {"order_ref": order.reference if order else intent["id"]})

    elif event["type"] == "payment_intent.payment_failed":
        if order and order.status == "pending":
            order.status = "cancelled"
            db.session.commit()
            audit("payment_failed", {"order_ref": order.reference if order else intent["id"]})

    return jsonify({"received": True}), 200
