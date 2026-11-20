import hashlib
import hmac
import json

from flask import Blueprint, current_app, g, jsonify, request, send_file

from ..extensions import db
from ..models import Cart, CouponUsage, Order, OrderItem, Payment, Refund, Shipping, Transaction
from ..services import (adjust_stock, calc_totals, cancel_order, cart_lines, create_gateway_order,
                        get_setting, new_order_number, notify, record_payment_failure,
                        record_payment_success, sign_payment, validate_coupon, verify_signature,
                        build_invoice_pdf)
from ..utils import (api_error, audit, auth_required, clean, log, paginate, rate_limit, to_int)
from .auth import _address_from

bp = Blueprint("orders", __name__, url_prefix="/api")

CANCELLABLE = ("pending", "confirmed", "processing")


def _get_order(oid):
    order = db.session.get(Order, oid)
    if not order:
        return None
    if order.user_id != g.user.id and g.user.role.name not in ("super_admin", "store_admin"):
        return None
    return order


def _gateway_info(order):
    cfg = current_app.config
    return {"provider_order_id": order.payment.provider_order_id, "amount": int(round(order.total * 100)),
            "currency": "INR", "key_id": cfg["RAZORPAY_KEY_ID"] or None, "mock": cfg["MOCK_PAYMENTS"],
            "mode": cfg["RAZORPAY_MODE"]}


@bp.post("/orders/checkout")
@auth_required
@rate_limit(20)
def checkout():
    d = request.get_json(silent=True) or {}
    user = g.user
    cart = Cart.query.filter_by(user_id=user.id).first()
    if not cart or not cart.items:
        return api_error("Your cart is empty")
    if get_setting("maintenance_mode") == "true":
        return api_error("The store is temporarily not accepting orders", 503)

    ship, err = _address_from(d.get("shipping_address") or {})
    if err:
        return api_error("Shipping address: " + err)
    if d.get("billing_same_as_shipping", True) or not d.get("billing_address"):
        bill = ship
    else:
        bill, err = _address_from(d["billing_address"])
        if err:
            return api_error("Billing address: " + err)
    delivery = d.get("delivery_option", "standard")
    if delivery not in ("standard", "express"):
        return api_error("Invalid delivery option")
    method = d.get("payment_method")
    if method not in ("cod", "razorpay"):
        return api_error("Choose a payment method")
    if method == "cod" and get_setting("cod_enabled") != "true":
        return api_error("Cash on delivery is currently unavailable")
    if method == "razorpay" and get_setting("razorpay_enabled") != "true":
        return api_error("Online payment is currently unavailable")

    lines = cart_lines(cart)
    for l in lines:
        if not l["available"]:
            return api_error(f"{l['name']} is no longer available. Please remove it from your cart.", 409)
        if l["quantity"] > l["stock"]:
            return api_error(f"Only {l['stock']} left of {l['name']}", 409)
    subtotal = round(sum(l["line_total"] for l in lines), 2)

    coupon, discount = None, 0.0
    if cart.coupon_code:
        try:
            coupon, discount = validate_coupon(cart.coupon_code, subtotal, user.id)
        except ValueError as e:
            return api_error(str(e))
    totals = calc_totals(subtotal, delivery, discount)

    try:
        order = Order(order_number=new_order_number(), user_id=user.id, subtotal=totals["subtotal"],
                      discount=totals["discount"], tax=totals["tax"], shipping_cost=totals["shipping"],
                      total=totals["total"], coupon_code=coupon.code if coupon else None,
                      delivery_option=delivery, shipping_address=json.dumps(ship),
                      billing_address=json.dumps(bill), payment_method=method, payment_status="pending")
        db.session.add(order)
        db.session.flush()
        for ci in list(cart.items):
            v = ci.variant
            db.session.add(OrderItem(order_id=order.id, product_id=v.product_id, variant_id=v.id,
                                     name=v.product.name, size=v.size, color=v.color, price=v.price,
                                     quantity=ci.quantity))
            adjust_stock(v, -ci.quantity, f"Order {order.order_number}", user.id)
            v.product.sold_count = (v.product.sold_count or 0) + ci.quantity
        payment = Payment(order_id=order.id, method=method, status="pending", amount=order.total)
        db.session.add(payment)
        ship_row = Shipping(order_id=order.id)
        ship_row.add_event("pending", "Order placed")
        db.session.add(ship_row)
        if coupon:
            coupon.used_count = (coupon.used_count or 0) + 1
            db.session.add(CouponUsage(coupon_id=coupon.id, user_id=user.id, order_id=order.id,
                                       discount=discount))
        if method == "razorpay":
            payment.provider_order_id = create_gateway_order(order)
        for ci in list(cart.items):
            db.session.delete(ci)
        cart.coupon_code = None
        notify(user.id, f"Order {order.order_number} placed",
               f"Thanks {user.name}! Your order total is {order.total:.2f}.", "order")
        audit("checkout", "order", order.id, f"total={order.total} method={method}")
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        return api_error(str(e), 409)
    except Exception:
        db.session.rollback()
        log.exception("Checkout failed")
        return api_error("We could not place your order. Please try again.", 502)

    resp = {"order": order.to_dict(detail=True)}
    if method == "razorpay":
        resp["gateway"] = _gateway_info(order)
    return jsonify(resp), 201


