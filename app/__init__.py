# app/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from dotenv import load_dotenv
import os
from urllib.parse import urlparse

load_dotenv()


db = SQLAlchemy()
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
    print(f"[create_app] Flask root_path: {app.root_path}")


    app.config.from_object("app.config.AppConfig")


    db.init_app(app)
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



    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    from .shop import shop as shop_blueprint
    app.register_blueprint(shop_blueprint)

    from .controllers.payment.viva import payment as payment_blueprint
    app.register_blueprint(payment_blueprint, url_prefix="/payment")

    return app
