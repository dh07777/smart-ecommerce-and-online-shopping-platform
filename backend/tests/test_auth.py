from .conftest import login, register


def test_register_login_me(client):
    h = register(client)
    r = client.get("/api/auth/me", headers=h)
    assert r.status_code == 200 and r.get_json()["role"] == "customer"
    assert login(client, "buyer@test.com")


def test_duplicate_and_weak_password(client):
    register(client)
    assert client.post("/api/auth/register", json={"name": "X Y", "email": "buyer@test.com", "password": "Passw0rd!"}).status_code == 409
    assert client.post("/api/auth/register", json={"name": "X Y", "email": "n@test.com", "password": "short"}).status_code == 400


def test_wrong_password(client):
    register(client)
    assert client.post("/api/auth/login", json={"email": "buyer@test.com", "password": "nope12345"}).status_code == 401


def test_logout_revokes_token(client):
    h = register(client)
    assert client.post("/api/auth/logout", headers=h).status_code == 200
    assert client.get("/api/auth/me", headers=h).status_code == 401


def test_protected_route_requires_token(client):
    assert client.get("/api/cart").status_code == 401


def test_password_reset_flow(client):
    register(client)
    token = client.post("/api/auth/forgot-password", json={"email": "buyer@test.com"}).get_json()["dev_reset_token"]
    assert client.post("/api/auth/reset-password", json={"token": "bad", "password": "NewPass123"}).status_code == 400
    assert client.post("/api/auth/reset-password", json={"token": token, "password": "NewPass123"}).status_code == 200
    assert login(client, "buyer@test.com", "NewPass123")
    assert client.post("/api/auth/reset-password", json={"token": token, "password": "Another123"}).status_code == 400


def test_change_password(client, auth):
    r = client.post("/api/auth/change-password", headers=auth, json={"current_password": "Passw0rd!", "new_password": "Better123"})
    assert r.status_code == 200
    assert client.post("/api/auth/change-password", headers=auth, json={"current_password": "wrong", "new_password": "Better123"}).status_code == 403
