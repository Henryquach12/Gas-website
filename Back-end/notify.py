"""
Order notification service — Gmail SMTP

Setup trên Render Environment:
  NOTIFY_EMAIL          = địa chỉ Gmail của bạn  (vd: abc@gmail.com)
  NOTIFY_EMAIL_PASSWORD = App Password 16 ký tự từ Google
    → myaccount.google.com → Bảo mật → Xác minh 2 bước (bật) → Mật khẩu ứng dụng → Tạo
"""
from __future__ import annotations

import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import current_app


def _vnd(amount) -> str:
    return f"{int(amount):,}đ".replace(",", ".")


def _build_email(order, items: list) -> tuple[str, str]:
    """Trả về (subject, body) dạng HTML."""
    products_rows = "".join(
        f"<tr><td>{i.product_name_snapshot}</td><td style='text-align:center'>{i.quantity}</td>"
        f"<td style='text-align:right'>{_vnd(i.subtotal)}</td></tr>"
        for i in items
    )

    subject = f"[Đơn mới] {order.reference} — {order.customer_name}"

    body = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:600px;margin:auto">
      <h2 style="color:#2563eb">🛒 Đơn hàng mới — {order.reference}</h2>
      <table style="width:100%;border-collapse:collapse;margin-bottom:16px">
        <tr><td style="padding:6px 0;color:#666;width:130px">Khách hàng</td>
            <td><strong>{order.customer_name}</strong></td></tr>
        <tr><td style="padding:6px 0;color:#666">Điện thoại</td>
            <td><strong>{order.customer_phone}</strong></td></tr>
        <tr><td style="padding:6px 0;color:#666">Địa chỉ</td>
            <td>{order.customer_address}</td></tr>
        <tr><td style="padding:6px 0;color:#666">Ghi chú</td>
            <td>{order.notes or "—"}</td></tr>
      </table>

      <table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:8px">
        <thead>
          <tr style="background:#f8fafc">
            <th style="padding:8px 12px;text-align:left">Sản phẩm</th>
            <th style="padding:8px 12px;text-align:center">SL</th>
            <th style="padding:8px 12px;text-align:right">Thành tiền</th>
          </tr>
        </thead>
        <tbody>{products_rows}</tbody>
        <tfoot>
          <tr style="background:#eff6ff">
            <td colspan="2" style="padding:10px 12px;font-weight:bold">TỔNG CỘNG</td>
            <td style="padding:10px 12px;text-align:right;font-weight:bold;color:#2563eb;font-size:1.1em">
              {_vnd(order.total)}
            </td>
          </tr>
        </tfoot>
      </table>

      <p style="color:#64748b;font-size:.85em;margin-top:20px">
        Đại Lý Gas Lê Văn Tiền 3 — 665 Trần Hưng Đạo, Long Xuyên
      </p>
    </body></html>
    """
    return subject, body


def _send_email(subject: str, body: str, app) -> None:
    sender = app.config.get("NOTIFY_EMAIL", "")
    password = app.config.get("NOTIFY_EMAIL_PASSWORD", "")

    if not sender or not password:
        app.logger.warning("Gmail chưa cấu hình — thiếu NOTIFY_EMAIL hoặc NOTIFY_EMAIL_PASSWORD.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Gas Lê Văn Tiền 3 <{sender}>"
    msg["To"] = sender   # gửi cho chính mình

    msg.attach(MIMEText(body, "html", "utf-8"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, sender, msg.as_string())
        app.logger.info("Email thông báo đã gửi đến %s", sender)
    except Exception as exc:
        app.logger.error("Gửi email thất bại: %s", exc)


def send_order_notification(order, items: list) -> None:
    """
    Gửi email thông báo đơn hàng mới đến Gmail của chủ shop.
    Chạy trên thread riêng để không làm chậm response API.
    """
    app = current_app._get_current_object()
    subject, body = _build_email(order, items)

    def _dispatch():
        with app.app_context():
            _send_email(subject, body, app)

    threading.Thread(target=_dispatch, daemon=True).start()
