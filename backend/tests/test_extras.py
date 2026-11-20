import hashlib
import hmac
import json

from app.extensions import db
from app.models import Notification, Payment
from app.services import sign_payment

from .conftest import checkout, login, register


def _signed(app, body: dict):
    raw = json.dumps(body).encode()
    sig = hmac.new(app.config["MOCK_RAZORPAY_SECRET"].encode(), raw, hashlib.sha256).hexdigest()
    return {"data": raw, "content_type": "application/json", "headers": {"X-Razorpay-Signature": sig}}


def _razorpay_order(client, auth):
    client.post("/api/cart/items", headers=auth, json={"product_id": 1, "quantity": 2})
    d = checkout(client, auth, "razorpay").get_json()
    return d["order"]["id"], d["gateway"]["provider_order_id"]


# ---------------- webhook ----------------
def test_webhook_rejects_bad_signature(client, auth):
    _, prov = _razorpay_order(client, auth)
    r = client.post("/api/payments/webhook", data=b"{}", content_type="application/json",
                    headers={"X-Razorpay-Signature": "forged"})
    assert r.status_code == 400


def test_webhook_marks_paid_and_is_idempotent(client, auth, app):
    oid, prov = _razorpay_order(client, auth)
    body = {"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_w1", "order_id": prov, "amount": 236000}}}}
    assert client.post("/api/payments/webhook", **_signed(app, body)).get_json()["status"] == "ok"
    assert client.post("/api/payments/webhook", **_signed(app, body)).status_code == 200
    o = client.get(f"/api/orders/{oid}", headers=auth).get_json()
    assert o["payment_status"] == "paid" and o["status"] == "confirmed"
    assert len([t for t in o["payment"]["transactions"] if t["kind"] == "charge"]) == 1


def test_webhook_amount_mismatch_and_failure(client, auth, app):
    oid, prov = _razorpay_order(client, auth)
    bad = {"event": "payment.captured", "payload": {"payment": {"entity": {"id": "p", "order_id": prov, "amount": 100}}}}
    assert client.post("/api/payments/webhook", **_signed(app, bad)).get_json()["status"] == "amount_mismatch"
    assert client.get(f"/api/orders/{oid}", headers=auth).get_json()["payment_status"] == "pending"
    fail = {"event": "payment.failed", "payload": {"payment": {"entity": {"id": "p", "order_id": prov, "error_description": "declined"}}}}
    client.post("/api/payments/webhook", **_signed(app, fail))
    assert client.get(f"/api/orders/{oid}", headers=auth).get_json()["payment_status"] == "failed"


def test_webhook_unknown_order_ignored(client, app):
    body = {"event": "payment.captured", "payload": {"payment": {"entity": {"id": "p", "order_id": "order_nope", "amount": 1}}}}
    assert client.post("/api/payments/webhook", **_signed(app, body)).get_json()["status"] == "ignored"


# ---------------- guest cart ----------------
def test_guest_cart_summary_uses_db_prices(client):
    r = client.post("/api/cart/guest", json={"items": [{"product_id": 1, "quantity": 2}, {"variant_id": 2, "quantity": 1}, {"variant_id": 999, "quantity": 1}]})
    d = r.get_json()
    assert r.status_code == 200 and d["count"] == 3 and d["subtotal"] == 2250
    assert d["items"][0]["id"].startswith("v")


def test_guest_cart_merges_on_login_respecting_stock(client, auth):
    r = client.post("/api/cart/merge", headers=auth, json={"items": [{"variant_id": 1, "quantity": 3}, {"variant_id": 2, "quantity": 9}]})
    items = {i["variant_id"]: i["quantity"] for i in r.get_json()["items"]}
    assert items == {1: 3, 2: 2}  # variant 2 only has 2 in stock
    r = client.post("/api/cart/merge", headers=auth, json={"items": [{"variant_id": 1, "quantity": 2}]})
    assert {i["variant_id"]: i["quantity"] for i in r.get_json()["items"]}[1] == 5


# ---------------- promotions & newsletter ----------------
def test_promotion_broadcast_respects_opt_out(client, auth, admin, app):
    other = register(client, "optout@test.com")
    assert client.put("/api/auth/me", headers=other, json={"promo_opt_in": False}).get_json()["promo_opt_in"] is False
    r = client.post("/api/admin/promotions", headers=admin, json={"title": "Big Sale", "message": "Everything 20% off", "audience": "customers"})
    assert r.status_code == 201 and r.get_json()["notifications_sent"] == 1
    notes = client.get("/api/notifications", headers=auth).get_json()["items"]
    assert any(n["kind"] == "promo" and n["title"] == "Big Sale" for n in notes)
    assert not any(n["kind"] == "promo" for n in client.get("/api/notifications", headers=other).get_json()["items"])
    assert client.get("/api/admin/promotions", headers=admin).get_json()["total"] == 1


def test_promotion_requires_staff_and_valid_input(client, auth, admin):
    assert client.post("/api/admin/promotions", headers=auth, json={"title": "x", "message": "y"}).status_code == 403
    assert client.post("/api/admin/promotions", headers=admin, json={"title": "", "message": ""}).status_code == 400
    assert client.post("/api/admin/promotions", headers=admin, json={"title": "Hello", "message": "World!!", "audience": "nobody"}).status_code == 400


def test_newsletter_subscribe_list_unsubscribe(client, admin):
    assert client.post("/api/newsletter", json={"email": "fan@test.com"}).status_code == 200
    assert client.post("/api/newsletter", json={"email": "not-an-email"}).status_code == 400
    subs = client.get("/api/admin/subscribers", headers=admin).get_json()
    assert subs["total"] == 1 and subs["items"][0]["email"] == "fan@test.com"
    client.post("/api/newsletter/unsubscribe", json={"email": "fan@test.com"})
    assert client.get("/api/admin/subscribers", headers=admin).get_json()["total"] == 0


# ---------------- recently viewed + recommendations ----------------
def test_recently_viewed_and_recommendations(client, auth):
    client.get("/api/products/widget-one", headers=auth)
    rv = client.get("/api/products/recently-viewed", headers=auth).get_json()
    assert [p["slug"] for p in rv] == ["widget-one"]
    recs = client.get("/api/products/recommendations", headers=auth).get_json()
    assert "widget-two" in [p["slug"] for p in recs]
    assert client.get("/api/products/recommendations").status_code == 200  # anonymous works too


# ---------------- seller orders ----------------
def test_seller_sees_only_own_orders(client, auth, app):
    from app.models import Product, Seller, User
    from app.services import get_role
    from werkzeug.security import generate_password_hash
    with app.app_context():
        u = User(name="Sel", email="sel@test.com", role=get_role("seller"), password_hash=generate_password_hash("Passw0rd!"))
        db.session.add(u)
        db.session.flush()
        s = Seller(user_id=u.id, store_name="Sel Store", is_verified=True)
        db.session.add(s)
        db.session.flush()
        Product.query.get(1).seller_id = s.id
        db.session.commit()
    client.post("/api/cart/items", headers=auth, json={"product_id": 1, "quantity": 1})
    client.post("/api/cart/items", headers=auth, json={"product_id": 2, "quantity": 1})
    checkout(client, auth)
    h = login(client, "sel@test.com")
    orders = client.get("/api/admin/seller/orders", headers=h).get_json()
    assert len(orders) == 1 and [i["name"] for i in orders[0]["items"]] == ["Widget One"]
    assert orders[0]["seller_total"] == 1000
    assert client.get("/api/admin/seller/orders", headers=auth).status_code == 403
