"""Seed ShopSphere with realistic demo data.

Usage:   python seed.py --reset      (drops all tables, recreates, seeds)
         python seed.py              (seeds only if the database is empty)
"""
import argparse
import json
import os
import random
import textwrap
from datetime import timedelta

from PIL import Image, ImageDraw, ImageFont
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db, utcnow
from app.models import (FAQ, Address, Brand, Cart, Category, Coupon, CouponUsage, Inventory, Notification,
                        Order, OrderItem, Payment, Product, ProductImage, ProductVariant, Refund, Review,
                        Role, Seller, Setting, Shipping, StockHistory, SupportTicket, TicketMessage,
                        Transaction, User, Wishlist, ROLES)
from app.services import DEFAULT_SETTINGS, calc_totals, new_order_number
from app.utils import slugify

random.seed(42)

# name, gradient colours, brands, price range, product types, sizes, colours, spec keys, feature phrases
CATALOG = [
    ("Smartphones", ((79, 70, 229), (236, 72, 153)), ["Nexa", "Voltix", "Orbitron"], (9999, 89999),
     ["5G Smartphone", "Pro Max Smartphone", "Lite Smartphone", "Camera Phone", "Gaming Smartphone",
      "Compact Smartphone", "Foldable Phone", "Rugged Smartphone", "Flagship Smartphone"],
     ["128GB", "256GB"], ["Midnight Black", "Ocean Blue", "Pearl White"],
     {"Display": ['6.1" OLED', '6.5" AMOLED', '6.7" LTPO'], "Battery": ["4500 mAh", "5000 mAh"],
      "Camera": ["50 MP", "64 MP", "108 MP"], "Processor": ["Octa-core 3.0 GHz", "Octa-core 2.6 GHz"]},
     ["a vivid high-refresh display", "all-day battery life with fast charging", "a multi-lens camera system",
      "5G connectivity", "a slim, durable body", "smooth, lag-free performance"]),
    ("Laptops", ((14, 116, 144), (99, 102, 241)), ["Zephyr", "Lumina", "Corvex"], (29999, 149999),
     ["Ultrabook 14-inch", "Gaming Laptop 15.6-inch", "Business Laptop 14-inch", "Student Laptop 15-inch",
      "Creator Laptop 16-inch", "2-in-1 Convertible Laptop", "Chromebook 11-inch", "Workstation Laptop 17-inch",
      "Thin & Light Laptop 13-inch"],
     ["8GB/256GB", "16GB/512GB"], ["Space Grey", "Silver"],
     {"Processor": ["Core i5", "Core i7", "Ryzen 5", "Ryzen 7"], "Display": ['14" FHD', '15.6" FHD', '16" QHD'],
      "Battery": ["8 hours", "10 hours", "14 hours"], "OS": ["Windows 11", "ChromeOS"]},
     ["a fast SSD for instant boot", "a backlit keyboard", "a crisp anti-glare display", "long battery life",
      "a lightweight aluminium chassis", "plenty of ports for everyday work"]),
    ("Audio", ((124, 58, 237), (14, 165, 233)), ["Sonara", "Auralis", "BeatForge"], (799, 19999),
     ["Wireless Earbuds", "Over-Ear Headphones", "Bluetooth Speaker", "2.1 Soundbar", "Noise Cancelling Headphones",
      "Neckband Earphones", "Portable Party Speaker", "Studio Headphones", "Gaming Headset"],
     [None], ["Black", "White", "Blue"],
     {"Connectivity": ["Bluetooth 5.3", "Bluetooth 5.0", "Wired + Bluetooth"], "Battery": ["12 hours", "24 hours", "40 hours"],
      "Driver": ["10 mm", "40 mm", "50 mm"]},
     ["deep, balanced bass", "crystal clear mids and highs", "a comfortable all-day fit", "quick pairing",
      "a built-in microphone for calls", "a splash-resistant build"]),
    ("Smart Watches", ((190, 24, 93), (249, 115, 22)), ["Chronix", "Pulsewear", "Vitalis"], (1499, 29999),
     ["Fitness Smartwatch", "AMOLED Smartwatch", "Kids GPS Watch", "Sports Smartwatch", "Hybrid Classic Watch",
      "Fitness Band", "Rugged Outdoor Watch", "Calling Smartwatch", "Titanium Smartwatch"],
     ["40mm", "44mm"], ["Black", "Silver", "Rose Gold"],
     {"Display": ['1.4" AMOLED', '1.8" LCD', '1.3" MIP'], "Battery": ["5 days", "7 days", "14 days"],
      "Water Resistance": ["5 ATM", "IP68"]},
     ["24/7 heart-rate and SpO2 tracking", "built-in GPS", "100+ sports modes", "sleep and stress insights",
      "customisable watch faces", "smart notifications on your wrist"]),
    ("Men's Fashion", ((30, 64, 175), (15, 118, 110)), ["Urbanic", "Stridewell", "Northloom"], (499, 6999),
     ["Slim Fit Cotton Shirt", "Classic Denim Jacket", "Crew Neck T-Shirt", "Stretch Chino Trousers",
      "Wool Blend Sweater", "Hooded Sweatshirt", "Linen Casual Shirt", "Track Pants", "Tailored Blazer"],
     ["S", "M", "L", "XL"], ["Navy", "Charcoal", "Olive", "White"],
     {"Fabric": ["100% Cotton", "Cotton Blend", "Linen Blend", "Wool Blend"], "Fit": ["Slim", "Regular", "Relaxed"],
      "Care": ["Machine wash", "Dry clean only", "Hand wash"]},
     ["soft, breathable fabric", "a tailored, flattering fit", "durable stitching that lasts", "an easy-care finish",
      "a versatile look from work to weekend", "a classic design that never goes out of style"]),
    ("Women's Fashion", ((190, 18, 60), (147, 51, 234)), ["Elara", "Velvet & Oak", "Maisonne"], (599, 7999),
     ["Floral Midi Dress", "High-Rise Jeans", "Cotton Kurti", "Pleated Skirt", "Knit Cardigan", "Satin Blouse",
      "Palazzo Pants", "Wrap Dress", "Oversized Hoodie"],
     ["XS", "S", "M", "L"], ["Rose", "Teal", "Black", "Ivory"],
     {"Fabric": ["Cotton", "Rayon", "Satin", "Viscose Blend"], "Fit": ["Regular", "Relaxed", "A-line"],
      "Care": ["Machine wash", "Hand wash"]},
     ["a graceful drape", "breathable, skin-friendly fabric", "a flattering silhouette", "vibrant colours that stay fresh",
      "easy styling for any occasion", "a comfortable all-day feel"]),
    ("Footwear", ((6, 95, 70), (202, 138, 4)), ["Strideon", "Paceline", "Solewise"], (799, 8999),
     ["Running Shoes", "Leather Sneakers", "Canvas Slip-Ons", "Trail Hiking Boots", "Formal Oxford Shoes",
      "Sports Sandals", "Casual Loafers", "High-Top Sneakers", "Training Shoes"],
     ["7", "8", "9", "10"], ["Black", "White", "Grey"],
     {"Sole": ["EVA", "Rubber", "TPU"], "Upper": ["Mesh", "Leather", "Canvas", "Synthetic"], "Closure": ["Lace-up", "Slip-on", "Velcro"]},
     ["cushioned all-day comfort", "a grippy, durable outsole", "a breathable upper", "a lightweight build",
      "a supportive footbed", "a clean look that pairs with anything"]),
    ("Home & Kitchen", ((180, 83, 9), (22, 101, 52)), ["Homecrest", "Kitchenly", "Nestora"], (599, 24999),
     ["Air Fryer 4L", "Non-Stick Cookware Set", "Stainless Steel Kettle", "Mixer Grinder 750W", "Memory Foam Pillow",
      "Cotton Bedsheet Set", "Vacuum Flask 1L", "Robot Vacuum Cleaner", "LED Desk Lamp"],
     [None], ["Black", "White", "Steel"],
     {"Material": ["Stainless Steel", "Cotton", "ABS Plastic", "Aluminium"], "Power": ["750 W", "1500 W", "N/A"],
      "Warranty": ["1 year", "2 years"]},
     ["effortless everyday use", "a premium, easy-to-clean finish", "safe, food-grade materials",
      "energy-efficient operation", "a space-saving design", "reliable build quality"]),
    ("Beauty & Care", ((219, 39, 119), (234, 179, 8)), ["Glowlab", "Purelle", "Auraskin"], (199, 3999),
     ["Vitamin C Face Serum", "Hydrating Moisturiser", "Matte Lipstick", "SPF 50 Sunscreen", "Argan Hair Oil",
      "Charcoal Face Wash", "Beard Grooming Kit", "Eau de Parfum", "Ionic Hair Dryer"],
     ["50ml", "100ml"], [None],
     {"Skin Type": ["All skin types", "Oily", "Dry", "Sensitive"], "Shelf Life": ["24 months", "18 months", "36 months"],
      "Origin": ["Made in India"]},
     ["dermatologically tested ingredients", "a lightweight, non-greasy feel", "visible results with regular use",
      "cruelty-free formulation", "a pleasant, subtle fragrance", "gentle on daily use"]),
    ("Sports & Fitness", ((220, 38, 38), (30, 58, 138)), ["Fitora", "ProMotion", "Athlix"], (299, 7999),
     ["Yoga Mat 6mm", "Adjustable Dumbbell Set", "Resistance Bands Set", "Willow Cricket Bat", "Football Size 5",
      "Badminton Racket Pair", "Skipping Rope", "Gym Duffel Bag", "Insulated Sports Bottle"],
     [None], ["Black", "Blue", "Red"],
     {"Material": ["TPE", "Cast Iron", "Latex", "Polyester"], "Level": ["Beginner", "Intermediate", "Pro"],
      "Warranty": ["6 months", "1 year"]},
     ["a non-slip, sweat-proof grip", "rugged construction built for training", "easy storage and portability",
      "a comfortable feel through long sessions", "trusted by weekend athletes", "great value for performance"]),
    ("Stationery & Office", ((71, 85, 105), (13, 148, 136)), ["Papermint", "Inkwell", "Scribbly"], (99, 2499),
     ["Hardcover Notebook A5", "Fountain Pen Set", "Gel Pen Pack of 10", "Desk Organiser", "Sketchbook 120 GSM",
      "Productivity Planner", "Highlighter Set", "Scientific Calculator", "Leather Journal"],
     [None], ["Black", "Navy", "Green"],
     {"Pages": ["120", "160", "200"], "Paper": ["80 GSM", "100 GSM", "120 GSM"], "Binding": ["Hardcover", "Spiral", "Stitched"]},
     ["smooth, bleed-resistant paper", "a sturdy, good-looking cover", "a smooth writing experience",
      "an organised layout", "an eco-friendly build", "a gift-worthy finish"]),
    ("Toys & Games", ((234, 88, 12), (59, 130, 246)), ["Playnest", "Kidoodle", "Funforge"], (249, 4999),
     ["Building Blocks 500 pcs", "Remote Control Car", "Strategy Board Game", "Plush Teddy Bear",
      "1000-piece Jigsaw Puzzle", "Science Experiment Kit", "Art & Craft Set", "Wooden Train Set", "Party Card Game"],
     [None], [None],
     {"Age Group": ["3+ years", "5+ years", "8+ years", "12+ years"], "Players": ["1", "2-4", "2-6"],
      "Material": ["BPA-free plastic", "Wood", "Cardboard", "Plush"]},
     ["hours of screen-free fun", "child-safe, non-toxic materials", "builds creativity and problem solving",
      "a great gift for birthdays", "durable parts built to last", "easy-to-follow instructions"]),
]

