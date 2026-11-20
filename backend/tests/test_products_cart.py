def test_product_list_search_filter(client):
    data = client.get("/api/products").get_json()
    assert data["total"] == 2
    assert client.get("/api/products?q=two").get_json()["total"] == 1
    assert client.get("/api/products?min_price=500").get_json()["total"] == 1
    assert client.get("/api/products?category=gadgets&sort=price_asc").get_json()["items"][0]["name"] == "Widget Two"
    assert client.get("/api/products?in_stock=1").get_json()["total"] == 2


def test_product_detail_and_404(client):
    d = client.get("/api/products/widget-one").get_json()
    assert d["variants"][0]["stock"] == 10 and len(d["related"]) == 1
    assert client.get("/api/products/nope").status_code == 404


def test_cart_flow_and_totals(client, auth):
    r = client.post("/api/cart/items", headers=auth, json={"product_id": 1, "quantity": 2})
    assert r.status_code == 201
    cart = r.get_json()
    assert cart["subtotal"] == 2000 and cart["tax"] == 360 and cart["shipping"] == 0 and cart["total"] == 2360
    item_id = cart["items"][0]["id"]
    assert client.patch(f"/api/cart/items/{item_id}", headers=auth, json={"quantity": 1}).get_json()["subtotal"] == 1000
    assert client.patch(f"/api/cart/items/{item_id}", headers=auth, json={"quantity": 99}).status_code in (400, 409)
    assert client.delete(f"/api/cart/items/{item_id}", headers=auth).get_json()["count"] == 0


def test_cart_respects_stock(client, auth):
    assert client.post("/api/cart/items", headers=auth, json={"product_id": 2, "quantity": 5}).status_code == 409


def test_coupon(client, auth):
    client.post("/api/cart/items", headers=auth, json={"product_id": 1, "quantity": 1})
    r = client.post("/api/cart/coupon", headers=auth, json={"code": "ten"})
    assert r.status_code == 200 and r.get_json()["discount"] == 100
    assert client.post("/api/cart/coupon", headers=auth, json={"code": "NOPE"}).status_code == 400


def test_wishlist(client, auth):
    assert client.post("/api/wishlist", headers=auth, json={"product_id": 1}).status_code == 201
    assert len(client.get("/api/wishlist", headers=auth).get_json()) == 1
    assert client.post("/api/wishlist/1/move-to-cart", headers=auth).get_json()["count"] == 1
    assert client.get("/api/wishlist", headers=auth).get_json() == []
