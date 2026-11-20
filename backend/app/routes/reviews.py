from flask import Blueprint, g, jsonify, request
from sqlalchemy import func

from ..extensions import db
from ..models import Order, OrderItem, Product, Review
from ..utils import api_error, audit, auth_required, clean, optional_user, paginate, to_int

bp = Blueprint("reviews", __name__, url_prefix="/api")

BANNED = ("scam", "idiot", "stupid", "fraud", "hate you", "http://", "https://", "www.")


def refresh_rating(product):
    avg, cnt = db.session.query(func.avg(Review.rating), func.count(Review.id)).filter(
        Review.product_id == product.id, Review.status == "approved").one()
    product.rating_avg = round(float(avg or 0), 2)
    product.rating_count = cnt or 0


def _validated(d):
    rating = to_int(d.get("rating"))
    if rating is None or not 1 <= rating <= 5:
        return None, "Rating must be between 1 and 5"
    body = clean(d.get("body"), 2000)
    if len(body) < 3:
        return None, "Please write a short review"
    return {"rating": rating, "title": clean(d.get("title"), 120), "body": body}, None


def _initial_status(text):
    return "pending" if any(b in text.lower() for b in BANNED) else "approved"


@bp.get("/products/<int:pid>/reviews")
def product_reviews(pid):
    user = optional_user()
    q = Review.query.filter_by(product_id=pid, status="approved").order_by(Review.created_at.desc())
    data = paginate(q, lambda r: r.to_dict())
    breakdown = dict(db.session.query(Review.rating, func.count(Review.id))
                     .filter_by(product_id=pid, status="approved").group_by(Review.rating))
    data["breakdown"] = {str(i): breakdown.get(i, 0) for i in range(1, 6)}
    if user:
        mine = Review.query.filter_by(product_id=pid, user_id=user.id).first()
        data["mine"] = mine.to_dict() if mine else None
        data["can_review"] = mine is None
    return jsonify(data)


@bp.post("/products/<int:pid>/reviews")
@auth_required
def add_review(pid):
    product = db.session.get(Product, pid)
    if not product:
        return api_error("Product not found", 404)
    if Review.query.filter_by(product_id=pid, user_id=g.user.id).first():
        return api_error("You have already reviewed this product", 409)
    data, err = _validated(request.get_json(silent=True) or {})
    if err:
        return api_error(err)
    verified = db.session.query(OrderItem.id).join(Order).filter(
        Order.user_id == g.user.id, OrderItem.product_id == pid,
        Order.status.in_(["delivered", "shipped", "out_for_delivery"])).first() is not None
    review = Review(user_id=g.user.id, product_id=pid, verified_purchase=verified,
                    status=_initial_status(data["title"] + " " + data["body"]), **data)
    db.session.add(review)
    db.session.flush()
    refresh_rating(product)
    db.session.commit()
    resp = review.to_dict()
    if review.status == "pending":
        resp["notice"] = "Your review is awaiting moderation."
    return jsonify(resp), 201


@bp.get("/reviews/mine")
@auth_required
def my_reviews():
    rows = Review.query.filter_by(user_id=g.user.id).order_by(Review.created_at.desc()).all()
    return jsonify([r.to_dict() for r in rows])


@bp.put("/reviews/<int:rid>")
@auth_required
def edit_review(rid):
    review = Review.query.filter_by(id=rid, user_id=g.user.id).first_or_404()
    data, err = _validated(request.get_json(silent=True) or {})
    if err:
        return api_error(err)
    for k, v in data.items():
        setattr(review, k, v)
    review.status = _initial_status(data["title"] + " " + data["body"])
    refresh_rating(review.product)
    db.session.commit()
    return jsonify(review.to_dict())


@bp.delete("/reviews/<int:rid>")
@auth_required
def delete_review(rid):
    review = db.session.get(Review, rid)
    if not review or (review.user_id != g.user.id and g.user.role.name not in ("super_admin", "store_admin")):
        return api_error("Review not found", 404)
    product = review.product
    db.session.delete(review)
    db.session.flush()
    refresh_rating(product)
    audit("delete_review", "review", rid)
    db.session.commit()
    return jsonify({"message": "Review deleted"})
