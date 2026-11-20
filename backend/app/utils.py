"""HTTP helpers, auth decorators, rate limiting, uploads, e-mail."""
import logging
import os
import re
import smtplib
import time
import uuid
from collections import defaultdict, deque
from email.message import EmailMessage
from functools import wraps

from flask import current_app, g, jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from PIL import Image

from .extensions import db
from .models import AuditLog, User

log = logging.getLogger("shopsphere")


def api_error(message, status=400, **extra):
    return jsonify({"error": message, **extra}), status


# ---------- validation ----------
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def valid_email(email):
    return bool(email) and len(email) <= 255 and bool(_EMAIL_RE.match(email))


def password_problem(pw):
    if not isinstance(pw, str) or len(pw) < 8:
        return "Password must be at least 8 characters"
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        return "Password must contain letters and numbers"
    if len(pw) > 128:
        return "Password is too long"
    return None


def clean(value, maxlen=255):
    return value.strip()[:maxlen] if isinstance(value, str) else ""


def to_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def paginate(query, serializer):
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    per_page = min(max(request.args.get("per_page", 12, type=int) or 12, 1), 100)
    p = query.paginate(page=page, per_page=per_page, error_out=False)
    return {"items": [serializer(i) for i in p.items], "page": p.page, "pages": p.pages,
            "total": p.total, "per_page": per_page}


# ---------- auth ----------
def _load_user():
    user = db.session.get(User, int(get_jwt_identity()))
    if not user or not user.is_active:
        return None
    return user


def roles_required(*roles):
    """Require a valid JWT. If roles given, user must have one (super_admin always passes)."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **k):
            verify_jwt_in_request()
            user = _load_user()
            if not user:
                return api_error("Account not found or disabled", 403)
            if roles and user.role.name != "super_admin" and user.role.name not in roles:
                return api_error("You do not have permission to do this", 403)
            g.user = user
            return fn(*a, **k)
        return wrapper
    return deco


def auth_required(fn):
    return roles_required()(fn)


def optional_user():
    try:
        verify_jwt_in_request(optional=True)
        if get_jwt_identity():
            return _load_user()
    except Exception:
        return None
    return None


# ---------- rate limiting (in-memory, per process) ----------
_hits = defaultdict(deque)


def rate_limit(limit, window=60):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **k):
            if current_app.config.get("RATELIMIT_ENABLED", True):
                key = (request.remote_addr, request.endpoint)
                now = time.time()
                q = _hits[key]
                while q and q[0] <= now - window:
                    q.popleft()
                if len(q) >= limit:
                    return api_error("Too many requests. Please try again shortly.", 429)
                q.append(now)
            return fn(*a, **k)
        return wrapper
    return deco


# ---------- audit / e-mail ----------
def audit(action, entity=None, entity_id=None, details=None, user=None):
    u = user or g.get("user")
    db.session.add(AuditLog(user_id=u.id if u else None, action=action, entity=entity,
                            entity_id=str(entity_id) if entity_id is not None else None,
                            details=(details or "")[:500], ip=request.remote_addr if request else None))


def send_email(to, subject, body):
    cfg = current_app.config
    if not cfg.get("MAIL_SERVER"):
        log.info("[email not sent - MAIL_SERVER unset] to=%s subject=%s", to, subject)
        return False
    try:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = cfg["MAIL_SENDER"], to, subject
        msg.set_content(body)
        with smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=10) as s:
            if cfg["MAIL_USE_TLS"]:
                s.starttls()
            if cfg["MAIL_USERNAME"]:
                s.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
            s.send_message(msg)
        return True
    except Exception:
        log.exception("Failed to send e-mail to %s", to)
        return False


# ---------- secure image upload ----------
ALLOWED_EXT = {"jpg", "jpeg", "png", "webp"}


def save_image(file_storage, subdir, max_px=1200):
    if not file_storage or not file_storage.filename:
        raise ValueError("No file provided")
    ext = file_storage.filename.rsplit(".", 1)[-1].lower() if "." in file_storage.filename else ""
    if ext not in ALLOWED_EXT:
        raise ValueError("Only JPG, PNG or WEBP images are allowed")
    try:
        img = Image.open(file_storage.stream)
        img.verify()
        file_storage.stream.seek(0)
        img = Image.open(file_storage.stream).convert("RGB")
    except Exception:
        raise ValueError("File is not a valid image")
    img.thumbnail((max_px, max_px))
    folder = os.path.join(current_app.config["UPLOAD_DIR"], subdir)
    os.makedirs(folder, exist_ok=True)
    name = f"{uuid.uuid4().hex}.jpg"
    img.save(os.path.join(folder, name), "JPEG", quality=88)
    return f"/uploads/{subdir}/{name}"


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:90] or uuid.uuid4().hex[:8]
