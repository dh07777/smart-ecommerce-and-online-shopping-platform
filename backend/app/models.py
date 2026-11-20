"""Relational models for ShopSphere (SQLAlchemy ORM)."""
import json
from sqlalchemy import CheckConstraint, UniqueConstraint
from .extensions import db, utcnow

ORDER_STATUSES = ["pending", "confirmed", "processing", "shipped", "out_for_delivery",
                  "delivered", "cancelled", "returned"]
ROLES = ["super_admin", "store_admin", "seller", "customer"]


def iso(dt):
    return dt.isoformat() + "Z" if dt else None


class Role(db.Model):
    __tablename__ = "roles"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False)


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20))
    avatar = db.Column(db.String(255))
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    promo_opt_in = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    last_login = db.Column(db.DateTime)
    reset_token_hash = db.Column(db.String(64), index=True)
    reset_expires = db.Column(db.DateTime)
    role = db.relationship("Role")
    addresses = db.relationship("Address", backref="user", cascade="all, delete-orphan")

    def to_dict(self):
        return {"id": self.id, "name": self.name, "email": self.email, "phone": self.phone,
                "avatar": self.avatar, "role": self.role.name, "is_active": self.is_active,
                "promo_opt_in": self.promo_opt_in,
                "created_at": iso(self.created_at), "last_login": iso(self.last_login)}


class Address(db.Model):
    __tablename__ = "addresses"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    label = db.Column(db.String(30), default="Home")
    full_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    line1 = db.Column(db.String(255), nullable=False)
    line2 = db.Column(db.String(255))
    city = db.Column(db.String(80), nullable=False)
    state = db.Column(db.String(80), nullable=False)
    postal_code = db.Column(db.String(12), nullable=False)
    country = db.Column(db.String(60), default="India")
    is_default = db.Column(db.Boolean, default=False)

    FIELDS = ["label", "full_name", "phone", "line1", "line2", "city", "state", "postal_code", "country"]

    def to_dict(self):
        d = {k: getattr(self, k) for k in self.FIELDS}
        d.update(id=self.id, is_default=self.is_default)
        return d


class Category(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    image = db.Column(db.String(255))
    parent_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    is_active = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "slug": self.slug, "description": self.description,
                "image": self.image, "parent_id": self.parent_id, "is_active": self.is_active}


class Brand(db.Model):
    __tablename__ = "brands"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    logo = db.Column(db.String(255))

    def to_dict(self):
        return {"id": self.id, "name": self.name, "slug": self.slug, "logo": self.logo}


class Seller(db.Model):
    __tablename__ = "sellers"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    store_name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    is_verified = db.Column(db.Boolean, default=False)
    commission_rate = db.Column(db.Float, default=10.0)
    created_at = db.Column(db.DateTime, default=utcnow)
    user = db.relationship("User", backref=db.backref("seller", uselist=False))

    def to_dict(self):
        return {"id": self.id, "user_id": self.user_id, "store_name": self.store_name,
                "description": self.description, "is_verified": self.is_verified,
                "commission_rate": self.commission_rate, "email": self.user.email,
                "owner": self.user.name, "created_at": iso(self.created_at)}


class Product(db.Model):
    __tablename__ = "products"
    __table_args__ = (CheckConstraint("price >= 0", name="ck_product_price"),)
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    slug = db.Column(db.String(220), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    specifications = db.Column(db.Text, default="{}")  # JSON
    price = db.Column(db.Float, nullable=False)
    mrp = db.Column(db.Float)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False, index=True)
    brand_id = db.Column(db.Integer, db.ForeignKey("brands.id"), index=True)
    seller_id = db.Column(db.Integer, db.ForeignKey("sellers.id"), index=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    is_featured = db.Column(db.Boolean, default=False)
    sold_count = db.Column(db.Integer, default=0)
    views = db.Column(db.Integer, default=0)
    rating_avg = db.Column(db.Float, default=0)
    rating_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)
    category = db.relationship("Category")
    brand = db.relationship("Brand")
    seller = db.relationship("Seller")
    images = db.relationship("ProductImage", backref="product", cascade="all, delete-orphan",
                             order_by="ProductImage.position")
    variants = db.relationship("ProductVariant", backref="product", cascade="all, delete-orphan")

    @property
    def stock(self):
        return sum(v.inventory.quantity for v in self.variants if v.is_active and v.inventory)

    def specs(self):
        try:
            return json.loads(self.specifications or "{}")
        except ValueError:
            return {}

    def to_dict(self, detail=False):
        d = {"id": self.id, "name": self.name, "slug": self.slug, "price": self.price, "mrp": self.mrp,
             "discount_percent": round((1 - self.price / self.mrp) * 100) if self.mrp and self.mrp > self.price else 0,
             "category": {"id": self.category.id, "name": self.category.name, "slug": self.category.slug},
             "brand": {"id": self.brand.id, "name": self.brand.name, "slug": self.brand.slug} if self.brand else None,
             "image": self.images[0].url if self.images else None,
             "rating": round(self.rating_avg or 0, 1), "review_count": self.rating_count or 0,
             "stock": self.stock, "in_stock": self.stock > 0, "is_featured": self.is_featured,
             "is_active": self.is_active, "sold_count": self.sold_count}
        if detail:
            d.update(description=self.description, specifications=self.specs(),
                     images=[{"id": i.id, "url": i.url, "alt": i.alt} for i in self.images],
                     variants=[v.to_dict() for v in self.variants if v.is_active],
                     seller=self.seller.store_name if self.seller else None, views=self.views)
        return d


