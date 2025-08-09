# config.py
import os

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "your_default_dev_secret")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    AVAILABLE_THEMES = ["MyTemplate", "AnotherTemplate"]  # Add more themes here