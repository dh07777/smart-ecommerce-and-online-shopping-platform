"""Admin / seller back-office API (all endpoints are role protected)."""
import io
import json
import secrets
from datetime import datetime, timedelta

import pandas as pd
from flask import Blueprint, Response, g, jsonify, request
from sqlalchemy import case, func, or_
from werkzeug.security import generate_password_hash

from ..extensions import db, utcnow
from ..models import (ORDER_STATUSES, AuditLog, Brand, CartItem, Category, Coupon, CouponUsage, Inventory,
                      NewsletterSubscriber, Notification, Promotion, Order, OrderItem, Payment, Product, ProductImage, ProductVariant, RecentlyViewed,
                      Refund, Review, Role, Seller, Setting, StockHistory, SupportTicket, TicketMessage,
                      Transaction, User, WishlistItem)
from ..services import (DEFAULT_SETTINGS, adjust_stock, cancel_order, get_role, get_setting, notify)
from ..utils import send_email
from ..models import iso
from ..utils import (api_error, audit, clean, paginate, password_problem, roles_required, save_image,
                     slugify, to_float, to_int, valid_email)
from .reviews import refresh_rating

bp = Blueprint("admin", __name__, url_prefix="/api/admin")

staff = roles_required("store_admin")
staff_or_seller = roles_required("store_admin", "seller")
superadmin = roles_required("super_admin")
LIVE = ["cancelled", "returned"]  # statuses excluded from sales figures


def _is_seller():
    return g.user.role.name == "seller"


def _seller_id():
    return g.user.seller.id if g.user.seller else -1


def _owns(product):
    return not _is_seller() or product.seller_id == _seller_id()


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "")[:19])
    except ValueError:
        raise ValueError("Invalid date")


# =============================== dashboard ===============================
def _revenue_expr():
    return func.coalesce(func.sum(case((Order.payment_status == "paid", Order.total), else_=0)), 0)


@bp.get("/dashboard")
@staff
def dashboard():
    live = Order.status.notin_(LIVE)
    revenue = db.session.query(func.coalesce(func.sum(Order.total), 0)).filter(
        Order.payment_status == "paid", live).scalar()
    items_sold = db.session.query(func.coalesce(func.sum(OrderItem.quantity), 0)).join(Order).filter(live).scalar()
    low = (db.session.query(ProductVariant, Inventory).join(Inventory, Inventory.variant_id == ProductVariant.id)
           .join(Product).filter(Product.is_active.is_(True), Inventory.quantity <= Inventory.low_stock_threshold)
           .order_by(Inventory.quantity).limit(10).all())
    low_count = (db.session.query(func.count(Inventory.id)).filter(
        Inventory.quantity <= Inventory.low_stock_threshold).scalar())
    recent = Order.query.order_by(Order.created_at.desc()).limit(8).all()
    return jsonify({
        "total_revenue": round(float(revenue), 2), "total_sales": int(items_sold),
        "total_orders": Order.query.count(),
        "total_customers": User.query.join(Role).filter(Role.name == "customer").count(),
        "total_products": Product.query.filter_by(is_active=True).count(),
        "pending_orders": Order.query.filter_by(status="pending").count(),
        "low_stock_count": low_count,
        "low_stock": [{"variant_id": v.id, "product": v.product.name, "sku": v.sku, "size": v.size,
                       "color": v.color, "quantity": i.quantity, "threshold": i.low_stock_threshold}
                      for v, i in low],
        "recent_orders": [o.to_dict() for o in recent],
        "revenue_chart": _sales_series("daily", 14)})


# =============================== products ===============================
def _product_payload(d, product=None):
    out = {}
    if "name" in d or product is None:
        name = clean(d.get("name"), 200)
        if len(name) < 2:
            raise ValueError("Product name is required")
        out["name"] = name
    if "price" in d or product is None:
        price = to_float(d.get("price"))
        if price is None or price < 0:
            raise ValueError("Enter a valid price")
        out["price"] = round(price, 2)
    if "mrp" in d:
        mrp = to_float(d.get("mrp"))
        out["mrp"] = round(mrp, 2) if mrp else None
    if "description" in d:
        out["description"] = clean(d.get("description"), 5000)
    if "category_id" in d or product is None:
        if not db.session.get(Category, to_int(d.get("category_id"), 0)):
            raise ValueError("Choose a valid category")
        out["category_id"] = int(d["category_id"])
    if "brand_id" in d:
        bid = to_int(d.get("brand_id"))
        if bid and not db.session.get(Brand, bid):
            raise ValueError("Invalid brand")
        out["brand_id"] = bid or None
    for flag in ("is_active", "is_featured"):
        if flag in d:
            out[flag] = bool(d[flag])
    if "specifications" in d:
        specs = d["specifications"]
        if isinstance(specs, str):
            try:
                specs = json.loads(specs or "{}")
            except ValueError:
                raise ValueError("Specifications must be valid JSON")
        if not isinstance(specs, dict):
            raise ValueError("Specifications must be an object")
        out["specifications"] = json.dumps({str(k)[:60]: str(v)[:200] for k, v in specs.items()})
    return out


def _unique_slug(name):
    base, slug, n = slugify(name), None, 0
    while True:
        slug = base if n == 0 else f"{base}-{n}"
        if not Product.query.filter_by(slug=slug).first():
            return slug
        n += 1