SEED_DIR = None


def font(size):
    for name in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf", "Helvetica.ttc"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def make_image(path, c1, c2, title, label, style):
    """Locally generated illustrative product card (no external image dependencies)."""
    S = 640
    img = Image.new("RGB", (S, S))
    d = ImageDraw.Draw(img)
    for y in range(S):
        t = y / S
        col = tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3))
        d.line([(0, y), (S, y)], fill=col)
    overlay = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    o = ImageDraw.Draw(overlay)
    if style == 0:
        o.ellipse([-120, -120, 360, 360], fill=(255, 255, 255, 38))
        o.ellipse([300, 330, 760, 790], fill=(255, 255, 255, 30))
    else:
        o.rounded_rectangle([60, 60, 580, 580], radius=48, outline=(255, 255, 255, 120), width=6)
        o.ellipse([380, 40, 620, 280], fill=(255, 255, 255, 36))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    d = ImageDraw.Draw(img)
    d.text((48, 40), label.upper(), font=font(26), fill=(255, 255, 255))
    f = font(46)
    lines = textwrap.wrap(title, 16)[:4]
    heights = [d.textbbox((0, 0), ln, font=f)[3] + 14 for ln in lines]
    y = (S - sum(heights)) // 2
    for ln, h in zip(lines, heights):
        w = d.textbbox((0, 0), ln, font=f)[2]
        d.text(((S - w) // 2, y), ln, font=f, fill=(255, 255, 255))
        y += h
    img.save(path, "JPEG", quality=85)


def build(app):
    global SEED_DIR
    SEED_DIR = os.path.join(app.config["UPLOAD_DIR"], "seed")
    os.makedirs(SEED_DIR, exist_ok=True)
    now = utcnow()

    roles = {n: Role(name=n) for n in ROLES}
    db.session.add_all(roles.values())
    for k, v in DEFAULT_SETTINGS.items():
        db.session.add(Setting(key=k, value=v))

    def user(name, email, pw, role, days_ago=60, phone=None):
        u = User(name=name, email=email, password_hash=generate_password_hash(pw), role=roles[role],
                 phone=phone or f"9{random.randint(100000000, 999999999)}", created_at=now - timedelta(days=days_ago))
        db.session.add(u)
        db.session.flush()
        db.session.add_all([Cart(user_id=u.id), Wishlist(user_id=u.id)])
        return u

    user("Super Admin", "admin@shopsphere.com", "Admin@123", "super_admin", 200)
    user("Store Manager", "manager@shopsphere.com", "Manager@123", "store_admin", 180)
    s1u = user("Meera Nair", "seller1@shopsphere.com", "Seller@123", "seller", 150)
    s2u = user("Rohit Verma", "seller2@shopsphere.com", "Seller@123", "seller", 10)
    seller1 = Seller(user_id=s1u.id, store_name="Nair Electronics & Lifestyle", is_verified=True,
                     description="Authorised reseller of electronics and lifestyle products since 2015.")
    seller2 = Seller(user_id=s2u.id, store_name="Verma Traders", is_verified=False,
                     description="New seller awaiting verification.")
    db.session.add_all([seller1, seller2])

    names = [("Aarav", "Sharma"), ("Diya", "Patel"), ("Vihaan", "Reddy"), ("Ananya", "Iyer"), ("Kabir", "Singh"),
             ("Ishita", "Gupta"), ("Arjun", "Mehta"), ("Saanvi", "Das"), ("Reyansh", "Khan"), ("Myra", "Joshi")]
    cities = [("Bengaluru", "Karnataka", "560001"), ("Mumbai", "Maharashtra", "400001"), ("Delhi", "Delhi", "110001"),
              ("Chennai", "Tamil Nadu", "600001"), ("Hyderabad", "Telangana", "500001"), ("Pune", "Maharashtra", "411001")]
    customers = []
    for i, (fn, ln) in enumerate(names):
        email = "customer@shopsphere.com" if i == 0 else f"{fn.lower()}.{ln.lower()}@example.com"
        u = user(f"{fn} {ln}", email, "Customer@123", "customer", random.randint(20, 120))
        c = cities[i % len(cities)]
        db.session.add(Address(user_id=u.id, full_name=u.name, phone=u.phone, line1=f"{random.randint(10, 99)}, MG Road",
                               line2="Near City Mall", city=c[0], state=c[1], postal_code=c[2], is_default=True))
        customers.append(u)
    db.session.flush()

    # ---- catalogue ----
    products = []
    for ci, (cname, (c1, c2), brands, (lo, hi), types, sizes, colors, specs, feats) in enumerate(CATALOG):
        cat = Category(name=cname, slug=slugify(cname), description=f"Shop the best of {cname.lower()}.")
        db.session.add(cat)
        brand_objs = []
        for b in brands:
            bo = Brand.query.filter_by(name=b).first() or Brand(name=b, slug=slugify(b))
            db.session.add(bo)
            brand_objs.append(bo)
        db.session.flush()
        for ti, ptype in enumerate(types):
            brand = brand_objs[ti % len(brand_objs)]
            series = ["Air", "Prime", "Neo", "Edge", "Core", "Plus", "Max", "One", "Go"][ti]
            name = f"{brand.name} {series} {ptype}"
            price = round(random.uniform(lo, hi), -1) - 1
            price = max(price, lo)
            mrp = round(price * random.uniform(1.1, 1.45), -1) - 1
            picks = random.sample(feats, 3)
            desc = (f"The {name} brings {picks[0]}, {picks[1]} and {picks[2]} to your everyday routine. "
                    f"Designed by {brand.name} for people who want reliable quality without compromise, it has been "
                    f"tested for durability and comes with a manufacturer warranty. Every order includes free "
                    f"invoice, secure packaging and an easy 7-day return policy.")
            p = Product(name=name, slug=slugify(name), description=desc, price=price, mrp=mrp, category_id=cat.id,
                        brand_id=brand.id, seller_id=seller1.id if random.random() < 0.35 else None,
                        is_featured=random.random() < 0.22, views=random.randint(10, 2500),
                        created_at=now - timedelta(days=random.randint(0, 120)),
                        specifications=json.dumps({k: random.choice(v) for k, v in specs.items()} | {"Brand": brand.name}))
            db.session.add(p)
            db.session.flush()
            for style in (0, 1):
                fname = f"p{p.id}_{style}.jpg"
                make_image(os.path.join(SEED_DIR, fname), c1, c2, ptype, cname, style)
                db.session.add(ProductImage(product_id=p.id, url=f"/uploads/seed/{fname}", alt=name, position=style))
            combos = [(s, c) for s in sizes for c in colors]
            random.shuffle(combos)
            for vi, (s, c) in enumerate(combos[:4]):
                v = ProductVariant(product_id=p.id, sku=f"SS{p.id:04d}-{vi + 1}", size=s, color=c,
                                   price_delta=random.choice([0, 0, 0, 500, 1000]) if (s and sizes[-1] == s and cname in ("Smartphones", "Laptops")) else 0)
                db.session.add(v)
                db.session.flush()
                r = random.random()
                qty = 0 if r < 0.04 else random.randint(2, 9) if r < 0.14 else random.randint(20, 150)
                db.session.add(Inventory(variant_id=v.id, quantity=qty, low_stock_threshold=10))
                db.session.add(StockHistory(variant_id=v.id, change=qty, quantity_after=qty, reason="Initial stock"))
            products.append(p)
    db.session.flush()
    print(f"  {len(products)} products, {len(CATALOG)} categories")

    # ---- coupons ----
    db.session.add_all([
        Coupon(code="WELCOME10", description="10% off your order (max ₹500)", discount_type="percent", value=10,
               min_order_value=499, max_discount=500, per_user_limit=1),
        Coupon(code="FLAT200", description="₹200 off orders above ₹1999", discount_type="fixed", value=200,
               min_order_value=1999, per_user_limit=3),
        Coupon(code="SAVE25", description="25% off (max ₹1500) on orders above ₹2999", discount_type="percent", value=25,
               min_order_value=2999, max_discount=1500, usage_limit=100, per_user_limit=1,
               expires_at=now + timedelta(days=90)),
        Coupon(code="OLD5", description="Expired demo coupon", discount_type="percent", value=5,
               expires_at=now - timedelta(days=5)),
    ])
    db.session.add_all([FAQ(question=q, answer=a) for q, a in [
        ("How long does delivery take?", "Standard delivery takes 3-6 business days. Express delivery takes 1-2 business days."),
        ("What is your return policy?", "You can request a return within 7 days of delivery from the Orders page."),
        ("Which payment methods do you accept?", "Cash on Delivery and online payments through Razorpay (UPI, cards, netbanking)."),
        ("How do I track my order?", "Open Orders in your account and choose Track to see live shipping updates."),
        ("Can I cancel my order?", "Yes, until it has shipped. Paid orders are refunded to the original payment method."),
        ("How do I become a seller?", "Register as a seller from the Sell page. Our team verifies new sellers within 2 business days."),
    ]])

    # ---- orders ----
    reviewed = set()
    texts = [(5, "Excellent quality", "Exactly as described and arrived earlier than expected. Totally worth the price."),
             (5, "Love it", "Great build and very comfortable to use every day. Highly recommended."),
             (4, "Very good", "Good value for money. Packaging was neat and delivery was quick."),
             (4, "Solid purchase", "Works well and looks great. Minor delay in delivery but overall happy."),
             (3, "Decent", "Does the job. Quality is okay for the price, nothing extraordinary."),
             (5, "Perfect gift", "Bought this as a gift and it was a huge hit. Will buy again."),
             (2, "Not what I expected", "Colour was slightly different from the photos but support was helpful.")]
    in_stock = [v for p in products for v in p.variants if v.inventory.quantity > 15]
    for n in range(120):
        cust = random.choice(customers)
        age = random.randint(0, 90)
        created = now - timedelta(days=age, hours=random.randint(0, 23))
        chosen = random.sample(in_stock, random.randint(1, 3))
        qtys = [random.randint(1, 2) for _ in chosen]
        subtotal = round(sum(v.price * q for v, q in zip(chosen, qtys)), 2)
        delivery = random.choice(["standard", "standard", "express"])
        totals = calc_totals(subtotal, delivery, 0)
        method = random.choice(["cod", "razorpay", "razorpay"])
        r = random.random()
        if age > 12:
            status = "delivered" if r < 0.8 else "cancelled" if r < 0.92 else "returned"
        elif age > 5:
            status = random.choice(["shipped", "out_for_delivery", "delivered", "processing"])
        else:
            status = random.choice(["pending", "confirmed", "processing", "confirmed"])
        addr = cust.addresses[0].to_dict()
        addr.pop("id"), addr.pop("is_default")
        order = Order(order_number=new_order_number(), user_id=cust.id, status=status, subtotal=totals["subtotal"],
                      discount=0, tax=totals["tax"], shipping_cost=totals["shipping"], total=totals["total"],
                      delivery_option=delivery, shipping_address=json.dumps(addr), billing_address=json.dumps(addr),
                      payment_method=method, created_at=created)
        db.session.add(order)
        db.session.flush()
        for v, q in zip(chosen, qtys):
            db.session.add(OrderItem(order_id=order.id, product_id=v.product_id, variant_id=v.id, name=v.product.name,
                                     size=v.size, color=v.color, price=v.price, quantity=q))
            if status not in ("cancelled",):
                v.product.sold_count = (v.product.sold_count or 0) + q
                v.inventory.quantity = max(v.inventory.quantity - q, 0)
        paid = (method == "razorpay" and status not in ("pending",) and not (status == "cancelled" and random.random() < 0.5)) \
            or (method == "cod" and status in ("delivered", "returned"))
        pay = Payment(order_id=order.id, method=method, amount=order.total, status="paid" if paid else "pending",
                      provider_order_id=("order_seed_" + str(order.id)) if method == "razorpay" else None,
                      provider_payment_id=("pay_seed_" + str(order.id)) if (paid and method == "razorpay") else None,
                      created_at=created)
        db.session.add(pay)
        db.session.flush()
        order.payment_status = pay.status
        if paid:
            db.session.add(Transaction(payment_id=pay.id, kind="charge" if method == "razorpay" else "cod_collected",
                                       amount=order.total, status="success", reference=pay.provider_payment_id,
                                       created_at=created))
        if status == "cancelled":
            if paid:
                db.session.add(Refund(order_id=order.id, kind="cancellation", amount=order.total,
                                      reason="Cancelled by customer", status="processed", created_at=created))
                db.session.add(Transaction(payment_id=pay.id, kind="refund", amount=order.total, status="success",
                                           note="Refund processed", created_at=created))
                pay.status = order.payment_status = "refunded"
            else:
                pay.status = order.payment_status = "cancelled"
        if status == "returned":
            db.session.add(Refund(order_id=order.id, kind="return", amount=order.total, reason="Product did not fit expectations",
                                  status="processed", created_at=created))
            db.session.add(Transaction(payment_id=pay.id, kind="refund", amount=order.total, status="success",
                                       note="Refund processed", created_at=created))
            pay.status = order.payment_status = "refunded"
        if method == "razorpay" and status == "pending" and random.random() < 0.5:
            pay.status = order.payment_status = "failed"
        sh = Shipping(order_id=order.id, carrier="ShopSphere Express")
        flow = ["pending", "confirmed", "processing", "shipped", "out_for_delivery", "delivered"]
        steps = flow[:flow.index(status) + 1] if status in flow else (["pending", "cancelled"] if status == "cancelled" else flow + ["returned"])
        for s in steps:
            sh.add_event(s, "")
        if status in ("shipped", "out_for_delivery", "delivered", "returned"):
            sh.tracking_number = f"TRK{random.randint(10**9, 10**10 - 1)}"
        if status in ("delivered", "returned"):
            sh.delivered_at = created + timedelta(days=4)
        db.session.add(sh)
        if status == "delivered":
            for v in chosen:
                key = (cust.id, v.product_id)
                if key in reviewed or random.random() < 0.45:
                    continue
                reviewed.add(key)
                rating, title, body = random.choice(texts)
                db.session.add(Review(user_id=cust.id, product_id=v.product_id, rating=rating, title=title, body=body,
                                      verified_purchase=True, status="approved", created_at=created + timedelta(days=6)))
    db.session.flush()
    from app.routes.reviews import refresh_rating
    for p in products:
        refresh_rating(p)
    db.session.add(Review(user_id=customers[1].id, product_id=products[0].id, rating=1, title="Bad",
                          body="This is a scam, visit www.spam-site.example", status="pending"))
    db.session.add(Notification(user_id=customers[0].id, title="Welcome to ShopSphere!",
                                message="Use code WELCOME10 for 10% off your first order.", kind="promo"))
    t = SupportTicket(user_id=customers[0].id, name=customers[0].name, email=customers[0].email,
                      subject="Question about warranty")
    t.messages.append(TicketMessage(sender="customer", body="Does the warranty cover accidental damage?"))
    db.session.add(t)
    db.session.commit()
    print("  120 orders with payments, transactions, shipping and reviews")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="drop all tables first")
    args = ap.parse_args()
    app = create_app()
    with app.app_context():
        if args.reset:
            db.drop_all()
        db.create_all()
        if Product.query.first():
            print("Database already contains data. Use --reset to rebuild.")
            return
        print("Seeding database ...")
        build(app)
        print("Done.\n\nLogins:\n  Super admin : admin@shopsphere.com / Admin@123"
              "\n  Store admin : manager@shopsphere.com / Manager@123"
              "\n  Seller      : seller1@shopsphere.com / Seller@123  (verified)"
              "\n  Customer    : customer@shopsphere.com / Customer@123")


if __name__ == "__main__":
    main()