@bp.get("/orders")
@auth_required
def my_orders():
    q = Order.query.filter_by(user_id=g.user.id).order_by(Order.created_at.desc())
    return jsonify(paginate(q, lambda o: o.to_dict(detail=True)))


@bp.get("/orders/<int:oid>")
@auth_required
def order_detail(oid):
    order = _get_order(oid)
    if not order:
        return api_error("Order not found", 404)
    return jsonify(order.to_dict(detail=True))


@bp.get("/orders/<int:oid>/tracking")
@auth_required
def order_tracking(oid):
    order = _get_order(oid)
    if not order:
        return api_error("Order not found", 404)
    return jsonify({"order_number": order.order_number, "status": order.status,
                    "tracking": order.shipping.to_dict() if order.shipping else None})


@bp.post("/orders/<int:oid>/cancel")
@auth_required
def cancel(oid):
    order = _get_order(oid)
    if not order or order.user_id != g.user.id:
        return api_error("Order not found", 404)
    if order.status not in CANCELLABLE:
        return api_error("This order can no longer be cancelled")
    reason = clean((request.get_json(silent=True) or {}).get("reason"), 200) or "Cancelled by customer"
    cancel_order(order, g.user, reason)
    audit("cancel_order", "order", order.id, reason)
    db.session.commit()
    return jsonify(order.to_dict(detail=True))


@bp.post("/orders/<int:oid>/refund-request")
@auth_required
def refund_request(oid):
    order = _get_order(oid)
    if not order or order.user_id != g.user.id:
        return api_error("Order not found", 404)
    if order.status != "delivered":
        return api_error("Refunds can only be requested for delivered orders")
    if any(r.status in ("pending", "approved", "processed") for r in order.refunds):
        return api_error("A refund request already exists for this order", 409)
    reason = clean((request.get_json(silent=True) or {}).get("reason"), 250)
    if len(reason) < 5:
        return api_error("Please tell us why you want a refund")
    db.session.add(Refund(order_id=order.id, kind="return", amount=order.total, reason=reason))
    audit("refund_request", "order", order.id, reason)
    db.session.commit()
    return jsonify(order.to_dict(detail=True)), 201


@bp.get("/orders/<int:oid>/invoice")
@auth_required
def invoice(oid):
    order = _get_order(oid)
    if not order:
        return api_error("Order not found", 404)
    return send_file(build_invoice_pdf(order), mimetype="application/pdf",
                     download_name=f"invoice-{order.order_number}.pdf")


@bp.post("/orders/<int:oid>/pay")
@auth_required
def retry_payment(oid):
    order = _get_order(oid)
    if not order or order.user_id != g.user.id:
        return api_error("Order not found", 404)
    if order.payment_method != "razorpay" or order.payment_status not in ("failed", "pending") \
            or order.status not in ("pending", "confirmed"):
        return api_error("This order cannot be paid online")
    try:
        order.payment.provider_order_id = create_gateway_order(order)
        order.payment.status = "pending"
        order.payment_status = "pending"
        db.session.commit()
    except Exception:
        db.session.rollback()
        log.exception("Retry payment failed")
        return api_error("Could not start payment. Try again.", 502)
    return jsonify({"order": order.to_dict(detail=True), "gateway": _gateway_info(order)})


# ---------------- payments ----------------
@bp.get("/payments/config")
def payment_config():
    cfg = current_app.config
    return jsonify({"mock": cfg["MOCK_PAYMENTS"], "mode": cfg["RAZORPAY_MODE"],
                    "key_id": cfg["RAZORPAY_KEY_ID"] or None,
                    "cod_enabled": get_setting("cod_enabled") == "true",
                    "online_enabled": get_setting("razorpay_enabled") == "true"})