def _new_variant(product, size=None, color=None, delta=0, stock=0, user_id=None):
    v = ProductVariant(product=product, size=clean(size, 30) or None, color=clean(color, 30) or None,
                       price_delta=to_float(delta, 0) or 0,
                       sku=f"{slugify(product.name)[:14].upper()}-{secrets.token_hex(3).upper()}")
    db.session.add(v)
    db.session.flush()
    db.session.add(Inventory(variant_id=v.id, quantity=0, low_stock_threshold=int(get_setting("low_stock_default") or 10)))
    db.session.flush()
    db.session.refresh(v)
    stock = max(to_int(stock, 0) or 0, 0)
    if stock:
        adjust_stock(v, stock, "Initial stock", user_id)
    return v


@bp.get("/products")
@staff_or_seller
def admin_products():
    q = Product.query.join(Category).outerjoin(Brand)
    if _is_seller():
        q = q.filter(Product.seller_id == _seller_id())
    if request.args.get("q"):
        like = f"%{clean(request.args['q'], 80)}%"
        q = q.filter(or_(Product.name.ilike(like), Brand.name.ilike(like), Category.name.ilike(like)))
    if request.args.get("category_id"):
        q = q.filter(Product.category_id == request.args.get("category_id", type=int))
    return jsonify(paginate(q.order_by(Product.id.desc()), lambda p: p.to_dict(detail=True)))


@bp.post("/products")
@staff_or_seller
def create_product():
    d = request.get_json(silent=True) or {}
    seller_id = None
    if _is_seller():
        if not g.user.seller or not g.user.seller.is_verified:
            return api_error("Your seller account is awaiting verification", 403)
        seller_id = g.user.seller.id
    elif d.get("seller_id"):
        seller_id = to_int(d["seller_id"])
        if not db.session.get(Seller, seller_id or 0):
            return api_error("Invalid seller")
    try:
        data = _product_payload(d)
    except ValueError as e:
        return api_error(str(e))
    p = Product(slug=_unique_slug(data["name"]), seller_id=seller_id, **data)
    db.session.add(p)
    db.session.flush()
    variants = d.get("variants") or [{}]
    for v in variants[:30]:
        _new_variant(p, v.get("size"), v.get("color"), v.get("price_delta"), v.get("stock"), g.user.id)
    audit("create_product", "product", p.id, p.name)
    db.session.commit()
    return jsonify(p.to_dict(detail=True)), 201


@bp.get("/products/<int:pid>")
@staff_or_seller
def admin_product(pid):
    p = db.session.get(Product, pid)
    if not p or not _owns(p):
        return api_error("Product not found", 404)
    return jsonify(p.to_dict(detail=True))


@bp.put("/products/<int:pid>")
@staff_or_seller
def update_product(pid):
    p = db.session.get(Product, pid)
    if not p or not _owns(p):
        return api_error("Product not found", 404)
    try:
        data = _product_payload(request.get_json(silent=True) or {}, p)
    except ValueError as e:
        return api_error(str(e))
    for k, v in data.items():
        setattr(p, k, v)
    audit("update_product", "product", p.id, p.name)
    db.session.commit()
    return jsonify(p.to_dict(detail=True))


@bp.delete("/products/<int:pid>")
@staff_or_seller
def delete_product(pid):
    p = db.session.get(Product, pid)
    if not p or not _owns(p):
        return api_error("Product not found", 404)
    if OrderItem.query.filter_by(product_id=pid).first():
        p.is_active = False  # keep order history intact
        audit("deactivate_product", "product", pid, p.name)
        db.session.commit()
        return jsonify({"message": "Product has orders, so it was deactivated instead of deleted"})
    vids = [v.id for v in p.variants]
    if vids:
        CartItem.query.filter(CartItem.variant_id.in_(vids)).delete(synchronize_session=False)
        StockHistory.query.filter(StockHistory.variant_id.in_(vids)).delete(synchronize_session=False)
    WishlistItem.query.filter_by(product_id=pid).delete()
    Review.query.filter_by(product_id=pid).delete()
    RecentlyViewed.query.filter_by(product_id=pid).delete()
    audit("delete_product", "product", pid, p.name)
    db.session.delete(p)
    db.session.commit()
    return jsonify({"message": "Product deleted"})


@bp.post("/products/<int:pid>/images")
@staff_or_seller
def upload_product_images(pid):
    p = db.session.get(Product, pid)
    if not p or not _owns(p):
        return api_error("Product not found", 404)
    files = request.files.getlist("files") or request.files.getlist("file")
    if not files:
        return api_error("No files uploaded")
    if len(p.images) + len(files) > 10:
        return api_error("A product can have at most 10 images")
    try:
        for f in files:
            url = save_image(f, "products")
            db.session.add(ProductImage(product_id=p.id, url=url, alt=p.name, position=len(p.images)))
            db.session.flush()
            db.session.refresh(p)
    except ValueError as e:
        db.session.rollback()
        return api_error(str(e))
    db.session.commit()
    return jsonify(p.to_dict(detail=True)), 201


@bp.delete("/products/<int:pid>/images/<int:iid>")
@staff_or_seller
def delete_product_image(pid, iid):
    p = db.session.get(Product, pid)
    img = ProductImage.query.filter_by(id=iid, product_id=pid).first()
    if not p or not img or not _owns(p):
        return api_error("Image not found", 404)
    db.session.delete(img)
    db.session.commit()
    return jsonify(p.to_dict(detail=True))


@bp.post("/products/<int:pid>/variants")
@staff_or_seller
def add_variant(pid):
    p = db.session.get(Product, pid)
    if not p or not _owns(p):
        return api_error("Product not found", 404)
    d = request.get_json(silent=True) or {}
    _new_variant(p, d.get("size"), d.get("color"), d.get("price_delta"), d.get("stock"), g.user.id)
    db.session.commit()
    db.session.refresh(p)
    return jsonify(p.to_dict(detail=True)), 201


