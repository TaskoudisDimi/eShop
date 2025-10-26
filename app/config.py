from flask import current_app
from .models import Config as ConfigModel

class AppConfig:

    SQLALCHEMY_DATABASE_URI = "postgresql://postgres:9963@localhost/eshop_db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = "your_default_dev_secret"

    @staticmethod
    def get(key, default=None):
        with current_app.app_context():
            config_entry = ConfigModel.query.filter_by(key=key).first()
            return config_entry.value if config_entry else default

    @staticmethod
    def init_app(app):

        app.config['SECRET_KEY'] = AppConfig.get("SECRET_KEY", app.config['SECRET_KEY'])
        app.config['SQLALCHEMY_DATABASE_URI'] = AppConfig.get(
            "DATABASE_URL", app.config['SQLALCHEMY_DATABASE_URI']
        )