class ProductImage(db.Model):
    __tablename__ = "product_images"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    url = db.Column(db.String(255), nullable=False)
    alt = db.Column(db.String(200))
    position = db.Column(db.Integer, default=0)


class ProductVariant(db.Model):
    __tablename__ = "product_variants"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    sku = db.Column(db.String(60), unique=True, nullable=False)
    size = db.Column(db.String(30))
    color = db.Column(db.String(30))
    price_delta = db.Column(db.Float, default=0)
    is_active = db.Column(db.Boolean, default=True)
    inventory = db.relationship("Inventory", uselist=False, backref="variant", cascade="all, delete-orphan")

    @property
    def price(self):
        return round(self.product.price + (self.price_delta or 0), 2)

    def to_dict(self):
        return {"id": self.id, "sku": self.sku, "size": self.size, "color": self.color,
                "price": self.price, "price_delta": self.price_delta,
                "stock": self.inventory.quantity if self.inventory else 0}


class Inventory(db.Model):
    __tablename__ = "inventory"
    __table_args__ = (CheckConstraint("quantity >= 0", name="ck_inventory_qty"),)
    id = db.Column(db.Integer, primary_key=True)
    variant_id = db.Column(db.Integer, db.ForeignKey("product_variants.id"), unique=True, nullable=False)
    quantity = db.Column(db.Integer, default=0, nullable=False)
    low_stock_threshold = db.Column(db.Integer, default=10)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)


class StockHistory(db.Model):
    __tablename__ = "stock_history"
    id = db.Column(db.Integer, primary_key=True)
    variant_id = db.Column(db.Integer, db.ForeignKey("product_variants.id"), nullable=False, index=True)
    change = db.Column(db.Integer, nullable=False)
    quantity_after = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(200))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=utcnow)
    variant = db.relationship("ProductVariant")


class Cart(db.Model):
    __tablename__ = "carts"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    coupon_code = db.Column(db.String(40))
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
    items = db.relationship("CartItem", backref="cart", cascade="all, delete-orphan")