@bp.put("/variants/<int:vid>")
@staff_or_seller
def update_variant(vid):
    v = db.session.get(ProductVariant, vid)
    if not v or not _owns(v.product):
        return api_error("Variant not found", 404)
    d = request.get_json(silent=True) or {}
    for f in ("size", "color"):
        if f in d:
            setattr(v, f, clean(d[f], 30) or None)
    if "price_delta" in d:
        v.price_delta = to_float(d["price_delta"], 0) or 0
    db.session.commit()
    return jsonify(v.to_dict())


@bp.delete("/variants/<int:vid>")
@staff_or_seller
def delete_variant(vid):
    v = db.session.get(ProductVariant, vid)
    if not v or not _owns(v.product):
        return api_error("Variant not found", 404)
    if len([x for x in v.product.variants if x.is_active]) <= 1:
        return api_error("A product needs at least one variant")
    if OrderItem.query.filter_by(variant_id=vid).first():
        v.is_active = False
    else:
        CartItem.query.filter_by(variant_id=vid).delete()
        StockHistory.query.filter_by(variant_id=vid).delete()
        db.session.delete(v)
    db.session.commit()
    return jsonify({"message": "Variant removed"})


# =============================== categories & brands ===============================
def _simple_crud(model, label, url, extra_fields=()):
    def create():
        d = request.get_json(silent=True) or {}
        name = clean(d.get("name"), 80)
        if len(name) < 2:
            return api_error(f"{label} name is required")
        if model.query.filter(func.lower(model.name) == name.lower()).first():
            return api_error(f"{label} already exists", 409)
        obj = model(name=name, slug=slugify(name))
        for f in extra_fields:
            if f in d:
                setattr(obj, f, clean(d[f], 1000) or None)
        db.session.add(obj)
        audit(f"create_{label.lower()}", label.lower(), name)
        db.session.commit()
        return jsonify(obj.to_dict()), 201

    def update(oid):
        obj = db.session.get(model, oid)
        if not obj:
            return api_error(f"{label} not found", 404)
        d = request.get_json(silent=True) or {}
        if d.get("name"):
            obj.name = clean(d["name"], 80)
            obj.slug = slugify(obj.name)
        for f in extra_fields:
            if f in d:
                setattr(obj, f, clean(d[f], 1000) or None)
        if "is_active" in d and hasattr(obj, "is_active"):
            obj.is_active = bool(d["is_active"])
        db.session.commit()
        return jsonify(obj.to_dict())

    def delete(oid):
        obj = db.session.get(model, oid)
        if not obj:
            return api_error(f"{label} not found", 404)
        col = Product.category_id if model is Category else Product.brand_id
        if Product.query.filter(col == oid).first():
            return api_error(f"This {label.lower()} still has products. Move or delete them first.", 409)
        db.session.delete(obj)
        audit(f"delete_{label.lower()}", label.lower(), oid)
        db.session.commit()
        return jsonify({"message": f"{label} deleted"})

    bp.add_url_rule(f"/{url}", f"create_{url}", staff(create), methods=["POST"])
    bp.add_url_rule(f"/{url}/<int:oid>", f"update_{url}", staff(update), methods=["PUT"])
    bp.add_url_rule(f"/{url}/<int:oid>", f"delete_{url}", staff(delete), methods=["DELETE"])


_simple_crud(Category, "Category", "categories", ("description",))
_simple_crud(Brand, "Brand", "brands")


# =============================== inventory ===============================
@bp.get("/inventory")
@staff_or_seller
def inventory_list():
    q = (db.session.query(ProductVariant).join(Product).join(Inventory, Inventory.variant_id == ProductVariant.id)
         .filter(ProductVariant.is_active.is_(True)))
    if _is_seller():
        q = q.filter(Product.seller_id == _seller_id())
    if request.args.get("q"):
        q = q.filter(or_(Product.name.ilike(f"%{clean(request.args['q'], 80)}%"),
                         ProductVariant.sku.ilike(f"%{clean(request.args['q'], 80)}%")))
    if request.args.get("low_stock") in ("1", "true"):
        q = q.filter(Inventory.quantity <= Inventory.low_stock_threshold)
    return jsonify(paginate(q.order_by(Inventory.quantity), lambda v: {
        "variant_id": v.id, "product_id": v.product_id, "product": v.product.name, "sku": v.sku,
        "size": v.size, "color": v.color, "quantity": v.inventory.quantity,
        "threshold": v.inventory.low_stock_threshold,
        "status": "out" if v.inventory.quantity == 0 else
        ("low" if v.inventory.quantity <= v.inventory.low_stock_threshold else "ok")}))


@bp.patch("/inventory/<int:vid>")
@staff_or_seller
def inventory_update(vid):
    v = db.session.get(ProductVariant, vid)
    if not v or not _owns(v.product):
        return api_error("Variant not found", 404)
    d = request.get_json(silent=True) or {}
    reason = clean(d.get("reason"), 150) or "Manual adjustment"
    try:
        if "quantity" in d:
            target = to_int(d["quantity"])
            if target is None or target < 0:
                return api_error("Quantity must be 0 or more")
            adjust_stock(v, target - v.inventory.quantity, reason, g.user.id)
        elif "delta" in d:
            delta = to_int(d["delta"])
            if not delta:
                return api_error("Enter a non-zero change")
            adjust_stock(v, delta, reason, g.user.id)
        if "low_stock_threshold" in d:
            v.inventory.low_stock_threshold = max(to_int(d["low_stock_threshold"], 0) or 0, 0)
    except ValueError as e:
        return api_error(str(e))
    audit("update_stock", "variant", vid, reason)
    db.session.commit()
    return jsonify(v.to_dict())


