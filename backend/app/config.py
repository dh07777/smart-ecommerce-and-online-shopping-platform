import os
from datetime import timedelta
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


DATA_DIR = os.path.abspath(os.getenv("DATA_DIR") or os.path.join(BASE_DIR, "data"))
if not os.path.isabs(os.getenv("DATA_DIR", "/")):
    DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, os.getenv("DATA_DIR")))
os.makedirs(DATA_DIR, exist_ok=True)

_MODE = os.getenv("RAZORPAY_MODE", "sandbox").lower()
if _MODE == "live":
    _RZP_KEY, _RZP_SECRET = os.getenv("RAZORPAY_LIVE_KEY_ID", ""), os.getenv("RAZORPAY_LIVE_KEY_SECRET", "")
    _RZP_WEBHOOK = os.getenv("RAZORPAY_LIVE_WEBHOOK_SECRET", "")
else:
    _RZP_KEY, _RZP_SECRET = os.getenv("RAZORPAY_TEST_KEY_ID", ""), os.getenv("RAZORPAY_TEST_KEY_SECRET", "")
    _RZP_WEBHOOK = os.getenv("RAZORPAY_TEST_WEBHOOK_SECRET", "")

DEFAULT_SECRET = "dev-secret-change-me"
DEFAULT_JWT = "dev-jwt-secret-change-me-dev-jwt-secret-change-me"


class Config:
    ENV_NAME = os.getenv("APP_ENV", "development")
    SECRET_KEY = os.getenv("SECRET_KEY", DEFAULT_SECRET)
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", DEFAULT_JWT)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=2)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=14)
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or "sqlite:///" + os.path.join(DATA_DIR, "shopsphere.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DATA_DIR = DATA_DIR
    UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
    MAX_CONTENT_LENGTH = 6 * 1024 * 1024
    CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
    EXPOSE_RESET_TOKEN = _bool("EXPOSE_RESET_TOKEN", False)
    RATELIMIT_ENABLED = True
    RAZORPAY_MODE = _MODE
    RAZORPAY_KEY_ID = _RZP_KEY
    RAZORPAY_KEY_SECRET = _RZP_SECRET
    RAZORPAY_WEBHOOK_SECRET = _RZP_WEBHOOK
    MOCK_PAYMENTS = (_MODE != "live") and not (_RZP_KEY and _RZP_SECRET)
    MOCK_RAZORPAY_SECRET = "mock_sandbox_secret"
    MAIL_SERVER = os.getenv("MAIL_SERVER", "")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = _bool("MAIL_USE_TLS", True)
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_SENDER = os.getenv("MAIL_SENDER", "no-reply@shopsphere.local")


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    RATELIMIT_ENABLED = False
    MOCK_PAYMENTS = True
    RAZORPAY_MODE = "sandbox"
    RAZORPAY_KEY_ID = ""
    EXPOSE_RESET_TOKEN = True
    UPLOAD_DIR = os.path.join(DATA_DIR, "test_uploads")