class CartItem(db.Model):
    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("cart_id", "variant_id", name="uq_cart_variant"),
                      CheckConstraint("quantity > 0", name="ck_cart_qty"))
    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.Integer, db.ForeignKey("carts.id"), nullable=False, index=True)
    variant_id = db.Column(db.Integer, db.ForeignKey("product_variants.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    variant = db.relationship("ProductVariant")


class Wishlist(db.Model):
    __tablename__ = "wishlists"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    items = db.relationship("WishlistItem", backref="wishlist", cascade="all, delete-orphan")


class WishlistItem(db.Model):
    __tablename__ = "wishlist_items"
    __table_args__ = (UniqueConstraint("wishlist_id", "product_id", name="uq_wishlist_product"),)
    id = db.Column(db.Integer, primary_key=True)
    wishlist_id = db.Column(db.Integer, db.ForeignKey("wishlists.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    added_at = db.Column(db.DateTime, default=utcnow)
    product = db.relationship("Product")


class Coupon(db.Model):
    __tablename__ = "coupons"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, nullable=False, index=True)
    description = db.Column(db.String(200))
    discount_type = db.Column(db.String(10), nullable=False)  # percent | fixed
    value = db.Column(db.Float, nullable=False)
    min_order_value = db.Column(db.Float, default=0)
    max_discount = db.Column(db.Float)
    expires_at = db.Column(db.DateTime)
    usage_limit = db.Column(db.Integer)
    per_user_limit = db.Column(db.Integer, default=1)
    used_count = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {"id": self.id, "code": self.code, "description": self.description,
                "discount_type": self.discount_type, "value": self.value,
                "min_order_value": self.min_order_value, "max_discount": self.max_discount,
                "expires_at": iso(self.expires_at), "usage_limit": self.usage_limit,
                "per_user_limit": self.per_user_limit, "used_count": self.used_count,
                "is_active": self.is_active}


class CouponUsage(db.Model):
    __tablename__ = "coupon_usage"
    id = db.Column(db.Integer, primary_key=True)
    coupon_id = db.Column(db.Integer, db.ForeignKey("coupons.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    discount = db.Column(db.Float, default=0)
    used_at = db.Column(db.DateTime, default=utcnow)


class Order(db.Model):
    __tablename__ = "orders"
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(30), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    status = db.Column(db.String(20), default="pending", nullable=False, index=True)
    subtotal = db.Column(db.Float, nullable=False)
    discount = db.Column(db.Float, default=0)
    tax = db.Column(db.Float, default=0)
    shipping_cost = db.Column(db.Float, default=0)
    total = db.Column(db.Float, nullable=False)
    coupon_code = db.Column(db.String(40))
    delivery_option = db.Column(db.String(20), default="standard")
    shipping_address = db.Column(db.Text, nullable=False)  # JSON snapshot
    billing_address = db.Column(db.Text, nullable=False)
    payment_method = db.Column(db.String(20), nullable=False)
    payment_status = db.Column(db.String(20), default="pending", index=True)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)
    user = db.relationship("User")
    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan")
    payment = db.relationship("Payment", uselist=False, backref="order", cascade="all, delete-orphan")
    shipping = db.relationship("Shipping", uselist=False, backref="order", cascade="all, delete-orphan")
    refunds = db.relationship("Refund", backref="order", cascade="all, delete-orphan")

    def to_dict(self, detail=False):
        d = {"id": self.id, "order_number": self.order_number, "status": self.status,
             "subtotal": self.subtotal, "discount": self.discount, "tax": self.tax,
             "shipping_cost": self.shipping_cost, "total": self.total, "coupon_code": self.coupon_code,
             "payment_method": self.payment_method, "payment_status": self.payment_status,
             "created_at": iso(self.created_at), "item_count": sum(i.quantity for i in self.items),
             "customer": {"id": self.user.id, "name": self.user.name, "email": self.user.email}}
        if detail:
            d.update(delivery_option=self.delivery_option,
                     shipping_address=json.loads(self.shipping_address),
                     billing_address=json.loads(self.billing_address),
                     items=[i.to_dict() for i in self.items],
                     payment=self.payment.to_dict() if self.payment else None,
                     tracking=self.shipping.to_dict() if self.shipping else None,
                     refunds=[r.to_dict() for r in self.refunds])
        return d


class OrderItem(db.Model):
    __tablename__ = "order_items"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    variant_id = db.Column(db.Integer, db.ForeignKey("product_variants.id"))
    name = db.Column(db.String(200), nullable=False)
    size = db.Column(db.String(30))
    color = db.Column(db.String(30))
    price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    product = db.relationship("Product")

    def to_dict(self):
        return {"id": self.id, "product_id": self.product_id, "variant_id": self.variant_id,
                "name": self.name, "size": self.size, "color": self.color, "price": self.price,
                "quantity": self.quantity, "line_total": round(self.price * self.quantity, 2),
                "image": self.product.images[0].url if self.product and self.product.images else None,
                "slug": self.product.slug if self.product else None}


class Payment(db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), unique=True, nullable=False)
    method = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False)  # pending|paid|failed|refunded
    amount = db.Column(db.Float, nullable=False)
    provider_order_id = db.Column(db.String(60), index=True)
    provider_payment_id = db.Column(db.String(60))
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
    transactions = db.relationship("Transaction", backref="payment", cascade="all, delete-orphan")

    def to_dict(self):
        return {"id": self.id, "method": self.method, "status": self.status, "amount": self.amount,
                "provider_order_id": self.provider_order_id, "provider_payment_id": self.provider_payment_id,
                "transactions": [t.to_dict() for t in self.transactions]}


class Transaction(db.Model):
    __tablename__ = "transactions"
    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.Integer, db.ForeignKey("payments.id"), nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False)  # charge | refund | cod_collected | failure
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), nullable=False)
    reference = db.Column(db.String(80))
    note = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {"id": self.id, "kind": self.kind, "amount": self.amount, "status": self.status,
                "reference": self.reference, "note": self.note, "created_at": iso(self.created_at)}