@bp.get("/inventory/history")
@staff_or_seller
def inventory_history():
    q = StockHistory.query.join(ProductVariant).join(Product)
    if _is_seller():
        q = q.filter(Product.seller_id == _seller_id())
    if request.args.get("variant_id"):
        q = q.filter(StockHistory.variant_id == request.args.get("variant_id", type=int))
    return jsonify(paginate(q.order_by(StockHistory.id.desc()), lambda h: {
        "id": h.id, "product": h.variant.product.name, "sku": h.variant.sku, "change": h.change,
        "quantity_after": h.quantity_after, "reason": h.reason, "created_at": h.created_at.isoformat() + "Z"}))


@bp.get("/inventory/report")
@staff
def inventory_report():
    rows = db.session.query(Inventory.quantity, Inventory.low_stock_threshold, ProductVariant.price_delta,
                            Product.price).join(ProductVariant).join(Product).all()
    return jsonify({"variants": len(rows), "units": sum(r[0] for r in rows),
                    "out_of_stock": sum(1 for r in rows if r[0] == 0),
                    "low_stock": sum(1 for r in rows if 0 < r[0] <= r[1]),
                    "stock_value": round(sum(r[0] * (r[3] + (r[2] or 0)) for r in rows), 2)})


# =============================== orders & refunds ===============================
TRANSITIONS = {"pending": ["confirmed", "cancelled"], "confirmed": ["processing", "cancelled"],
               "processing": ["shipped", "cancelled"], "shipped": ["out_for_delivery", "delivered"],
               "out_for_delivery": ["delivered"], "delivered": [], "cancelled": [], "returned": []}


@bp.get("/orders")
@staff
def admin_orders():
    q = Order.query.join(User)
    a = request.args
    if a.get("status") in ORDER_STATUSES:
        q = q.filter(Order.status == a["status"])
    if a.get("payment_status"):
        q = q.filter(Order.payment_status == a["payment_status"])
    if a.get("q"):
        like = f"%{clean(a['q'], 60)}%"
        q = q.filter(or_(Order.order_number.ilike(like), User.email.ilike(like), User.name.ilike(like)))
    return jsonify(paginate(q.order_by(Order.created_at.desc()), lambda o: o.to_dict()))


@bp.get("/orders/<int:oid>")
@staff
def admin_order(oid):
    o = db.session.get(Order, oid)
    return jsonify(o.to_dict(detail=True)) if o else api_error("Order not found", 404)


@bp.patch("/orders/<int:oid>/status")
@staff
def update_order_status(oid):
    o = db.session.get(Order, oid)
    if not o:
        return api_error("Order not found", 404)
    d = request.get_json(silent=True) or {}
    new = d.get("status")
    if new not in TRANSITIONS.get(o.status, []):
        return api_error(f"Cannot move an order from '{o.status}' to '{new}'")
    note = clean(d.get("note"), 200)
    if new == "cancelled":
        cancel_order(o, g.user, note or "Cancelled by store")
    else:
        o.status = new
        sh = o.shipping
        if d.get("carrier"):
            sh.carrier = clean(d["carrier"], 60)
        if d.get("tracking_number"):
            sh.tracking_number = clean(d["tracking_number"], 60)
        if new == "shipped" and not sh.tracking_number:
            sh.tracking_number = "TRK" + secrets.token_hex(5).upper()
            sh.carrier = sh.carrier or "ShopSphere Express"
        sh.add_event(new, note)
        if new == "delivered":
            sh.delivered_at = utcnow()
            if o.payment_method == "cod" and o.payment.status == "pending":
                o.payment.status, o.payment_status = "paid", "paid"
                db.session.add(Transaction(payment_id=o.payment.id, kind="cod_collected", amount=o.total,
                                           status="success", note="Cash collected on delivery"))
        titles = {"confirmed": "Order confirmed", "processing": "Order is being prepared",
                  "shipped": "Order shipped", "out_for_delivery": "Out for delivery", "delivered": "Order delivered"}
        notify(o.user_id, f"{titles[new]} - {o.order_number}",
               f"Your order {o.order_number} is now '{new.replace('_', ' ')}'." +
               (f" Tracking: {sh.tracking_number}" if new == "shipped" else ""), "shipping")
    audit("order_status", "order", o.id, f"{new}")
    db.session.commit()
    return jsonify(o.to_dict(detail=True))


@bp.get("/refunds")
@staff
def list_refunds():
    q = Refund.query
    if request.args.get("status"):
        q = q.filter_by(status=request.args["status"])
    return jsonify(paginate(q.order_by(Refund.created_at.desc()), lambda r: r.to_dict()))


@bp.patch("/refunds/<int:rid>")
@staff
def update_refund(rid):
    r = db.session.get(Refund, rid)
    if not r:
        return api_error("Refund not found", 404)
    new = (request.get_json(silent=True) or {}).get("status")
    allowed = {"pending": ["approved", "rejected", "processed"], "approved": ["processed"]}
    if new not in allowed.get(r.status, []):
        return api_error(f"Cannot change refund from '{r.status}' to '{new}'")
    o = r.order
    if new == "rejected" and r.kind == "cancellation":
        return api_error("Refunds for cancelled paid orders cannot be rejected")
    r.status = new
    if new == "processed":
        # NOTE: record-keeping only. Trigger the real gateway refund from your Razorpay dashboard/API.
        o.payment.status = o.payment_status = "refunded"
        db.session.add(Transaction(payment_id=o.payment.id, kind="refund", amount=r.amount, status="success",
                                   note=f"Refund #{r.id} processed"))
        if r.kind == "return":
            for it in o.items:
                if it.variant:
                    adjust_stock(it.variant, it.quantity, f"Return {o.order_number}", g.user.id)
            o.status = "returned"
            o.shipping.add_event("returned", "Return accepted")
    notify(o.user_id, f"Refund {new}", f"Your refund for order {o.order_number} is {new}.", "payment")
    audit("refund_update", "refund", r.id, new)
    db.session.commit()
    return jsonify(r.to_dict())


