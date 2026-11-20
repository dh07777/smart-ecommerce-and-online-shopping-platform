import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import CartItem, Inventory, User
from .conftest import ADDRESS, checkout, login


def test_customer_blocked_from_admin(client, auth):
    for url in ("/api/admin/dashboard", "/api/admin/orders", "/api/admin/customers", "/api/admin/settings"):
        assert client.get(url, headers=auth).status_code == 403
    assert client.get("/api/admin/dashboard").status_code == 401


def test_staff_endpoints_need_super_admin(client, admin):
    assert client.get("/api/admin/staff", headers=admin).status_code == 403
    sa = login(client, "admin@test.com")
    assert client.get("/api/admin/staff", headers=sa).status_code == 200


def test_dashboard_numbers_come_from_db(client, auth, admin):
    client.post("/api/cart/items", headers=auth, json={"product_id": 1, "quantity": 1})
    checkout(client, auth)
    d = client.get("/api/admin/dashboard", headers=admin).get_json()
    assert d["total_orders"] == 1 and d["pending_orders"] == 1 and d["total_products"] == 2
    assert d["total_revenue"] == 0  # COD unpaid is not revenue yet


def test_admin_product_crud(client, admin):
    r = client.post("/api/admin/products", headers=admin, json={
        "name": "New Gizmo", "price": 499, "category_id": 1, "variants": [{"size": "L", "color": "Blue", "stock": 7}]})
    assert r.status_code == 201
    p = r.get_json()
    assert p["stock"] == 7 and p["variants"][0]["sku"]
    assert client.put(f"/api/admin/products/{p['id']}", headers=admin, json={"price": 599}).get_json()["price"] == 599
    assert client.post("/api/admin/products", headers=admin, json={"name": "Bad", "price": -5, "category_id": 1}).status_code == 400
    assert client.delete(f"/api/admin/products/{p['id']}", headers=admin).status_code == 200
    assert client.get(f"/api/products/{p['slug']}").status_code == 404


def test_inventory_update_logs_history(client, admin):
    assert client.patch("/api/admin/inventory/1", headers=admin, json={"quantity": 3, "reason": "recount"}).get_json()["stock"] == 3
    assert client.patch("/api/admin/inventory/1", headers=admin, json={"delta": -10}).status_code == 400
    h = client.get("/api/admin/inventory/history", headers=admin).get_json()
    assert h["items"][0]["reason"] == "recount"
    assert client.get("/api/admin/inventory?low_stock=1", headers=admin).status_code == 200


def test_coupon_management(client, admin):
    r = client.post("/api/admin/coupons", headers=admin, json={"code": "fixed50", "discount_type": "fixed", "value": 50})
    assert r.status_code == 201 and r.get_json()["code"] == "FIXED50"
    assert client.post("/api/admin/coupons", headers=admin, json={"code": "FIXED50", "discount_type": "fixed", "value": 5}).status_code == 400
    assert client.post("/api/admin/coupons", headers=admin, json={"code": "BIG", "discount_type": "percent", "value": 150}).status_code == 400


def test_review_lifecycle_and_moderation(client, auth, admin):
    assert client.post("/api/products/1/reviews", headers=auth, json={"rating": 5, "body": "Great stuff"}).status_code == 201
    assert client.post("/api/products/1/reviews", headers=auth, json={"rating": 5, "body": "Again"}).status_code == 409
    p = client.get("/api/products/widget-one").get_json()
    assert p["rating"] == 5 and p["review_count"] == 1
    rid = client.get("/api/products/1/reviews").get_json()["items"][0]["id"]
    assert client.patch(f"/api/admin/reviews/{rid}", headers=admin, json={"status": "rejected"}).status_code == 200
    assert client.get("/api/products/widget-one").get_json()["review_count"] == 0
    spam = client.post("/api/products/2/reviews", headers=auth, json={"rating": 1, "body": "visit http://spam.example"})
    assert spam.get_json()["status"] == "pending"


def test_support_ticket_and_notifications(client, auth, admin):
    r = client.post("/api/support/contact", headers=auth, json={"subject": "Help", "message": "I need some help please"})
    assert r.status_code == 201
    tid = r.get_json()["id"]
    assert client.post(f"/api/admin/tickets/{tid}/reply", headers=admin, json={"message": "On it"}).status_code == 200
    notes = client.get("/api/notifications", headers=auth).get_json()
    assert notes["unread"] >= 1


def test_export_csv(client, admin):
    r = client.get("/api/admin/analytics/export?type=products", headers=admin)
    assert r.status_code == 200 and b"Widget One" in r.data


def test_analytics_endpoints(client, admin):
    for u in ("sales?period=monthly", "top-products", "by-category", "customers", "orders"):
        assert client.get(f"/api/admin/analytics/{u}", headers=admin).status_code == 200


# ---------- database-level constraints ----------
def test_db_unique_email(app):
    with app.app_context():
        existing = User.query.first()
        db.session.add(User(name="Dup", email=existing.email, password_hash="x", role_id=existing.role_id))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_db_negative_stock_rejected(app):
    with app.app_context():
        inv = Inventory.query.first()
        inv.quantity = -1
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_db_cart_quantity_check(app):
    with app.app_context():
        db.session.add(CartItem(cart_id=1, variant_id=1, quantity=0))
        with pytest.raises(Exception):
            db.session.commit()
        db.session.rollback()
