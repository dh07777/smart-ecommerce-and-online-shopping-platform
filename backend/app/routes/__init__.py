def register_blueprints(app):
    from . import auth, catalog, cart, orders, reviews, support, admin
    for module in (auth, catalog, cart, orders, reviews, support, admin):
        app.register_blueprint(module.bp)