# =============================== customers ===============================
@bp.get("/customers")
@staff
def customers():
    q = User.query.join(Role).filter(Role.name == "customer")
    if request.args.get("q"):
        like = f"%{clean(request.args['q'], 60)}%"
        q = q.filter(or_(User.name.ilike(like), User.email.ilike(like)))
    stats = {uid: (cnt, spent) for uid, cnt, spent in db.session.query(
        Order.user_id, func.count(Order.id), func.coalesce(func.sum(Order.total), 0)).filter(
        Order.status.notin_(LIVE)).group_by(Order.user_id)}
    return jsonify(paginate(q.order_by(User.id.desc()), lambda u: {
        **u.to_dict(), "order_count": stats.get(u.id, (0, 0))[0],
        "total_spent": round(float(stats.get(u.id, (0, 0))[1]), 2)}))


@bp.get("/customers/<int:uid>")
@staff
def customer_detail(uid):
    u = db.session.get(User, uid)
    if not u:
        return api_error("User not found", 404)
    orders = Order.query.filter_by(user_id=uid).order_by(Order.created_at.desc()).limit(20).all()
    return jsonify({**u.to_dict(), "orders": [o.to_dict() for o in orders],
                    "addresses": [a.to_dict() for a in u.addresses]})


@bp.put("/customers/<int:uid>")
@staff
def edit_customer(uid):
    u = db.session.get(User, uid)
    if not u or u.role.name != "customer":
        return api_error("Customer not found", 404)
    d = request.get_json(silent=True) or {}
    if d.get("name"):
        u.name = clean(d["name"], 120)
    if "phone" in d:
        u.phone = clean(d["phone"], 20)
    if d.get("email"):
        email = clean(d["email"]).lower()
        if not valid_email(email):
            return api_error("Invalid email")
        if User.query.filter(User.email == email, User.id != uid).first():
            return api_error("Email already in use", 409)
        u.email = email
    audit("edit_customer", "user", uid)
    db.session.commit()
    return jsonify(u.to_dict())


@bp.patch("/customers/<int:uid>/active")
@staff
def toggle_customer(uid):
    u = db.session.get(User, uid)
    if not u or u.id == g.user.id or u.role.name == "super_admin":
        return api_error("This account cannot be changed", 400)
    if u.role.name in ("store_admin",) and g.user.role.name != "super_admin":
        return api_error("Only a super admin can change staff accounts", 403)
    u.is_active = bool((request.get_json(silent=True) or {}).get("is_active"))
    audit("toggle_user", "user", uid, f"active={u.is_active}")
    db.session.commit()
    return jsonify(u.to_dict())


@bp.get("/staff")
@superadmin
def list_staff():
    rows = User.query.join(Role).filter(Role.name.in_(["super_admin", "store_admin"])).all()
    return jsonify([u.to_dict() for u in rows])


@bp.post("/staff")
@superadmin
def create_staff():
    d = request.get_json(silent=True) or {}
    email = clean(d.get("email")).lower()
    problem = password_problem(d.get("password"))
    if not valid_email(email) or len(clean(d.get("name"))) < 2:
        return api_error("Name and valid email are required")
    if problem:
        return api_error(problem)
    if User.query.filter_by(email=email).first():
        return api_error("Email already in use", 409)
    u = User(name=clean(d["name"], 120), email=email, role=get_role("store_admin"),
             password_hash=generate_password_hash(d["password"]))
    db.session.add(u)
    audit("create_staff", "user", email)
    db.session.commit()
    return jsonify(u.to_dict()), 201


# =============================== coupons ===============================
def _coupon_payload(d, coupon=None):
    out = {}
    if coupon is None or "code" in d:
        code = clean(d.get("code"), 40).upper().replace(" ", "")
        if len(code) < 3:
            raise ValueError("Coupon code must be at least 3 characters")
        dupe = Coupon.query.filter(func.upper(Coupon.code) == code)
        if coupon:
            dupe = dupe.filter(Coupon.id != coupon.id)
        if dupe.first():
            raise ValueError("Coupon code already exists")
        out["code"] = code
    if coupon is None or "discount_type" in d:
        if d.get("discount_type") not in ("percent", "fixed"):
            raise ValueError("Discount type must be percent or fixed")
        out["discount_type"] = d["discount_type"]
    if coupon is None or "value" in d:
        val = to_float(d.get("value"))
        if val is None or val <= 0:
            raise ValueError("Discount value must be greater than 0")
        if (out.get("discount_type") or coupon.discount_type) == "percent" and val > 100:
            raise ValueError("Percentage cannot exceed 100")
        out["value"] = val
    for f in ("min_order_value", "max_discount"):
        if f in d:
            v = to_float(d[f])
            out[f] = v if v and v > 0 else (0 if f == "min_order_value" else None)
    for f in ("usage_limit", "per_user_limit"):
        if f in d:
            v = to_int(d[f])
            out[f] = v if v and v > 0 else None
    if "expires_at" in d:
        out["expires_at"] = _parse_date(d["expires_at"])
    if "description" in d:
        out["description"] = clean(d["description"], 200)
    if "is_active" in d:
        out["is_active"] = bool(d["is_active"])
    return out


@bp.get("/coupons")
@staff
def list_coupons():
    return jsonify([c.to_dict() for c in Coupon.query.order_by(Coupon.id.desc())])


