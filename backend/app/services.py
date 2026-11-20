"""Business logic shared between routes (pricing, coupons, stock, payments, invoices)."""
import hashlib
import hmac
import io
import json
import logging
import secrets
import urllib.request
import base64
from datetime import datetime

from flask import current_app
from PIL import Image, ImageDraw, ImageFont

from .extensions import db, utcnow
from .models import (Coupon, CouponUsage, Inventory, Notification, Payment, Product, ProductVariant, Refund,
                     Role, Setting, StockHistory, Transaction, User)
from .utils import send_email, to_int

log = logging.getLogger("shopsphere")

DEFAULT_SETTINGS = {
    "store_name": "ShopSphere", "store_email": "support@shopsphere.local", "store_phone": "+91 90000 00000",
    "store_address": "12 Market Street, Bengaluru, India", "currency_symbol": "₹",
    "tax_rate": "18", "free_shipping_threshold": "999", "standard_shipping": "49", "express_shipping": "149",
    "cod_enabled": "true", "razorpay_enabled": "true", "email_notifications": "true",
    "low_stock_default": "10", "maintenance_mode": "false",
    "hero_title": "Discover products you'll love", "hero_subtitle": "Free shipping above ₹999 · Easy returns",
}
PUBLIC_SETTING_KEYS = ["store_name", "store_email", "store_phone", "currency_symbol", "tax_rate",
                       "free_shipping_threshold", "standard_shipping", "express_shipping", "cod_enabled",
                       "razorpay_enabled", "hero_title", "hero_subtitle"]


def get_setting(key):
    row = db.session.get(Setting, key)
    return row.value if row else DEFAULT_SETTINGS.get(key)


def get_role(name):
    role = Role.query.filter_by(name=name).first()
    if not role:
        role = Role(name=name)
        db.session.add(role)
        db.session.flush()
    return role


# ---------- notifications ----------
def notify(user_id, title, message, kind="info", email=True):
    db.session.add(Notification(user_id=user_id, title=title, message=message, kind=kind))
    if email and get_setting("email_notifications") == "true":
        user = db.session.get(User, user_id)
        if user:
            send_email(user.email, title, message)


def notify_staff(title, message, kind="inventory"):
    for u in User.query.join(Role).filter(Role.name.in_(["super_admin", "store_admin"]), User.is_active.is_(True)):
        db.session.add(Notification(user_id=u.id, title=title, message=message, kind=kind))


# ---------- stock ----------
def adjust_stock(variant, delta, reason, user_id=None):
    inv = variant.inventory
    if inv is None:
        inv = Inventory(variant=variant, quantity=0, low_stock_threshold=int(get_setting("low_stock_default") or 10))
        db.session.add(inv)
    new_qty = (inv.quantity or 0) + delta
    if new_qty < 0:
        raise ValueError(f"Insufficient stock for {variant.product.name}")
    inv.quantity = new_qty
    db.session.add(StockHistory(variant=variant, change=delta, quantity_after=new_qty, reason=reason, user_id=user_id))
    if delta < 0 and new_qty <= (inv.low_stock_threshold or 0):
        notify_staff("Low stock alert", f"{variant.product.name} ({variant.sku}) has only {new_qty} left.")
    return new_qty


# ---------- pricing ----------
def _line(v, qty, line_id):
    p = v.product
    unit = v.price
    return {"id": line_id, "variant_id": v.id, "product_id": p.id, "name": p.name, "slug": p.slug,
            "image": p.images[0].url if p.images else None, "size": v.size, "color": v.color,
            "unit_price": unit, "quantity": qty, "stock": v.inventory.quantity if v.inventory else 0,
            "available": p.is_active and v.is_active, "line_total": round(unit * qty, 2)}


def cart_lines(cart):
    return [_line(ci.variant, ci.quantity, ci.id) for ci in cart.items]


def resolve_entries(entries):
    """Turn [{variant_id|product_id, quantity}] from a guest cart into {variant_id: qty}."""
    merged = {}
    for e in (entries or [])[:50]:
        if not isinstance(e, dict):
            continue
        v = None
        if e.get("variant_id"):
            v = db.session.get(ProductVariant, to_int(e["variant_id"], 0))
        elif e.get("product_id"):
            p = db.session.get(Product, to_int(e["product_id"], 0))
            v = next((x for x in p.variants if x.is_active), None) if p else None
        qty = to_int(e.get("quantity"), 1) or 0
        if not v or qty < 1 or not (v.is_active and v.product.is_active):
            continue
        merged[v.id] = min(merged.get(v.id, 0) + qty, 20)
    return merged


