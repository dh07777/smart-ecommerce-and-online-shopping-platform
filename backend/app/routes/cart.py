from flask import Blueprint, g, jsonify, request

from ..extensions import db
from ..models import Cart, CartItem, Product, ProductVariant, Wishlist, WishlistItem
from ..services import cart_summary, guest_summary, resolve_entries, validate_coupon
from ..utils import api_error, auth_required, clean, to_int

bp = Blueprint("cart", __name__, url_prefix="/api")


def _cart():
    cart = Cart.query.filter_by(user_id=g.user.id).first()
    if not cart:
        cart = Cart(user_id=g.user.id)
        db.session.add(cart)
        db.session.flush()
    return cart


def _delivery():
    d = request.args.get("delivery", "standard")
    return d if d in ("standard", "express") else "standard"


@bp.post("/cart/guest")
def guest_cart():
    """Price a not-logged-in visitor's cart (kept in the browser) using live DB prices and stock."""
    d = request.get_json(silent=True) or {}
    return jsonify(guest_summary(d.get("items"), _delivery()))


@bp.post("/cart/merge")
@auth_required
def merge_cart():
    """Merge a guest cart into the logged-in user's persistent cart after login."""
    cart = _cart()
    for vid, qty in resolve_entries((request.get_json(silent=True) or {}).get("items")).items():
        variant = db.session.get(ProductVariant, vid)
        stock = variant.inventory.quantity if variant.inventory else 0
        item = next((i for i in cart.items if i.variant_id == vid), None)
        new_qty = min((item.quantity if item else 0) + qty, stock, 20)
        if new_qty < 1:
            continue
        if item:
            item.quantity = new_qty
        else:
            db.session.add(CartItem(cart_id=cart.id, variant_id=vid, quantity=new_qty))
    db.session.commit()
    db.session.refresh(cart)
    return jsonify(cart_summary(cart, _delivery()))


@bp.get("/cart")
@auth_required
def get_cart():
    return jsonify(cart_summary(_cart(), _delivery()))


@bp.post("/cart/items")
@auth_required
def add_item():
    d = request.get_json(silent=True) or {}
    qty = to_int(d.get("quantity"), 1)
    if qty < 1 or qty > 20:
        return api_error("Quantity must be between 1 and 20")
    variant = None
    if d.get("variant_id"):
        variant = db.session.get(ProductVariant, to_int(d["variant_id"], 0))
    elif d.get("product_id"):
        p = db.session.get(Product, to_int(d["product_id"], 0))
        if p:
            variant = next((v for v in p.variants if v.is_active), None)
    if not variant or not variant.is_active or not variant.product.is_active:
        return api_error("Product not available", 404)
    cart = _cart()
    item = next((i for i in cart.items if i.variant_id == variant.id), None)
    new_qty = (item.quantity if item else 0) + qty
    stock = variant.inventory.quantity if variant.inventory else 0
    if new_qty > stock:
        return api_error(f"Only {stock} left in stock", 409)
    if item:
        item.quantity = new_qty
    else:
        db.session.add(CartItem(cart_id=cart.id, variant_id=variant.id, quantity=new_qty))
    db.session.commit()
    db.session.refresh(cart)
    return jsonify(cart_summary(cart, _delivery())), 201


@bp.patch("/cart/items/<int:item_id>")
@auth_required
def update_item(item_id):
    cart = _cart()
    item = CartItem.query.filter_by(id=item_id, cart_id=cart.id).first_or_404()
    qty = to_int((request.get_json(silent=True) or {}).get("quantity"))
    if qty is None or qty < 1 or qty > 20:
        return api_error("Quantity must be between 1 and 20")
    stock = item.variant.inventory.quantity if item.variant.inventory else 0
    if qty > stock:
        return api_error(f"Only {stock} left in stock", 409)
    item.quantity = qty
    db.session.commit()
    db.session.refresh(cart)
    return jsonify(cart_summary(cart, _delivery()))


@bp.delete("/cart/items/<int:item_id>")
@auth_required
def remove_item(item_id):
    cart = _cart()
    item = CartItem.query.filter_by(id=item_id, cart_id=cart.id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    db.session.refresh(cart)
    return jsonify(cart_summary(cart, _delivery()))


@bp.delete("/cart")
@auth_required
def clear_cart():
    cart = _cart()
    CartItem.query.filter_by(cart_id=cart.id).delete()
    cart.coupon_code = None
    db.session.commit()
    db.session.refresh(cart)
    return jsonify(cart_summary(cart, _delivery()))


@bp.post("/cart/coupon")
@auth_required
def apply_coupon():
    cart = _cart()
    code = clean((request.get_json(silent=True) or {}).get("code"), 40)
    summary = cart_summary(cart)
    try:
        coupon, _ = validate_coupon(code, summary["subtotal"], g.user.id)
    except ValueError as e:
        return api_error(str(e), 400)
    cart.coupon_code = coupon.code
    db.session.commit()
    return jsonify(cart_summary(cart, _delivery()))


@bp.delete("/cart/coupon")
@auth_required
def remove_coupon():
    cart = _cart()
    cart.coupon_code = None
    db.session.commit()
    return jsonify(cart_summary(cart, _delivery()))


# ---------- wishlist ----------
def _wishlist():
    wl = Wishlist.query.filter_by(user_id=g.user.id).first()
    if not wl:
        wl = Wishlist(user_id=g.user.id)
        db.session.add(wl)
        db.session.flush()
    return wl


@bp.get("/wishlist")
@auth_required
def get_wishlist():
    return jsonify([{**i.product.to_dict(), "added_at": i.added_at.isoformat() + "Z"}
                    for i in _wishlist().items if i.product.is_active])


@bp.post("/wishlist")
@auth_required
def add_wishlist():
    pid = to_int((request.get_json(silent=True) or {}).get("product_id"), 0)
    product = db.session.get(Product, pid)
    if not product or not product.is_active:
        return api_error("Product not found", 404)
    wl = _wishlist()
    if not any(i.product_id == pid for i in wl.items):
        db.session.add(WishlistItem(wishlist_id=wl.id, product_id=pid))
        db.session.commit()
    return jsonify({"message": "Added to wishlist"}), 201


@bp.delete("/wishlist/<int:pid>")
@auth_required
def remove_wishlist(pid):
    WishlistItem.query.filter_by(wishlist_id=_wishlist().id, product_id=pid).delete()
    db.session.commit()
    return jsonify({"message": "Removed from wishlist"})


@bp.post("/wishlist/<int:pid>/move-to-cart")
@auth_required
def move_to_cart(pid):
    product = db.session.get(Product, pid)
    wl = _wishlist()
    item = WishlistItem.query.filter_by(wishlist_id=wl.id, product_id=pid).first_or_404()
    variant = next((v for v in product.variants if v.is_active and v.inventory and v.inventory.quantity > 0), None)
    if not variant:
        return api_error("This product is out of stock", 409)
    cart = _cart()
    ci = next((i for i in cart.items if i.variant_id == variant.id), None)
    if ci:
        ci.quantity = min(ci.quantity + 1, variant.inventory.quantity)
    else:
        db.session.add(CartItem(cart_id=cart.id, variant_id=variant.id, quantity=1))
    db.session.delete(item)
    db.session.commit()
    db.session.refresh(cart)
    return jsonify(cart_summary(cart))