@bp.post("/coupons")
@staff
def create_coupon():
    try:
        c = Coupon(**_coupon_payload(request.get_json(silent=True) or {}))
    except ValueError as e:
        return api_error(str(e))
    db.session.add(c)
    audit("create_coupon", "coupon", c.code)
    db.session.commit()
    return jsonify(c.to_dict()), 201


@bp.put("/coupons/<int:cid>")
@staff
def update_coupon(cid):
    c = db.session.get(Coupon, cid)
    if not c:
        return api_error("Coupon not found", 404)
    try:
        for k, v in _coupon_payload(request.get_json(silent=True) or {}, c).items():
            setattr(c, k, v)
    except ValueError as e:
        return api_error(str(e))
    audit("update_coupon", "coupon", c.code)
    db.session.commit()
    return jsonify(c.to_dict())


@bp.delete("/coupons/<int:cid>")
@staff
def delete_coupon(cid):
    c = db.session.get(Coupon, cid)
    if not c:
        return api_error("Coupon not found", 404)
    if CouponUsage.query.filter_by(coupon_id=cid).first():
        c.is_active = False
        db.session.commit()
        return jsonify({"message": "Coupon was used before, so it was disabled instead of deleted"})
    db.session.delete(c)
    db.session.commit()
    return jsonify({"message": "Coupon deleted"})


# =============================== analytics ===============================
def _sales_series(period, limit=None):
    fmt = {"daily": "%Y-%m-%d", "monthly": "%Y-%m", "annual": "%Y"}[period]
    now = utcnow()
    span = {"daily": limit or 30, "monthly": limit or 12}.get(period)
    cutoff = (now - timedelta(days=span if period == "daily" else span * 31)) if span else None
    label = func.strftime(fmt, Order.created_at)
    q = db.session.query(label, _revenue_expr(), func.count(Order.id)).filter(Order.status.notin_(LIVE))
    if cutoff:
        q = q.filter(Order.created_at >= cutoff)
    data = {l: (float(r), int(c)) for l, r, c in q.group_by(label).order_by(label)}
    if period == "daily":
        labels = [(now - timedelta(days=i)).strftime(fmt) for i in range(span - 1, -1, -1)]
    else:
        labels = sorted(data)
    return [{"label": l, "revenue": round(data.get(l, (0, 0))[0], 2), "orders": data.get(l, (0, 0))[1]}
            for l in labels]


@bp.get("/analytics/sales")
@staff
def analytics_sales():
    period = request.args.get("period", "daily")
    if period not in ("daily", "monthly", "annual"):
        return api_error("period must be daily, monthly or annual")
    series = _sales_series(period)
    return jsonify({"period": period, "series": series,
                    "total_revenue": round(sum(s["revenue"] for s in series), 2),
                    "total_orders": sum(s["orders"] for s in series)})


@bp.get("/analytics/top-products")
@staff
def analytics_top_products():
    rows = (db.session.query(Product.id, Product.name, func.sum(OrderItem.quantity),
                             func.sum(OrderItem.quantity * OrderItem.price))
            .join(OrderItem, OrderItem.product_id == Product.id).join(Order)
            .filter(Order.status.notin_(LIVE)).group_by(Product.id).order_by(func.sum(OrderItem.quantity).desc())
            .limit(10).all())
    return jsonify([{"id": i, "name": n, "units": int(u), "revenue": round(float(r), 2)} for i, n, u, r in rows])


@bp.get("/analytics/by-category")
@staff
def analytics_by_category():
    rows = (db.session.query(Category.name, func.sum(OrderItem.quantity * OrderItem.price),
                             func.sum(OrderItem.quantity))
            .join(Product, Product.category_id == Category.id)
            .join(OrderItem, OrderItem.product_id == Product.id).join(Order)
            .filter(Order.status.notin_(LIVE)).group_by(Category.id).order_by(
                func.sum(OrderItem.quantity * OrderItem.price).desc()).all())
    return jsonify([{"category": n, "revenue": round(float(r), 2), "units": int(u)} for n, r, u in rows])


@bp.get("/analytics/customers")
@staff
def analytics_customers():
    label = func.strftime("%Y-%m", User.created_at)
    new = db.session.query(label, func.count(User.id)).join(Role).filter(Role.name == "customer") \
        .group_by(label).order_by(label.desc()).limit(6).all()
    top = (db.session.query(User.id, User.name, User.email, func.count(Order.id), func.sum(Order.total))
           .join(Order).filter(Order.status.notin_(LIVE)).group_by(User.id)
           .order_by(func.sum(Order.total).desc()).limit(5).all())
    buyers = db.session.query(Order.user_id, func.count(Order.id)).filter(Order.status.notin_(LIVE)) \
        .group_by(Order.user_id).all()
    repeat = sum(1 for _, c in buyers if c > 1)
    return jsonify({"new_customers": [{"month": m, "count": c} for m, c in reversed(new)],
                    "top_customers": [{"id": i, "name": n, "email": e, "orders": c, "spent": round(float(s), 2)}
                                      for i, n, e, c, s in top],
                    "buyers": len(buyers), "repeat_buyers": repeat,
                    "repeat_rate": round(repeat / len(buyers) * 100, 1) if buyers else 0})


@bp.get("/analytics/orders")
@staff
def analytics_orders():
    by_status = dict(db.session.query(Order.status, func.count(Order.id)).group_by(Order.status))
    by_method = dict(db.session.query(Order.payment_method, func.count(Order.id)).group_by(Order.payment_method))
    aov = db.session.query(func.avg(Order.total)).filter(Order.status.notin_(LIVE)).scalar() or 0
    return jsonify({"by_status": by_status, "by_payment_method": by_method, "average_order_value": round(float(aov), 2)})