def guest_summary(entries, delivery="standard"):
    lines = []
    for vid, qty in resolve_entries(entries).items():
        lines.append(_line(db.session.get(ProductVariant, vid), qty, f"v{vid}"))
    subtotal = sum(l["line_total"] for l in lines)
    return {"items": lines, "count": sum(l["quantity"] for l in lines), "coupon_code": None,
            "coupon_error": None, "delivery_option": delivery, **calc_totals(subtotal, delivery, 0.0)}


def validate_coupon(code, subtotal, user_id):
    """Return (coupon, discount). Raises ValueError with a user-friendly message."""
    c = Coupon.query.filter(db.func.upper(Coupon.code) == (code or "").strip().upper()).first()
    if not c or not c.is_active:
        raise ValueError("Invalid coupon code")
    if c.expires_at and c.expires_at < utcnow():
        raise ValueError("This coupon has expired")
    if c.usage_limit is not None and c.used_count >= c.usage_limit:
        raise ValueError("This coupon has reached its usage limit")
    if subtotal < (c.min_order_value or 0):
        raise ValueError(f"Minimum order value for this coupon is {c.min_order_value:.0f}")
    used = CouponUsage.query.filter_by(coupon_id=c.id, user_id=user_id).count()
    if c.per_user_limit is not None and used >= c.per_user_limit:
        raise ValueError("You have already used this coupon")
    disc = subtotal * c.value / 100 if c.discount_type == "percent" else c.value
    if c.max_discount:
        disc = min(disc, c.max_discount)
    return c, round(min(disc, subtotal), 2)


def calc_totals(subtotal, delivery="standard", discount=0.0):
    rate = float(get_setting("tax_rate") or 0)
    threshold = float(get_setting("free_shipping_threshold") or 0)
    if subtotal <= 0:
        ship = 0.0
    elif delivery == "express":
        ship = float(get_setting("express_shipping") or 0)
    else:
        ship = 0.0 if subtotal >= threshold else float(get_setting("standard_shipping") or 0)
    taxable = max(subtotal - discount, 0)
    tax = round(taxable * rate / 100, 2)
    return {"subtotal": round(subtotal, 2), "discount": round(discount, 2), "tax": tax,
            "shipping": round(ship, 2), "total": round(taxable + tax + ship, 2)}


def cart_summary(cart, delivery="standard"):
    lines = cart_lines(cart)
    subtotal = sum(l["line_total"] for l in lines)
    discount, coupon_error = 0.0, None
    if cart.coupon_code and lines:
        try:
            _, discount = validate_coupon(cart.coupon_code, subtotal, cart.user_id)
        except ValueError as e:
            coupon_error = str(e)
    totals = calc_totals(subtotal, delivery, discount)
    return {"items": lines, "count": sum(l["quantity"] for l in lines), "coupon_code": cart.coupon_code,
            "coupon_error": coupon_error, "delivery_option": delivery, **totals}


# ---------- orders ----------
def new_order_number():
    return f"SS-{utcnow().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"


def cancel_order(order, actor, reason="Cancelled"):
    """Restock, release coupon, create refund if paid. Caller commits."""
    for it in order.items:
        if it.variant:
            adjust_stock(it.variant, it.quantity, f"Cancelled {order.order_number}", actor.id if actor else None)
        if it.product:
            it.product.sold_count = max((it.product.sold_count or 0) - it.quantity, 0)
    usage = CouponUsage.query.filter_by(order_id=order.id).first()
    if usage:
        c = db.session.get(Coupon, usage.coupon_id)
        if c:
            c.used_count = max((c.used_count or 0) - 1, 0)
        db.session.delete(usage)
    order.status = "cancelled"
    if order.shipping:
        order.shipping.add_event("cancelled", reason)
    if order.payment_status == "paid":
        db.session.add(Refund(order_id=order.id, kind="cancellation", amount=order.total,
                              reason=reason, status="pending"))
        order.payment_status = "refund_pending"
        if order.payment:
            order.payment.status = "refund_pending"
    elif order.payment_status == "pending" and order.payment:
        order.payment_status = "cancelled"
        order.payment.status = "cancelled"
    notify(order.user_id, f"Order {order.order_number} cancelled", reason, "order")


def record_payment_success(order, provider_payment_id, note="Payment captured"):
    pay = order.payment
    if pay.status == "paid":
        return
    pay.status = "paid"
    pay.provider_payment_id = provider_payment_id
    order.payment_status = "paid"
    if order.status == "pending":
        order.status = "confirmed"
        if order.shipping:
            order.shipping.add_event("confirmed", "Payment received")
    db.session.add(Transaction(payment_id=pay.id, kind="charge", amount=pay.amount, status="success",
                               reference=provider_payment_id, note=note))
    notify(order.user_id, "Payment confirmed", f"We received {pay.amount:.2f} for order {order.order_number}.", "payment")


