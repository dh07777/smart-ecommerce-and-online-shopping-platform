from app.extensions import db
from app.models import Inventory, Order
from app.services import sign_payment

from .conftest import checkout


def _fill(client, auth, pid=1, qty=2):
    client.post("/api/cart/items", headers=auth, json={"product_id": pid, "quantity": qty})


def test_checkout_cod_reduces_stock_and_clears_cart(client, auth, app):
    _fill(client, auth)
    r = checkout(client, auth)
    assert r.status_code == 201
    o = r.get_json()["order"]
    assert o["total"] == 2360 and o["payment_status"] == "pending" and o["payment"]["method"] == "cod"
    with app.app_context():
        assert Inventory.query.filter_by(variant_id=1).first().quantity == 8
    assert client.get("/api/cart", headers=auth).get_json()["count"] == 0


def test_checkout_empty_cart_and_bad_address(client, auth):
    assert checkout(client, auth).status_code == 400
    _fill(client, auth)
    r = client.post("/api/orders/checkout", headers=auth, json={"shipping_address": {}, "payment_method": "cod"})
    assert r.status_code == 400


def test_checkout_with_coupon(client, auth):
    _fill(client, auth, qty=1)
    client.post("/api/cart/coupon", headers=auth, json={"code": "TEN"})
    o = checkout(client, auth).get_json()["order"]
    assert o["discount"] == 100 and o["coupon_code"] == "TEN"
    _fill(client, auth, qty=1)
    r = client.post("/api/cart/coupon", headers=auth, json={"code": "TEN"})
    assert r.status_code == 400  # per-user limit reached


def test_payment_sandbox_verify_and_bad_signature(client, auth):
    _fill(client, auth)
    data = checkout(client, auth, "razorpay").get_json()
    oid, prov = data["order"]["id"], data["gateway"]["provider_order_id"]
    assert data["gateway"]["mock"] is True
    bad = client.post("/api/payments/verify", headers=auth, json={
        "order_id": oid, "razorpay_order_id": prov, "razorpay_payment_id": "pay_x", "razorpay_signature": "forged"})
    assert bad.status_code == 400
    assert client.get(f"/api/orders/{oid}", headers=auth).get_json()["payment_status"] == "failed"
    sig = sign_payment(prov, "pay_ok")
    ok = client.post("/api/payments/verify", headers=auth, json={
        "order_id": oid, "razorpay_order_id": prov, "razorpay_payment_id": "pay_ok", "razorpay_signature": sig})
    body = ok.get_json()
    assert ok.status_code == 200 and body["payment_status"] == "paid" and body["status"] == "confirmed"


def test_payment_failure_then_retry(client, auth):
    _fill(client, auth)
    oid = checkout(client, auth, "razorpay").get_json()["order"]["id"]
    assert client.post("/api/payments/failure", headers=auth, json={"order_id": oid}).get_json()["payment_status"] == "failed"
    assert client.post(f"/api/orders/{oid}/pay", headers=auth).status_code == 200
    r = client.post("/api/payments/sandbox/simulate", headers=auth, json={"order_id": oid, "outcome": "success"})
    assert r.get_json()["payment_status"] == "paid"


def test_cancel_restocks_and_creates_refund_for_paid(client, auth, app):
    _fill(client, auth)
    oid = checkout(client, auth, "razorpay").get_json()["order"]["id"]
    client.post("/api/payments/sandbox/simulate", headers=auth, json={"order_id": oid, "outcome": "success"})
    r = client.post(f"/api/orders/{oid}/cancel", headers=auth, json={})
    body = r.get_json()
    assert body["status"] == "cancelled" and body["payment_status"] == "refund_pending"
    assert body["refunds"][0]["status"] == "pending"
    with app.app_context():
        assert Inventory.query.filter_by(variant_id=1).first().quantity == 10


def test_cannot_view_other_users_order(client, auth):
    _fill(client, auth)
    oid = checkout(client, auth).get_json()["order"]["id"]
    other = client.post("/api/auth/register", json={"name": "Other One", "email": "o@test.com", "password": "Passw0rd!"}).get_json()
    h2 = {"Authorization": "Bearer " + other["access_token"]}
    assert client.get(f"/api/orders/{oid}", headers=h2).status_code == 404


def test_invoice_pdf(client, auth):
    _fill(client, auth)
    oid = checkout(client, auth).get_json()["order"]["id"]
    r = client.get(f"/api/orders/{oid}/invoice", headers=auth)
    assert r.status_code == 200 and r.data[:4] == b"%PDF"


def test_order_status_flow_by_admin(client, auth, admin):
    _fill(client, auth)
    oid = checkout(client, auth).get_json()["order"]["id"]
    for st in ("confirmed", "processing", "shipped", "out_for_delivery", "delivered"):
        r = client.patch(f"/api/admin/orders/{oid}/status", headers=admin, json={"status": st})
        assert r.status_code == 200, r.get_json()
    d = r.get_json()
    assert d["payment_status"] == "paid" and d["tracking"]["tracking_number"]
    assert client.patch(f"/api/admin/orders/{oid}/status", headers=admin, json={"status": "pending"}).status_code == 400
    assert client.post(f"/api/orders/{oid}/refund-request", headers=auth, json={"reason": "Not satisfied"}).status_code == 201