@bp.get("/analytics/export")
@staff
def analytics_export():
    kind = request.args.get("type", "orders")
    if kind == "orders":
        rows = [{"order_number": o.order_number, "date": o.created_at.date().isoformat(), "customer": o.user.email,
                 "status": o.status, "payment_method": o.payment_method, "payment_status": o.payment_status,
                 "subtotal": o.subtotal, "discount": o.discount, "tax": o.tax, "shipping": o.shipping_cost,
                 "total": o.total} for o in Order.query.order_by(Order.id)]
    elif kind == "products":
        rows = [{"id": p.id, "name": p.name, "category": p.category.name, "brand": p.brand.name if p.brand else "",
                 "price": p.price, "stock": p.stock, "sold": p.sold_count, "rating": p.rating_avg}
                for p in Product.query.order_by(Product.id)]
    elif kind == "customers":
        rows = [{"id": u.id, "name": u.name, "email": u.email, "joined": u.created_at.date().isoformat(),
                 "active": u.is_active} for u in User.query.join(Role).filter(Role.name == "customer")]
    elif kind == "inventory":
        rows = [{"sku": v.sku, "product": v.product.name, "size": v.size, "color": v.color,
                 "quantity": v.inventory.quantity if v.inventory else 0,
                 "threshold": v.inventory.low_stock_threshold if v.inventory else 0}
                for v in ProductVariant.query.order_by(ProductVariant.id)]
    else:
        return api_error("Unknown report type")
    buf = io.StringIO()
    pd.DataFrame(rows).to_csv(buf, index=False)
    audit("export", "report", kind)
    db.session.commit()
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={kind}-report.csv"})


# =============================== sellers ===============================
def _seller_stats(s):
    ids = [pid for (pid,) in db.session.query(Product.id).filter_by(seller_id=s.id)]
    units, revenue = 0, 0.0
    if ids:
        units, revenue = db.session.query(func.coalesce(func.sum(OrderItem.quantity), 0),
                                          func.coalesce(func.sum(OrderItem.quantity * OrderItem.price), 0)) \
            .join(Order).filter(OrderItem.product_id.in_(ids), Order.status.notin_(LIVE)).one()
    rating = db.session.query(func.avg(Product.rating_avg)).filter(Product.seller_id == s.id, Product.rating_count > 0).scalar()
    return {**s.to_dict(), "product_count": len(ids), "units_sold": int(units),
            "revenue": round(float(revenue), 2), "avg_rating": round(float(rating or 0), 2)}


@bp.get("/sellers")
@staff
def sellers():
    return jsonify([_seller_stats(s) for s in Seller.query.order_by(Seller.id.desc())])


@bp.get("/sellers/<int:sid>")
@staff
def seller_detail(sid):
    s = db.session.get(Seller, sid)
    if not s:
        return api_error("Seller not found", 404)
    prods = Product.query.filter_by(seller_id=sid).order_by(Product.sold_count.desc()).limit(20).all()
    return jsonify({**_seller_stats(s), "products": [p.to_dict() for p in prods]})


@bp.patch("/sellers/<int:sid>/verify")
@staff
def verify_seller(sid):
    s = db.session.get(Seller, sid)
    if not s:
        return api_error("Seller not found", 404)
    s.is_verified = bool((request.get_json(silent=True) or {}).get("is_verified"))
    notify(s.user_id, "Seller verification update",
           "Your seller account is now verified. You can list products." if s.is_verified
           else "Your seller verification has been revoked.", "account")
    audit("verify_seller", "seller", sid, f"verified={s.is_verified}")
    db.session.commit()
    return jsonify(_seller_stats(s))


@bp.route("/seller/profile", methods=["GET", "PUT"])
@roles_required("seller")
def seller_profile():
    s = g.user.seller
    if not s:
        return api_error("Seller profile not found", 404)
    if request.method == "PUT":
        d = request.get_json(silent=True) or {}
        if d.get("store_name"):
            s.store_name = clean(d["store_name"], 120)
        if "description" in d:
            s.description = clean(d["description"], 1000)
        db.session.commit()
    return jsonify(_seller_stats(s))


# =============================== reviews ===============================
@bp.get("/reviews")
@staff
def admin_reviews():
    q = Review.query
    if request.args.get("status"):
        q = q.filter_by(status=request.args["status"])
    return jsonify(paginate(q.order_by(Review.created_at.desc()), lambda r: r.to_dict()))


@bp.patch("/reviews/<int:rid>")
@staff
def moderate_review(rid):
    r = db.session.get(Review, rid)
    status = (request.get_json(silent=True) or {}).get("status")
    if not r or status not in ("approved", "rejected", "pending"):
        return api_error("Invalid request", 400)
    r.status = status
    db.session.flush()
    refresh_rating(r.product)
    audit("moderate_review", "review", rid, status)
    db.session.commit()
    return jsonify(r.to_dict())


# =============================== support tickets ===============================
@bp.get("/tickets")
@staff
def admin_tickets():
    q = SupportTicket.query
    if request.args.get("status"):
        q = q.filter_by(status=request.args["status"])
    return jsonify(paginate(q.order_by(SupportTicket.created_at.desc()), lambda t: t.to_dict()))


@bp.get("/tickets/<int:tid>")
@staff
def admin_ticket(tid):
    t = db.session.get(SupportTicket, tid)
    return jsonify(t.to_dict(detail=True)) if t else api_error("Ticket not found", 404)


