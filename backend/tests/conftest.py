import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import (Brand, Category, Coupon, Inventory, Product, ProductVariant, Role, User, ROLES)
from app.services import get_role


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        for r in ROLES:
            db.session.add(Role(name=r))
        cat = Category(name="Gadgets", slug="gadgets")
        brand = Brand(name="Acme", slug="acme")
        db.session.add_all([cat, brand])
        db.session.flush()
        for i, (name, price, qty) in enumerate([("Widget One", 1000.0, 10), ("Widget Two", 250.0, 2)], start=1):
            p = Product(name=name, slug=name.lower().replace(" ", "-"), description="A test widget",
                        price=price, category_id=cat.id, brand_id=brand.id)
            db.session.add(p)
            db.session.flush()
            v = ProductVariant(product_id=p.id, sku=f"T-{i}", size="M", color="Red")
            db.session.add(v)
            db.session.flush()
            db.session.add(Inventory(variant_id=v.id, quantity=qty, low_stock_threshold=1))
        db.session.add(Coupon(code="TEN", discount_type="percent", value=10, min_order_value=500))
        for email, role in (("admin@test.com", "super_admin"), ("manager@test.com", "store_admin")):
            db.session.add(User(name=role, email=email, role=get_role(role),
                                password_hash=generate_password_hash("Passw0rd!")))
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def register(client, email="buyer@test.com", password="Passw0rd!"):
    r = client.post("/api/auth/register", json={"name": "Test Buyer", "email": email, "password": password})
    assert r.status_code == 201, r.get_json()
    return {"Authorization": "Bearer " + r.get_json()["access_token"]}


def login(client, email, password="Passw0rd!"):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.get_json()
    return {"Authorization": "Bearer " + r.get_json()["access_token"]}


@pytest.fixture()
def auth(client):
    return register(client)


@pytest.fixture()
def admin(client):
    return login(client, "manager@test.com")


ADDRESS = {"full_name": "Test Buyer", "phone": "9999999999", "line1": "1 Test St", "city": "Pune",
           "state": "MH", "postal_code": "411001"}


def checkout(client, auth, method="cod", **extra):
    return client.post("/api/orders/checkout", headers=auth,
                       json={"shipping_address": ADDRESS, "payment_method": method, **extra})