def record_payment_failure(order, reason="Payment failed"):
    pay = order.payment
    if pay.status == "paid":
        return
    pay.status = "failed"
    order.payment_status = "failed"
    db.session.add(Transaction(payment_id=pay.id, kind="failure", amount=pay.amount, status="failed",
                               reference=pay.provider_order_id, note=reason[:250]))
    notify(order.user_id, "Payment failed", f"Payment for order {order.order_number} did not complete. You can retry from your orders page.", "payment")


# ---------- Razorpay (sandbox / live separated by config) ----------
def create_gateway_order(order):
    """Create a Razorpay order (or a mock one in sandbox without keys). Returns provider order id."""
    cfg = current_app.config
    amount = int(round(order.total * 100))
    if cfg["MOCK_PAYMENTS"]:
        return "order_mock_" + secrets.token_hex(7)
    body = json.dumps({"amount": amount, "currency": "INR", "receipt": order.order_number}).encode()
    req = urllib.request.Request("https://api.razorpay.com/v1/orders", data=body, method="POST")
    token = base64.b64encode(f"{cfg['RAZORPAY_KEY_ID']}:{cfg['RAZORPAY_KEY_SECRET']}".encode()).decode()
    req.add_header("Authorization", "Basic " + token)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())["id"]


def signing_secret():
    cfg = current_app.config
    return cfg["MOCK_RAZORPAY_SECRET"] if cfg["MOCK_PAYMENTS"] else cfg["RAZORPAY_KEY_SECRET"]


def sign_payment(provider_order_id, provider_payment_id):
    return hmac.new(signing_secret().encode(), f"{provider_order_id}|{provider_payment_id}".encode(),
                    hashlib.sha256).hexdigest()


def verify_signature(provider_order_id, provider_payment_id, signature):
    expected = sign_payment(provider_order_id, provider_payment_id)
    return hmac.compare_digest(expected, signature or "")


# ---------- invoice PDF (Pillow) ----------
def _font(size, bold=False):
    for name in (("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"), "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def build_invoice_pdf(order):
    W, H = 1240, 1754
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f_big, f_h, f_n = _font(48, True), _font(26, True), _font(24)
    d.rectangle([0, 0, W, 150], fill=(79, 70, 229))
    d.text((60, 45), get_setting("store_name") or "ShopSphere", font=f_big, fill="white")
    d.text((W - 360, 60), "TAX INVOICE", font=f_h, fill="white")
    y = 190
    ship = json.loads(order.shipping_address)
    d.text((60, y), f"Invoice for order {order.order_number}", font=f_h, fill="black"); y += 40
    d.text((60, y), f"Date: {order.created_at.strftime('%d %b %Y')}   Status: {order.status}   Payment: {order.payment_method} ({order.payment_status})", font=f_n, fill=(80, 80, 80)); y += 60
    d.text((60, y), "Bill / Ship to", font=f_h, fill="black"); y += 38
    for line in [ship.get("full_name"), ship.get("line1"), ship.get("line2"),
                 f"{ship.get('city')}, {ship.get('state')} {ship.get('postal_code')}", ship.get("phone")]:
        if line:
            d.text((60, y), str(line), font=f_n, fill=(50, 50, 50)); y += 32
    y += 30
    d.rectangle([60, y, W - 60, y + 50], fill=(238, 238, 252))
    for x, t in ((70, "Item"), (700, "Qty"), (820, "Price"), (1000, "Total")):
        d.text((x, y + 10), t, font=f_h, fill="black")
    y += 70
    for it in order.items:
        label = it.name + (f" ({it.size}/{it.color})" if it.size or it.color else "")
        d.text((70, y), label[:44], font=f_n, fill="black")
        d.text((700, y), str(it.quantity), font=f_n, fill="black")
        d.text((820, y), f"{it.price:,.2f}", font=f_n, fill="black")
        d.text((1000, y), f"{it.price * it.quantity:,.2f}", font=f_n, fill="black")
        y += 44
    y += 20
    d.line([60, y, W - 60, y], fill=(200, 200, 200), width=2); y += 25
    rows = [("Subtotal", order.subtotal), ("Discount", -order.discount), ("Tax", order.tax),
            ("Shipping", order.shipping_cost)]
    for label, val in rows:
        d.text((760, y), label, font=f_n, fill="black")
        d.text((1000, y), f"{val:,.2f}", font=f_n, fill="black"); y += 38
    d.text((760, y + 10), "Grand Total", font=f_h, fill="black")
    d.text((1000, y + 10), f"{order.total:,.2f}", font=f_h, fill="black")
    d.text((60, H - 100), "Thank you for shopping with us. This is a computer generated invoice.", font=f_n, fill=(120, 120, 120))
    buf = io.BytesIO()
    img.save(buf, "PDF", resolution=150.0)
    buf.seek(0)
    return buf