class Shipping(db.Model):
    __tablename__ = "shipping"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), unique=True, nullable=False)
    carrier = db.Column(db.String(60))
    tracking_number = db.Column(db.String(60))
    status = db.Column(db.String(20), default="pending")
    events = db.Column(db.Text, default="[]")  # JSON list
    delivered_at = db.Column(db.DateTime)

    def to_dict(self):
        return {"carrier": self.carrier, "tracking_number": self.tracking_number, "status": self.status,
                "events": json.loads(self.events or "[]"), "delivered_at": iso(self.delivered_at)}

    def add_event(self, status, note=""):
        ev = json.loads(self.events or "[]")
        ev.append({"status": status, "note": note, "at": iso(utcnow())})
        self.events = json.dumps(ev)
        self.status = status


class Refund(db.Model):
    __tablename__ = "refunds"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    kind = db.Column(db.String(20), default="cancellation")  # cancellation | return
    amount = db.Column(db.Float, nullable=False)
    reason = db.Column(db.String(255))
    status = db.Column(db.String(20), default="pending")  # pending|approved|processed|rejected
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    def to_dict(self):
        return {"id": self.id, "order_id": self.order_id, "order_number": self.order.order_number,
                "kind": self.kind, "amount": self.amount, "reason": self.reason, "status": self.status,
                "created_at": iso(self.created_at)}


class Review(db.Model):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_review_user_product"),
                      CheckConstraint("rating BETWEEN 1 AND 5", name="ck_review_rating"))
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    rating = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(120))
    body = db.Column(db.Text)
    verified_purchase = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default="approved", index=True)  # pending|approved|rejected
    created_at = db.Column(db.DateTime, default=utcnow)
    user = db.relationship("User")
    product = db.relationship("Product")

    def to_dict(self):
        return {"id": self.id, "rating": self.rating, "title": self.title, "body": self.body,
                "verified_purchase": self.verified_purchase, "status": self.status,
                "created_at": iso(self.created_at), "user": self.user.name, "user_id": self.user_id,
                "product": {"id": self.product.id, "name": self.product.name, "slug": self.product.slug}}


class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    kind = db.Column(db.String(30), default="info")
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.String(500))
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {"id": self.id, "kind": self.kind, "title": self.title, "message": self.message,
                "is_read": self.is_read, "created_at": iso(self.created_at)}


class SupportTicket(db.Model):
    __tablename__ = "support_tickets"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    name = db.Column(db.String(120))
    email = db.Column(db.String(255), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), default="open", index=True)  # open|in_progress|resolved|closed
    created_at = db.Column(db.DateTime, default=utcnow)
    messages = db.relationship("TicketMessage", backref="ticket", cascade="all, delete-orphan",
                               order_by="TicketMessage.id")

    def to_dict(self, detail=False):
        d = {"id": self.id, "subject": self.subject, "status": self.status, "email": self.email,
             "name": self.name, "created_at": iso(self.created_at)}
        if detail:
            d["messages"] = [m.to_dict() for m in self.messages]
        return d


class TicketMessage(db.Model):
    __tablename__ = "ticket_messages"
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("support_tickets.id"), nullable=False, index=True)
    sender = db.Column(db.String(20), nullable=False)  # customer | staff
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {"id": self.id, "sender": self.sender, "body": self.body, "created_at": iso(self.created_at)}


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    action = db.Column(db.String(60), nullable=False, index=True)
    entity = db.Column(db.String(40))
    entity_id = db.Column(db.String(40))
    details = db.Column(db.String(500))
    ip = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=utcnow, index=True)
    user = db.relationship("User")

    def to_dict(self):
        return {"id": self.id, "user": self.user.email if self.user else None, "action": self.action,
                "entity": self.entity, "entity_id": self.entity_id, "details": self.details,
                "ip": self.ip, "created_at": iso(self.created_at)}


class Setting(db.Model):
    __tablename__ = "settings"
    key = db.Column(db.String(60), primary_key=True)
    value = db.Column(db.String(500))


class RecentlyViewed(db.Model):
    __tablename__ = "recently_viewed"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_recent_user_product"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    viewed_at = db.Column(db.DateTime, default=utcnow, index=True)


class NewsletterSubscriber(db.Model):
    __tablename__ = "newsletter_subscribers"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)


class FAQ(db.Model):
    __tablename__ = "faqs"
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(255), nullable=False)
    answer = db.Column(db.Text, nullable=False)


class RevokedToken(db.Model):
    __tablename__ = "revoked_tokens"
    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(64), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utcnow)


class Promotion(db.Model):
    """History of promotional broadcasts sent by staff."""
    __tablename__ = "promotions"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    audience = db.Column(db.String(20), nullable=False)  # customers | subscribers | both
    notifications_sent = db.Column(db.Integer, default=0)
    emails_sent = db.Column(db.Integer, default=0)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {"id": self.id, "title": self.title, "message": self.message, "audience": self.audience,
                "notifications_sent": self.notifications_sent, "emails_sent": self.emails_sent,
                "created_at": iso(self.created_at)}
