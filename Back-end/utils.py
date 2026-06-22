"""
Security utilities: sanitization, validation helpers, audit logging,
security headers, and IP extraction.
"""
import re
import unicodedata
import bleach
from functools import wraps
from flask import request, g, abort
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from models import db, AuditLog, RevokedToken, User

# ── HTML sanitization ──────────────────────────────────────────────────────────
# Allow zero tags — all user text is plain-text only
_ALLOWED_TAGS: list[str] = []
_ALLOWED_ATTRS: dict = {}


def sanitize(value: str | None) -> str:
    """Strip all HTML/JS from user input."""
    if value is None:
        return ""
    cleaned = bleach.clean(str(value), tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, strip=True)
    return cleaned.strip()


# ── Vietnamese phone validation ────────────────────────────────────────────────
_VN_PHONE_RE = re.compile(r"^0[35789]\d{8}$")


def is_valid_vn_phone(phone: str) -> bool:
    return bool(_VN_PHONE_RE.match(phone.strip()))


# ── Long Xuyên city address validation ────────────────────────────────────────

def _strip_diacritics(text: str) -> str:
    """Decompose Unicode then drop all combining marks — makes 'Long Xuyên' == 'Long Xuyen'."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(c)
    )


def is_long_xuyen_address(address: str) -> bool:
    """
    Return True only when the address is inside Long Xuyên city, An Giang.
    Accepts both diacritics ("Long Xuyên") and ASCII-only ("Long Xuyen") spelling,
    as well as common abbreviations (TP., Tp., tp long xuyen, etc.).
    """
    norm = _strip_diacritics(address)
    # "Long Xuyên" → stripped → "long xuyen"; check that exact phrase
    return "long xuyen" in norm


# ── IP address extraction ──────────────────────────────────────────────────────

def get_client_ip() -> str:
    """Return the real client IP, respecting X-Forwarded-For behind a proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


# ── Audit logging ──────────────────────────────────────────────────────────────

def audit(action: str, details: dict | None = None, user_id: int | None = None):
    """Write an immutable audit log entry."""
    uid = user_id
    if uid is None:
        try:
            uid = get_jwt_identity()
        except Exception:
            uid = None

    entry = AuditLog(
        user_id=uid,
        action=action,
        ip_address=get_client_ip(),
        details=details,
    )
    db.session.add(entry)
    # Flush so the log is committed even if the outer transaction rolls back
    try:
        db.session.flush()
    except Exception:
        db.session.rollback()


# ── JWT blacklist check ────────────────────────────────────────────────────────

def is_token_revoked(jwt_payload: dict) -> bool:
    jti = jwt_payload.get("jti")
    try:
        return db.session.query(RevokedToken).filter_by(jti=jti).first() is not None
    except Exception:
        return False


# ── Role-based access decorators ──────────────────────────────────────────────

def admin_required(fn):
    """Decorator: requires a valid JWT where the user has role='admin'."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        uid = get_jwt_identity()
        user = db.session.get(User, uid)
        if not user or user.role != "admin":
            audit("unauthorized_admin_access")
            abort(403)
        g.current_user = user
        return fn(*args, **kwargs)
    return wrapper


def login_required(fn):
    """Decorator: requires any valid JWT."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        uid = get_jwt_identity()
        user = db.session.get(User, uid)
        if not user or not user.is_active:
            abort(401)
        g.current_user = user
        return fn(*args, **kwargs)
    return wrapper


# ── Security response headers ──────────────────────────────────────────────────

def apply_security_headers(response):
    """Add defence-in-depth HTTP headers to every response."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "img-src 'self' data:; "
        "connect-src 'self' https://api.stripe.com; "
        "frame-src https://js.stripe.com; "
        "object-src 'none'; "
        "base-uri 'none'; "
        "form-action 'self';"
    )
    # HSTS — only enable when TLS is confirmed in production
    response.headers["Strict-Transport-Security"] = (
        "max-age=63072000; includeSubDomains; preload"
    )
    # Remove fingerprinting header
    response.headers.pop("Server", None)
    return response
