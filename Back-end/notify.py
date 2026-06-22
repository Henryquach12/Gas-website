"""
Order notification service — eSMS.vn (Vietnamese SMS provider).

Setup:
  1. Đăng ký tài khoản tại https://esms.vn
  2. Vào mục "Tích hợp API" → lấy ApiKey và SecretKey
  3. Nạp tiền (gói nhỏ nhất ~50.000đ)
  4. Điền ESMS_API_KEY, ESMS_SECRET_KEY, ESMS_PHONE_NUMBERS vào .env
"""
from __future__ import annotations

import threading
import requests as http
from flask import current_app

ESMS_SEND_URL = "https://rest.esms.vn/MainService.svc/json/SendMultipleMessage_V4_get/"


def _vnd(amount) -> str:
    return f"{int(amount):,}d".replace(",", ".")


def _build_sms(order, items: list) -> str:
    """
    Build a compact SMS message (Vietnamese Unicode ~160 chars/segment).
    Keeps it short to minimise cost.
    """
    products = ", ".join(
        f"{i.product_name_snapshot} x{i.quantity}" for i in items
    )
    return (
        f"DON HANG MOI [{order.reference}]\n"
        f"KH: {order.customer_name}\n"
        f"DT: {order.customer_phone}\n"
        f"DC: {order.customer_address}\n"
        f"SP: {products}\n"
        f"TONG: {_vnd(order.total)}"
    )


def _send_sms(content: str, app) -> None:
    api_key = app.config.get("ESMS_API_KEY", "")
    secret_key = app.config.get("ESMS_SECRET_KEY", "")
    raw_numbers = app.config.get("ESMS_PHONE_NUMBERS", "")

    if not api_key or not secret_key or not raw_numbers:
        app.logger.warning("eSMS not configured — SMS notification skipped.")
        return

    numbers = [n.strip() for n in raw_numbers.split(",") if n.strip()]

    for phone in numbers:
        payload = {
            "ApiKey": api_key,
            "Content": content,
            "Phone": phone,
            "SecretKey": secret_key,
            "SmsType": "2",      # 2 = tin nhắn thường (không cần brandname)
            "IsUnicode": "0",    # 0 = không dấu để tiết kiệm ký tự/giá
        }
        try:
            resp = http.post(ESMS_SEND_URL, json=payload, timeout=10)
            data = resp.json()
            code = data.get("CodeResult") or data.get("code")
            if str(code) == "100":
                app.logger.info("eSMS sent to %s for order %s", phone, "")
            else:
                app.logger.error("eSMS error to %s: %s", phone, data)
        except Exception as exc:
            app.logger.error("eSMS request failed to %s: %s", phone, exc)


def send_order_notification(order, items: list) -> None:
    """
    Gửi SMS thông báo đến các số của chủ shop qua eSMS.vn.
    Chạy trên thread riêng để không làm chậm response API.
    """
    app = current_app._get_current_object()
    content = _build_sms(order, items)

    def _dispatch():
        with app.app_context():
            _send_sms(content, app)

    threading.Thread(target=_dispatch, daemon=True).start()
