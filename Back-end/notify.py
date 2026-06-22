"""
Order notification service — SpeedSMS.vn

Setup:
  1. Đăng ký tại https://speedsms.vn
  2. Đăng nhập → Tài khoản → Lấy Access Token
  3. Nạp tiền (chuyển khoản nội địa)
  4. Điền SPEEDSMS_ACCESS_TOKEN và SPEEDSMS_PHONE_NUMBERS vào .env
"""
from __future__ import annotations

import base64
import threading

import requests as http
from flask import current_app

SPEEDSMS_URL = "https://api.speedsms.vn/index.php/sms/send"


def _vnd(amount) -> str:
    return f"{int(amount):,}d".replace(",", ".")


def _build_sms(order, items: list) -> str:
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
    token = app.config.get("SPEEDSMS_ACCESS_TOKEN", "")
    raw_numbers = app.config.get("SPEEDSMS_PHONE_NUMBERS", "")

    if not token or not raw_numbers:
        app.logger.warning("SpeedSMS chưa cấu hình — bỏ qua thông báo SMS.")
        return

    numbers = [n.strip() for n in raw_numbers.split(",") if n.strip()]

    # SpeedSMS dùng HTTP Basic Auth: username=token, password=":x"
    credentials = base64.b64encode(f"{token}:x".encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/json",
    }
    payload = {
        "to": numbers,
        "content": content,
        "sms_type": 4,   # 4 = SMS đầu số ngẫu nhiên, không cần đăng ký brandname
    }

    try:
        resp = http.post(SPEEDSMS_URL, json=payload, headers=headers, timeout=10)
        data = resp.json()
        if data.get("status") == "success":
            app.logger.info("SpeedSMS gửi thành công đến %s", numbers)
        else:
            app.logger.error("SpeedSMS lỗi: %s", data)
    except Exception as exc:
        app.logger.error("SpeedSMS request thất bại: %s", exc)


def send_order_notification(order, items: list) -> None:
    """
    Gửi SMS thông báo đến các số của chủ shop qua SpeedSMS.vn.
    Chạy trên thread riêng để không làm chậm response API.
    """
    app = current_app._get_current_object()
    content = _build_sms(order, items)

    def _dispatch():
        with app.app_context():
            _send_sms(content, app)

    threading.Thread(target=_dispatch, daemon=True).start()
