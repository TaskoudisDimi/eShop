# app/config.py
from flask import current_app
from .models import Config, Setting
from . import db   # <-- make sure db is imported


class AppConfig:
    # Hard-coded fall-backs (used only when nothing is in DB)
    SQLALCHEMY_DATABASE_URI = "postgresql://postgres:9963@localhost/eshop_db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = "change-me-in-production"

    @staticmethod
    def get(key, user_id=None, default=None):
        """
        1. user-specific setting (user_id is not None)
        2. global setting (user_id IS NULL)
        3. old Config table
        4. default value supplied by caller
        """
        with current_app.app_context():
            if user_id is not None:
                setting = Setting.query.filter_by(user_id=user_id, key=key).first()
                if setting:
                    return setting.value

            setting = Setting.query.filter_by(user_id=None, key=key).first()
            if setting:
                return setting.value

            cfg = Config.query.filter_by(key=key).first()
            if cfg:
                return cfg.value

            return default

    @staticmethod
    def init_app(app):
        """
        Called once when the Flask app is created.
        """

        app.config['SECRET_KEY'] = AppConfig.get(
            "SECRET_KEY", default=app.config.get('SECRET_KEY', AppConfig.SECRET_KEY)
        )
        app.config['SQLALCHEMY_DATABASE_URI'] = AppConfig.get(
            "DATABASE_URL", default=app.config.get('SQLALCHEMY_DATABASE_URI', AppConfig.SQLALCHEMY_DATABASE_URI)
        )

        with app.app_context():
            defaults = [
                ("default_currency", "EUR", "Default shop currency"),
                ("tax_rate", "0.20", "Default tax rate (20 %)"),
                ("max_cart_items", "10", "Maximum items in a cart"),
                ("payment_gateway_active", "true", "Enable Viva payments"),
                ("payment_timeout", "300", "Payment timeout (seconds)"),
                ("default_shipping_cost", "5.00", "Flat shipping fee"),
                ("free_shipping_threshold", "50.00", "Free shipping above this amount"),
            ]

            for k, v, d in defaults:
                if not Setting.query.filter_by(key=k, user_id=None).first():
                    db.session.add(Setting(key=k, value=v, description=d, user_id=None))
            db.session.commit()