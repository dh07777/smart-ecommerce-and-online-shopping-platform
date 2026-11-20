import hashlib
import secrets
from datetime import timedelta

from flask import Blueprint, current_app, g, jsonify, request
from flask_jwt_extended import (create_access_token, create_refresh_token, get_jwt, get_jwt_identity,
                                jwt_required)
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db, utcnow
from ..models import Address, Cart, RevokedToken, Seller, User, Wishlist
from ..services import get_role, send_email
from ..utils import (api_error, audit, auth_required, clean, password_problem, rate_limit, save_image,
                     valid_email)

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _tokens(user):
    return {"access_token": create_access_token(identity=str(user.id), additional_claims={"role": user.role.name}),
            "refresh_token": create_refresh_token(identity=str(user.id)), "user": user.to_dict()}


def _create_user(d, role_name):
    name, email = clean(d.get("name"), 120), clean(d.get("email")).lower()
    if len(name) < 2:
        return None, api_error("Please enter your name")
    if not valid_email(email):
        return None, api_error("Please enter a valid email")
    problem = password_problem(d.get("password"))
    if problem:
        return None, api_error(problem)
    if User.query.filter_by(email=email).first():
        return None, api_error("An account with this email already exists", 409)
    user = User(name=name, email=email, phone=clean(d.get("phone"), 20), role=get_role(role_name),
                password_hash=generate_password_hash(d["password"]))
    db.session.add(user)
    db.session.flush()
    db.session.add_all([Cart(user_id=user.id), Wishlist(user_id=user.id)])
    return user, None


@bp.post("/register")
@rate_limit(10)
def register():
    user, err = _create_user(request.get_json(silent=True) or {}, "customer")
    if err:
        return err
    audit("register", "user", user.id, user=user)
    db.session.commit()
    return jsonify(_tokens(user)), 201


@bp.post("/register-seller")
@rate_limit(5)
def register_seller():
    d = request.get_json(silent=True) or {}
    store = clean(d.get("store_name"), 120)
    if len(store) < 2:
        return api_error("Please enter a store name")
    user, err = _create_user(d, "seller")
    if err:
        return err
    db.session.add(Seller(user_id=user.id, store_name=store, description=clean(d.get("description"), 1000)))
    audit("register_seller", "user", user.id, user=user)
    db.session.commit()
    return jsonify(_tokens(user)), 201


@bp.post("/login")
@rate_limit(10)
def login():
    d = request.get_json(silent=True) or {}
    user = User.query.filter_by(email=clean(d.get("email")).lower()).first()
    if not user or not check_password_hash(user.password_hash, d.get("password") or ""):
        return api_error("Incorrect email or password", 401)
    if not user.is_active:
        return api_error("This account has been deactivated. Contact support.", 403)
    user.last_login = utcnow()
    audit("login", "user", user.id, user=user)
    db.session.commit()
    return jsonify(_tokens(user))


@bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    user = db.session.get(User, int(get_jwt_identity()))
    if not user or not user.is_active:
        return api_error("Account disabled", 403)
    return jsonify({"access_token": create_access_token(identity=str(user.id), additional_claims={"role": user.role.name})})


@bp.post("/logout")
@jwt_required(verify_type=False)
def logout():
    db.session.add(RevokedToken(jti=get_jwt()["jti"]))
    db.session.commit()
    return jsonify({"message": "Logged out"})


@bp.post("/forgot-password")
@rate_limit(5)
def forgot_password():
    email = clean((request.get_json(silent=True) or {}).get("email")).lower()
    user = User.query.filter_by(email=email).first()
    resp = {"message": "If that email exists, a reset link has been sent."}
    if user and user.is_active:
        token = secrets.token_urlsafe(32)
        user.reset_token_hash = hashlib.sha256(token.encode()).hexdigest()
        user.reset_expires = utcnow() + timedelta(minutes=30)
        link = f"{current_app.config['FRONTEND_URL']}/reset-password?token={token}"
        send_email(user.email, "Reset your ShopSphere password", f"Use this link within 30 minutes:\n{link}")
        audit("forgot_password", "user", user.id, user=user)
        db.session.commit()
        if current_app.config["EXPOSE_RESET_TOKEN"]:  # development convenience only
            resp["dev_reset_token"] = token
            resp["dev_reset_link"] = link
    return jsonify(resp)


