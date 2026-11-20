# ShopSphere – Smart E-Commerce Platform

Full-stack e-commerce application: **Flask + SQLAlchemy + SQLite** backend (REST API, JWT auth, role-based access)
and a **React (Vite)** frontend. Customers, sellers, store admins and a super admin each get their own experience.

> **Honest status:** this project was generated in an environment with no internet access, so the Python
> dependencies and npm packages could not be installed there. Every Python and JSX file was syntax-checked
> (`py_compile` / esbuild) and the image generator was executed, but **the pytest suite, vitest suite, API and UI
> have not been run yet.** Follow the steps below, run the tests yourself (step 6) and expect to fix a few small
> issues on first run. Nothing here claims "all tests pass".

## What is included

| Area | Features |
|---|---|
| Customer | Home (hero, featured, trending, best sellers, new arrivals, offers, newsletter), catalog with category/brand/price/rating/stock filters, sorting, pagination, multi-word search with suggestions, product page (gallery, variants, specs, reviews, related), persistent cart, coupons, tax & shipping, wishlist, checkout (addresses, delivery option, COD / Razorpay sandbox), orders, tracking timeline, cancellation, refund requests, PDF invoice, profile & avatar, saved addresses, notifications, support tickets, FAQ |
| Admin / Seller | Dashboard with charts, products (CRUD, image upload, variants), categories & brands, orders & status workflow, refunds, inventory + stock history + low-stock alerts, customers, coupons, sales analytics (daily/monthly/annual, CSV export), sellers + verification, review moderation, support tickets, settings, audit log, staff accounts |
| Added in v1.1 | **Guest cart** (kept in the browser, priced by the server, merged into your account at login), **recently viewed** rows, **Buy again**, **promo opt-out** setting, **Razorpay webhook**, **promotional notifications & newsletter manager** (admin), **seller orders view**, admin **invoice download** |
| Backend | 26 relational tables with FKs, indexes and CHECK/UNIQUE constraints, JWT access + refresh tokens with logout revocation, password hashing, rate limiting, secure image uploads (Pillow re-encode), HMAC payment verification, audit logging, recommendations (purchase + browsing history), e-mail (SMTP or logged) |

## Project structure

```
shopsphere/
├── backend/
│   ├── app/            (config, models, services, utils, routes/*)
│   ├── tests/          (pytest suite)
│   ├── seed.py         (120+ demo products, users, orders …)
│   ├── run.py
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/            (pages, admin, components, context, api, tests)
    ├── package.json
    └── vite.config.js
```

---

## Run it in VS Code, step by step