@bp.post("/payments/verify")
@auth_required
@rate_limit(20)
def verify_payment():
    d = request.get_json(silent=True) or {}
    order = _get_order(to_int(d.get("order_id"), 0))
    if not order or order.user_id != g.user.id or not order.payment:
        return api_error("Order not found", 404)
    rz_order, rz_pay, sig = d.get("razorpay_order_id"), d.get("razorpay_payment_id"), d.get("razorpay_signature")
    if rz_order != order.payment.provider_order_id:
        return api_error("Payment does not match this order", 400)
    if not verify_signature(rz_order, rz_pay, sig):
        record_payment_failure(order, "Signature verification failed")
        audit("payment_verify_failed", "order", order.id)
        db.session.commit()
        return api_error("Payment verification failed", 400)
    record_payment_success(order, rz_pay)
    audit("payment_verified", "order", order.id)
    db.session.commit()
    return jsonify(order.to_dict(detail=True))


@bp.post("/payments/failure")
@auth_required
def payment_failure():
    d = request.get_json(silent=True) or {}
    order = _get_order(to_int(d.get("order_id"), 0))
    if not order or order.user_id != g.user.id or not order.payment:
        return api_error("Order not found", 404)
    if order.payment.status == "paid":
        return api_error("This order is already paid", 409)
    record_payment_failure(order, clean(d.get("reason"), 200) or "Payment failed or cancelled")
    db.session.commit()
    return jsonify(order.to_dict(detail=True))


@bp.post("/payments/sandbox/simulate")
@auth_required
def sandbox_simulate():
    """Local mock gateway: only available when MOCK_PAYMENTS is on (never with live keys)."""
    if not current_app.config["MOCK_PAYMENTS"]:
        return api_error("Not available", 404)
    d = request.get_json(silent=True) or {}
    order = _get_order(to_int(d.get("order_id"), 0))
    if not order or order.user_id != g.user.id or not order.payment or not order.payment.provider_order_id:
        return api_error("Order not found", 404)
    if d.get("outcome") == "failure":
        record_payment_failure(order, "Simulated sandbox failure")
    else:
        pay_id = "pay_mock_" + order.order_number[-6:]
        record_payment_success_via_signature(order, pay_id)
    db.session.commit()
    return jsonify(order.to_dict(detail=True))


def record_payment_success_via_signature(order, pay_id):
    """Run the exact same signature check real payments go through."""
    sig = sign_payment(order.payment.provider_order_id, pay_id)
    assert verify_signature(order.payment.provider_order_id, pay_id, sig)
    record_payment_success(order, pay_id, "Sandbox payment")


@bp.get("/payments/transactions")
@auth_required
def my_transactions():
    rows = (Transaction.query.join(Payment).join(Order, Order.id == Payment.order_id)
            .filter(Order.user_id == g.user.id).order_by(Transaction.created_at.desc()).limit(100))
    return jsonify([{**t.to_dict(), "order_number": t.payment.order.order_number} for t in rows])


def _webhook_secret():
    cfg = current_app.config
    return cfg.get("RAZORPAY_WEBHOOK_SECRET") or (cfg["MOCK_RAZORPAY_SECRET"] if cfg["MOCK_PAYMENTS"] else "")


@bp.post("/payments/webhook")
def payment_webhook():
    """Razorpay server-to-server webhook: confirms payments even if the customer closes the browser.
    Authenticated by the X-Razorpay-Signature HMAC of the raw body (no JWT)."""
    secret = _webhook_secret()
    if not secret:
        return api_error("Webhook is not configured", 503)
    raw = request.get_data()
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, request.headers.get("X-Razorpay-Signature", "")):
        log.warning("Webhook rejected: bad signature")
        return api_error("Invalid signature", 400)
    event = request.get_json(silent=True) or {}
    entity = (((event.get("payload") or {}).get("payment") or {}).get("entity")) or {}
    provider_order = entity.get("order_id")
    payment = Payment.query.filter_by(provider_order_id=provider_order).first() if provider_order else None
    if not payment:
        return jsonify({"status": "ignored"})
    order, kind = payment.order, event.get("event")
    if kind in ("payment.captured", "order.paid"):
        if entity.get("amount") is not None and to_int(entity["amount"]) != int(round(order.total * 100)):
            log.warning("Webhook amount mismatch for %s", order.order_number)
            audit("webhook_amount_mismatch", "order", order.id)
            db.session.commit()
            return jsonify({"status": "amount_mismatch"})
        if order.status == "cancelled":
            log.warning("Payment received for cancelled order %s - refund manually", order.order_number)
            return jsonify({"status": "order_cancelled"})
        record_payment_success(order, entity.get("id") or "webhook", "Confirmed via webhook")
    elif kind == "payment.failed":
        record_payment_failure(order, entity.get("error_description") or "Payment failed")
    else:
        return jsonify({"status": "ignored"})
    audit("payment_webhook", "order", order.id, kind)
    db.session.commit()
    return jsonify({"status": "ok"})