@bp.post("/reset-password")
@rate_limit(10)
def reset_password():
    d = request.get_json(silent=True) or {}
    token = d.get("token") or ""
    problem = password_problem(d.get("password"))
    if problem:
        return api_error(problem)
    user = User.query.filter_by(reset_token_hash=hashlib.sha256(token.encode()).hexdigest()).first()
    if not token or not user or not user.reset_expires or user.reset_expires < utcnow():
        return api_error("This reset link is invalid or has expired", 400)
    user.password_hash = generate_password_hash(d["password"])
    user.reset_token_hash, user.reset_expires = None, None
    audit("reset_password", "user", user.id, user=user)
    db.session.commit()
    return jsonify({"message": "Password updated. You can now log in."})


@bp.get("/me")
@auth_required
def me():
    return jsonify(g.user.to_dict())


@bp.put("/me")
@auth_required
def update_me():
    d = request.get_json(silent=True) or {}
    name = clean(d.get("name"), 120)
    if name:
        g.user.name = name
    if "phone" in d:
        g.user.phone = clean(d.get("phone"), 20)
    if "promo_opt_in" in d:
        g.user.promo_opt_in = bool(d["promo_opt_in"])
    db.session.commit()
    return jsonify(g.user.to_dict())


@bp.delete("/me")
@auth_required
def deactivate_me():
    d = request.get_json(silent=True) or {}
    if not check_password_hash(g.user.password_hash, d.get("password") or ""):
        return api_error("Password is incorrect", 403)
    g.user.is_active = False
    audit("deactivate_account", "user", g.user.id)
    db.session.commit()
    return jsonify({"message": "Account deactivated"})


@bp.post("/change-password")
@auth_required
@rate_limit(10)
def change_password():
    d = request.get_json(silent=True) or {}
    if not check_password_hash(g.user.password_hash, d.get("current_password") or ""):
        return api_error("Current password is incorrect", 403)
    problem = password_problem(d.get("new_password"))
    if problem:
        return api_error(problem)
    g.user.password_hash = generate_password_hash(d["new_password"])
    audit("change_password", "user", g.user.id)
    db.session.commit()
    return jsonify({"message": "Password changed"})


@bp.post("/avatar")
@auth_required
def upload_avatar():
    try:
        g.user.avatar = save_image(request.files.get("file"), "avatars", max_px=400)
    except ValueError as e:
        return api_error(str(e))
    db.session.commit()
    return jsonify(g.user.to_dict())


# ---------- addresses ----------
def _address_from(d):
    data = {k: clean(d.get(k), 255) for k in Address.FIELDS}
    for req in ("full_name", "phone", "line1", "city", "state", "postal_code"):
        if not data[req]:
            return None, f"{req.replace('_', ' ').capitalize()} is required"
    if not data["postal_code"].replace(" ", "").isalnum() or len(data["postal_code"]) > 10:
        return None, "Invalid postal code"
    data["label"] = data["label"] or "Home"
    data["country"] = data["country"] or "India"
    return data, None


@bp.get("/addresses")
@auth_required
def list_addresses():
    return jsonify([a.to_dict() for a in g.user.addresses])


@bp.post("/addresses")
@auth_required
def add_address():
    d = request.get_json(silent=True) or {}
    data, err = _address_from(d)
    if err:
        return api_error(err)
    addr = Address(user_id=g.user.id, **data, is_default=bool(d.get("is_default")) or not g.user.addresses)
    if addr.is_default:
        for a in g.user.addresses:
            a.is_default = False
    db.session.add(addr)
    db.session.commit()
    return jsonify(addr.to_dict()), 201


@bp.put("/addresses/<int:aid>")
@auth_required
def edit_address(aid):
    addr = Address.query.filter_by(id=aid, user_id=g.user.id).first_or_404()
    d = request.get_json(silent=True) or {}
    data, err = _address_from(d)
    if err:
        return api_error(err)
    for k, v in data.items():
        setattr(addr, k, v)
    if d.get("is_default"):
        for a in g.user.addresses:
            a.is_default = a.id == addr.id
    db.session.commit()
    return jsonify(addr.to_dict())


@bp.delete("/addresses/<int:aid>")
@auth_required
def delete_address(aid):
    addr = Address.query.filter_by(id=aid, user_id=g.user.id).first_or_404()
    db.session.delete(addr)
    db.session.commit()
    return jsonify({"message": "Address removed"})