@bp.post("/tickets/<int:tid>/reply")
@staff
def admin_ticket_reply(tid):
    t = db.session.get(SupportTicket, tid)
    body = clean((request.get_json(silent=True) or {}).get("message"), 3000)
    if not t or len(body) < 2:
        return api_error("Invalid request")
    t.messages.append(TicketMessage(sender="staff", body=body))
    if t.status == "open":
        t.status = "in_progress"
    if t.user_id:
        notify(t.user_id, f"Reply on ticket #{t.id}", body[:300], "support")
    db.session.commit()
    return jsonify(t.to_dict(detail=True))


@bp.patch("/tickets/<int:tid>")
@staff
def admin_ticket_status(tid):
    t = db.session.get(SupportTicket, tid)
    status = (request.get_json(silent=True) or {}).get("status")
    if not t or status not in ("open", "in_progress", "resolved", "closed"):
        return api_error("Invalid request")
    t.status = status
    db.session.commit()
    return jsonify(t.to_dict())


# =============================== settings & audit ===============================
NUMERIC = {"tax_rate", "free_shipping_threshold", "standard_shipping", "express_shipping", "low_stock_default"}
BOOLEAN = {"cod_enabled", "razorpay_enabled", "email_notifications", "maintenance_mode"}


@bp.get("/settings")
@staff
def get_settings():
    return jsonify({k: get_setting(k) for k in DEFAULT_SETTINGS})


@bp.put("/settings")
@staff
def put_settings():
    d = request.get_json(silent=True) or {}
    for k, v in d.items():
        if k not in DEFAULT_SETTINGS:
            continue
        if k in NUMERIC:
            n = to_float(v)
            if n is None or n < 0 or (k == "tax_rate" and n > 100):
                return api_error(f"Invalid value for {k}")
            v = str(int(n)) if n == int(n) else str(n)
        elif k in BOOLEAN:
            v = "true" if v in (True, "true", "1", 1) else "false"
        else:
            v = clean(str(v), 500)
        row = db.session.get(Setting, k)
        if row:
            row.value = v
        else:
            db.session.add(Setting(key=k, value=v))
    audit("update_settings", "settings", None, ",".join(d.keys())[:400])
    db.session.commit()
    return jsonify({k: get_setting(k) for k in DEFAULT_SETTINGS})


@bp.get("/audit-logs")
@staff
def audit_logs():
    q = AuditLog.query
    if request.args.get("action"):
        q = q.filter(AuditLog.action == request.args["action"])
    return jsonify(paginate(q.order_by(AuditLog.id.desc()), lambda a: a.to_dict()))


# =============================== promotions & newsletter ===============================
@bp.post("/promotions")
@staff
def send_promotion():
    d = request.get_json(silent=True) or {}
    title, message = clean(d.get("title"), 150), clean(d.get("message"), 500)
    audience = d.get("audience", "customers")
    if len(title) < 3 or len(message) < 5:
        return api_error("Add a title and a message")
    if audience not in ("customers", "subscribers", "both"):
        return api_error("Audience must be customers, subscribers or both")
    notifs, mails, sent_to = 0, 0, set()
    if audience in ("customers", "both"):
        users = (User.query.join(Role).filter(Role.name == "customer", User.is_active.is_(True),
                                              User.promo_opt_in.is_(True)).all())
        for u in users:
            db.session.add(Notification(user_id=u.id, title=title, message=message, kind="promo"))
            notifs += 1
            if get_setting("email_notifications") == "true" and len(sent_to) < 500:
                sent_to.add(u.email)
                mails += 1 if send_email(u.email, title, message) else 0
    if audience in ("subscribers", "both"):
        for sub in NewsletterSubscriber.query.limit(500).all():
            if sub.email not in sent_to:
                sent_to.add(sub.email)
                mails += 1 if send_email(sub.email, title, message) else 0
    promo = Promotion(title=title, message=message, audience=audience, notifications_sent=notifs,
                      emails_sent=mails, created_by=g.user.id)
    db.session.add(promo)
    audit("send_promotion", "promotion", title, f"audience={audience} notifications={notifs} emails={mails}")
    db.session.commit()
    return jsonify(promo.to_dict()), 201


@bp.get("/promotions")
@staff
def list_promotions():
    return jsonify(paginate(Promotion.query.order_by(Promotion.id.desc()), lambda p: p.to_dict()))


@bp.get("/subscribers")
@staff
def list_subscribers():
    return jsonify(paginate(NewsletterSubscriber.query.order_by(NewsletterSubscriber.id.desc()), lambda s: {
        "id": s.id, "email": s.email, "created_at": iso(s.created_at)}))


@bp.delete("/subscribers/<int:sid>")
@staff
def delete_subscriber(sid):
    NewsletterSubscriber.query.filter_by(id=sid).delete()
    db.session.commit()
    return jsonify({"message": "Subscriber removed"})


# =============================== seller: orders containing my products ===============================
@bp.get("/seller/orders")
@roles_required("seller")
def seller_orders():
    rows = (db.session.query(Order, OrderItem).join(OrderItem, OrderItem.order_id == Order.id)
            .join(Product, Product.id == OrderItem.product_id).filter(Product.seller_id == _seller_id())
            .order_by(Order.created_at.desc()).limit(300).all())
    out = {}
    for o, i in rows:
        e = out.setdefault(o.id, {"id": o.id, "order_number": o.order_number, "status": o.status,
                                  "payment_status": o.payment_status, "created_at": iso(o.created_at),
                                  "ship_to": json.loads(o.shipping_address).get("city"), "items": [],
                                  "seller_total": 0.0})
        e["items"].append({"name": i.name, "size": i.size, "color": i.color, "quantity": i.quantity, "price": i.price})
        e["seller_total"] = round(e["seller_total"] + i.price * i.quantity, 2)
    return jsonify(list(out.values()))
