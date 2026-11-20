from flask import Blueprint, g, jsonify, request
from sqlalchemy import func, or_

from ..extensions import db, utcnow
from ..models import (FAQ, Brand, Category, Inventory, NewsletterSubscriber, Order, OrderItem, Product,
                      ProductVariant, RecentlyViewed)
from ..services import PUBLIC_SETTING_KEYS, get_setting
from ..utils import (api_error, auth_required, clean, optional_user, paginate, rate_limit, to_float,
                     valid_email)

bp = Blueprint("catalog", __name__, url_prefix="/api")

SORTS = {"newest": Product.created_at.desc(), "price_asc": Product.price.asc(),
         "price_desc": Product.price.desc(), "popular": Product.sold_count.desc(),
         "rating": Product.rating_avg.desc()}


def _search_filter(q, text):
    for token in text.split()[:6]:  # advanced search: every word must match somewhere
        like = f"%{token}%"
        q = q.filter(or_(Product.name.ilike(like), Product.description.ilike(like),
                         Brand.name.ilike(like), Category.name.ilike(like)))
    return q


@bp.get("/products")
def list_products():
    q = Product.query.filter(Product.is_active.is_(True)).join(Category).outerjoin(Brand)
    a = request.args
    if a.get("q"):
        q = _search_filter(q, clean(a["q"], 100))
    if a.get("category"):
        cats = [c for c in a["category"].split(",") if c]
        q = q.filter(Category.slug.in_(cats))
    if a.get("brand"):
        q = q.filter(Brand.slug.in_([b for b in a["brand"].split(",") if b]))
    if a.get("min_price") is not None and to_float(a.get("min_price")) is not None:
        q = q.filter(Product.price >= to_float(a["min_price"]))
    if a.get("max_price") is not None and to_float(a.get("max_price")) is not None:
        q = q.filter(Product.price <= to_float(a["max_price"]))
    if to_float(a.get("min_rating")) is not None:
        q = q.filter(Product.rating_avg >= to_float(a["min_rating"]))
    if a.get("in_stock") in ("1", "true"):
        q = q.filter(Product.id.in_(
            db.session.query(ProductVariant.product_id).join(Inventory, Inventory.variant_id == ProductVariant.id)
            .filter(Inventory.quantity > 0, ProductVariant.is_active.is_(True))))
    section = a.get("section")
    if section == "featured":
        q = q.filter(Product.is_featured.is_(True))
    order = SORTS.get(a.get("sort"), Product.created_at.desc())
    if section == "trending":
        order = Product.views.desc()
    elif section == "bestsellers":
        order = Product.sold_count.desc()
    elif section == "new":
        order = Product.created_at.desc()
    return jsonify(paginate(q.order_by(order, Product.id), lambda p: p.to_dict()))


@bp.get("/products/suggestions")
def suggestions():
    text = clean(request.args.get("q"), 60)
    if len(text) < 2:
        return jsonify([])
    rows = Product.query.filter(Product.is_active.is_(True), Product.name.ilike(f"%{text}%")).limit(6).all()
    return jsonify([{"name": p.name, "slug": p.slug, "image": p.images[0].url if p.images else None,
                     "price": p.price} for p in rows])


@bp.get("/products/recently-viewed")
@auth_required
def recently_viewed():
    rows = (RecentlyViewed.query.filter_by(user_id=g.user.id).order_by(RecentlyViewed.viewed_at.desc())
            .limit(8).all())
    prods = [db.session.get(Product, r.product_id) for r in rows]
    return jsonify([p.to_dict() for p in prods if p and p.is_active])


@bp.get("/products/recommendations")
def recommendations():
    """Personalised: categories/brands from purchases + browsing; fallback to best sellers."""
    user = optional_user()
    limit = 8
    picks, seen = [], set()
    if user:
        bought = {pid for (pid,) in db.session.query(OrderItem.product_id).join(Order)
                  .filter(Order.user_id == user.id, Order.status != "cancelled")}
        viewed = {r.product_id for r in RecentlyViewed.query.filter_by(user_id=user.id)}
        seen = bought
        weights = {}
        for pid, w in [(p, 3) for p in bought] + [(p, 1) for p in viewed]:
            prod = db.session.get(Product, pid)
            if prod:
                weights[prod.category_id] = weights.get(prod.category_id, 0) + w
        for cat_id, _ in sorted(weights.items(), key=lambda kv: -kv[1])[:3]:
            for p in (Product.query.filter(Product.category_id == cat_id, Product.is_active.is_(True),
                                           ~Product.id.in_(seen or [0]))
                      .order_by(Product.rating_avg.desc(), Product.sold_count.desc()).limit(4)):
                if p.id not in {x.id for x in picks}:
                    picks.append(p)
    if len(picks) < limit:
        ids = [p.id for p in picks] + list(seen)
        picks += (Product.query.filter(Product.is_active.is_(True), ~Product.id.in_(ids or [0]))
                  .order_by(Product.sold_count.desc()).limit(limit - len(picks)).all())
    return jsonify([p.to_dict() for p in picks[:limit]])


@bp.get("/products/<slug>")
def product_detail(slug):
    p = (Product.query.filter_by(slug=slug).first() if not slug.isdigit()
         else db.session.get(Product, int(slug)))
    if not p or not p.is_active:
        return api_error("Product not found", 404)
    p.views = (p.views or 0) + 1
    user = optional_user()
    if user:
        rv = RecentlyViewed.query.filter_by(user_id=user.id, product_id=p.id).first()
        if rv:
            rv.viewed_at = utcnow()
        else:
            db.session.add(RecentlyViewed(user_id=user.id, product_id=p.id))
    db.session.commit()
    related = (Product.query.filter(Product.category_id == p.category_id, Product.id != p.id,
                                    Product.is_active.is_(True))
               .order_by(Product.rating_avg.desc()).limit(4).all())
    d = p.to_dict(detail=True)
    d["related"] = [r.to_dict() for r in related]
    return jsonify(d)


@bp.get("/categories")
def categories():
    counts = dict(db.session.query(Product.category_id, func.count(Product.id))
                  .filter(Product.is_active.is_(True)).group_by(Product.category_id))
    return jsonify([{**c.to_dict(), "product_count": counts.get(c.id, 0)}
                    for c in Category.query.filter_by(is_active=True).order_by(Category.name)])


@bp.get("/brands")
def brands():
    return jsonify([b.to_dict() for b in Brand.query.order_by(Brand.name)])


@bp.get("/settings/public")
def public_settings():
    return jsonify({k: get_setting(k) for k in PUBLIC_SETTING_KEYS})


@bp.post("/newsletter")
@rate_limit(10)
def newsletter():
    email = clean((request.get_json(silent=True) or {}).get("email")).lower()
    if not valid_email(email):
        return api_error("Please enter a valid email")
    if not NewsletterSubscriber.query.filter_by(email=email).first():
        db.session.add(NewsletterSubscriber(email=email))
        db.session.commit()
    return jsonify({"message": "Thanks for subscribing!"})


@bp.post("/newsletter/unsubscribe")
@rate_limit(10)
def newsletter_unsubscribe():
    email = clean((request.get_json(silent=True) or {}).get("email")).lower()
    NewsletterSubscriber.query.filter_by(email=email).delete()
    db.session.commit()
    return jsonify({"message": "You have been unsubscribed."})


@bp.get("/faqs")
def faqs():
    return jsonify([{"id": f.id, "question": f.question, "answer": f.answer} for f in FAQ.query.all()])
