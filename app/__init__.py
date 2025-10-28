# app/__init__.py
from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate
from dotenv import load_dotenv
import os
from urllib.parse import urlparse
from .db import db, init_app as db_init_app

load_dotenv()

login_manager = LoginManager()
login_manager.login_view = "auth.login"
migrate = Migrate()

@login_manager.user_loader
def load_user(user_id):
    from .models import User  
    return User.query.get(int(user_id))

def create_app():
    from .config import AppConfig

    app = Flask(__name__, template_folder="templates")
    app.config.from_object("app.config.AppConfig")

    db_init_app(app) 
    login_manager.init_app(app)
    migrate.init_app(app, db)

    from . import models
    with app.app_context():
        AppConfig.init_app(app)

        base_url = AppConfig.get("BASE_URL")
        if base_url:
            parsed = urlparse(base_url)
            app.config["PREFERRED_URL_SCHEME"] = parsed.scheme
            app.config["SERVER_NAME"] = parsed.netloc

    from .controllers.shop_routes import shop as shop_blueprint
    app.register_blueprint(shop_blueprint)

    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    from .controllers.payment.viva import payment as payment_blueprint
    app.register_blueprint(payment_blueprint, url_prefix="/payment")

    return app