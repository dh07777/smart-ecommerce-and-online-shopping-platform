import os
from app import create_app
from app.extensions import db

app = create_app()

with app.app_context():
    db.create_all()  # no-op if tables exist (use Flask-Migrate for schema changes)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    if os.getenv("APP_ENV") == "production":
        from waitress import serve
        serve(app, host="0.0.0.0", port=port)
    else:
        app.run(host="127.0.0.1", port=port, debug=True)