### 0. Prerequisites
* [Python 3.11+](https://www.python.org/downloads/) (tick "Add Python to PATH" on Windows)
* [Node.js 18+ (LTS)](https://nodejs.org/)
* [VS Code](https://code.visualstudio.com/) with the **Python** extension

### 1. Open the project
Unzip `shopsphere.zip`, then in VS Code: **File → Open Folder… → `shopsphere`**.
Open a terminal: **Terminal → New Terminal**. You will use **two terminals** (backend and frontend).

### 2. Backend setup (Terminal 1)
```bash
cd backend

# create + activate a virtual environment
python -m venv .venv
# Windows (PowerShell):   .venv\Scripts\Activate.ps1
#   (if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned)
# Windows (cmd):          .venv\Scripts\activate.bat
# macOS / Linux:          source .venv/bin/activate

pip install -r requirements.txt

# environment file
copy .env.example .env      # Windows
cp .env.example .env        # macOS / Linux
```
Press **Ctrl+Shift+P → "Python: Select Interpreter" →** choose the `.venv` one.

Edit `.env` and set `SECRET_KEY` and `JWT_SECRET_KEY` to long random strings
(generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`).
Leave the Razorpay keys empty to use the built-in **local sandbox**.

### 3. Create the database + sample data
> Upgrading from v1.0? The schema changed (new `promotions` table and `users.promo_opt_in`), so run `python seed.py --reset` again.
```bash
python seed.py --reset
```
This creates `backend/data/shopsphere.db`, 12 categories, 108 products (each with 2 locally generated
images and 1–4 variants), 10 customers, sellers, coupons, FAQs and 120 sample orders with payments,
transactions, shipping events and reviews. Takes ~20–40 seconds.

**Demo logins**

| Role | Email | Password |
|---|---|---|
| Super admin | admin@shopsphere.com | Admin@123 |
| Store admin | manager@shopsphere.com | Manager@123 |
| Seller (verified) | seller1@shopsphere.com | Seller@123 |
| Seller (pending) | seller2@shopsphere.com | Seller@123 |
| Customer | customer@shopsphere.com | Customer@123 |

Demo coupons: `WELCOME10`, `FLAT200`, `SAVE25` (`OLD5` is expired on purpose).

### 4. Start the backend
```bash
python run.py
```
API runs at http://127.0.0.1:5000 – check http://127.0.0.1:5000/api/health → `{"status":"ok"}`.

### 5. Frontend (Terminal 2)
```bash
cd frontend
npm install
npm run dev
```
Open **http://localhost:5173**. Vite proxies `/api` and `/uploads` to Flask, so no CORS setup is needed in development.

### 6. Run the tests
```bash
# backend (Terminal 1, venv active, inside /backend)
pytest -v

# frontend (Terminal 2, inside /frontend)
npm test
```
Please report/fix whatever fails – the suites (including the new `tests/test_extras.py` for webhook, guest cart, promotions, recommendations and seller orders) were written but not executed before delivery.

### 7. Try the full shopping workflow
1. Log in as the customer → open a product → choose size/colour → **Add to cart**.
2. Cart → apply `WELCOME10` → **Proceed to checkout**.
3. Pick the saved address, delivery option, and **Cash on Delivery** *or* **Pay online**.
   In sandbox mode a dialog lets you simulate a successful or failed payment (signature is verified server-side exactly like real Razorpay).
4. Open **Orders** → track, download the invoice PDF, cancel (stock is restored; paid orders get a refund record).
5. Log out and add items as a guest – they survive login and merge into your account. Admin → **Promotions** sends a notification to every opted-in customer.
6. Log in as the store admin → **Admin → Orders** → move the order through *confirmed → processing → shipped → delivered*; the customer gets notifications and COD payment is marked paid on delivery.

---

## Payments (Razorpay)
* **Sandbox / local mock (default):** leave the keys empty. A mock gateway issues `order_mock_…` ids; "Simulate success" produces a correctly signed payment that goes through the same HMAC check as real ones. It is disabled automatically when real keys are configured.
* **Razorpay test mode:** create test keys in the Razorpay dashboard and set `RAZORPAY_MODE=sandbox`, `RAZORPAY_TEST_KEY_ID`, `RAZORPAY_TEST_KEY_SECRET`. The frontend opens Razorpay's hosted checkout; the backend verifies the signature at `POST /api/payments/verify`.
* **Live:** set `RAZORPAY_MODE=live` and the `RAZORPAY_LIVE_*` variables. Test and live credentials are separate variables and never mixed.
* Card data never touches this app. Marking a refund "processed" only records it – issue the real transfer in the Razorpay dashboard/API. 

### Razorpay webhook (handles customers who close the tab after paying)
`POST /api/payments/webhook` verifies the `X-Razorpay-Signature` HMAC of the raw body, checks the amount matches the order, and is idempotent. In the Razorpay dashboard → Webhooks add `https://YOUR-BACKEND/api/payments/webhook`, enable `payment.captured`, `order.paid` and `payment.failed`, and put the secret in `RAZORPAY_TEST_WEBHOOK_SECRET` (or `..._LIVE_...`). The URL must be public (use a tunnel such as ngrok when testing locally). In local mock mode the webhook accepts bodies signed with the mock secret, which the tests use.

## Database changes with Flask-Migrate
`run.py` / `seed.py` create tables with `db.create_all()`. To manage schema changes with Alembic instead:
```bash
set FLASK_APP=run.py            # Windows (cmd);  PowerShell: $env:FLASK_APP="run.py";  macOS/Linux: export FLASK_APP=run.py
flask db init                   # once (creates /migrations)
flask db migrate -m "initial"
flask db upgrade
```
(Delete `backend/data/shopsphere.db` first if you started with `create_all`.)

## Deployment

**Backend (Flask)** – any host that runs Python and has a *persistent disk* (Render, Railway, Fly.io, a VPS, PythonAnywhere):
1. Set environment variables: `APP_ENV=production`, strong `SECRET_KEY` + `JWT_SECRET_KEY` (the app refuses to start in production with defaults), `DATA_DIR=/path/to/persistent/disk`, `CORS_ORIGINS=https://your-frontend-domain`, `FRONTEND_URL=https://your-frontend-domain`, `EXPOSE_RESET_TOKEN=false`, SMTP + Razorpay settings.
2. Start command: `python run.py` (uses Waitress in production) or `waitress-serve --port=$PORT run:app`.
3. Run `python seed.py` once if you want demo data, or create real catalog data via the admin panel. **Change/delete the demo accounts.**
4. SQLite lives at `$DATA_DIR/shopsphere.db`, uploads at `$DATA_DIR/uploads` – both must be on the persistent disk and backed up. SQLite suits a single server; use one worker process.

**Frontend (React)** – Netlify / Vercel / any static host:
1. `cd frontend && npm run build` (set `VITE_API_ORIGIN=https://your-backend-domain` first).
2. Publish `frontend/dist`. Add an SPA rewrite (`/* → /index.html`).

## Security notes
Password hashing (Werkzeug), JWT with refresh + revocation on logout, role checks on every back-office route (re-read from the DB, so deactivation is immediate), input validation, SQL-injection safe ORM queries, upload re-encoding with Pillow + extension allow-list, in-memory rate limiting (per process – use Redis-backed limiting if you scale out), HMAC-verified payments, server-side coupon validation, audit log, security headers. CSRF: the API authenticates with an `Authorization: Bearer` header (not cookies), so classic CSRF doesn't apply; if you move tokens to cookies, add CSRF protection. Review reset-token e-mailing, HTTPS and cookie/token storage before real production use.

## Known limitations / ideas
* Product images are generated illustrative cards (not photographs). Upload real photos from Admin → Products.
* E-mails are sent synchronously and only logged when `MAIL_SERVER` is empty.
* Money is stored as floats rounded to 2 decimals (fine for a project; use integer paise/`Numeric` for accounting-grade precision).
* "Frontend component tests" cover shared components and route protection, not every page.
* No Alembic `migrations/` folder is shipped (it must be generated by `flask db init` on your machine).
* Promotion e-mails are sent synchronously (capped at 500 per send); use a task queue for large lists.
