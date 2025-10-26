from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from .models import User, Order
from . import db
from werkzeug.security import generate_password_hash, check_password_hash
import logging
import os
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.auth.transport import requests
import pathlib

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

auth = Blueprint("auth", __name__)

# ---------------------------------------------------
# Google OAuth Config
# ---------------------------------------------------
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = "http://localhost:5000/google/callback"
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]
CLIENT_SECRETS_FILE = os.path.join(pathlib.Path(__file__).parent, "client_secret.json")
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# ---------------------------------------------------
# Routes
# ---------------------------------------------------
@auth.route("/")
@auth.route("/index")
def index():
    return render_template("index.html")

@auth.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email, password = request.form.get("email"), request.form.get("password")
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash("Login successful!", "success")
            return redirect(url_for("auth.dashboard"))
        flash("Invalid email or password.", "error")
    return render_template("login.html")

@auth.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email, password, name = request.form.get("email"), request.form.get("password"), request.form.get("name")
        if not email or not password:
            flash("Email and password are required.", "error")
            return redirect(url_for("auth.register"))
        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "error")
            return redirect(url_for("auth.register"))
        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "error")
            return redirect(url_for("auth.register"))

        new_user = User(email=email, name=name, theme="MyTemplate")
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("auth.login"))
    return render_template("register.html")

@auth.route("/dashboard")
@login_required
def dashboard():
    orders_count = Order.query.filter_by(user_id=current_user.id).count()
    return render_template("dashboard.html", orders_count=orders_count)

@auth.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.index"))

@auth.route("/set_theme", methods=["POST"])
@login_required
def set_theme():
    theme = request.form.get("theme")
    if theme in ["light", "dark", "MyTemplate"]:
        current_user.theme = theme
        db.session.commit()
        flash("Theme updated!", "success")
    else:
        flash("Invalid theme selected.", "error")
    return redirect(request.referrer or url_for("auth.dashboard"))

# ---------------------------------------------------
# Google OAuth
# ---------------------------------------------------
@auth.route("/google/login")
def google_login():
    flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES, redirect_uri=GOOGLE_REDIRECT_URI)
    authorization_url, state = flow.authorization_url(access_type="offline", include_granted_scopes="true")
    session["state"] = state
    return redirect(authorization_url)

@auth.route("/google/callback")
def google_callback():
    if request.args.get("state") != session.get("state"):
        flash("Invalid state parameter.", "error")
        return redirect(url_for("auth.login"))
    flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES, redirect_uri=GOOGLE_REDIRECT_URI)
    flow.fetch_token(authorization_response=request.url)

    credentials = flow.credentials
    idinfo = id_token.verify_oauth2_token(credentials.id_token, requests.Request(), GOOGLE_CLIENT_ID)
    google_id, email, name = idinfo["sub"], idinfo["email"], idinfo.get("name", "")

    user = User.query.filter_by(google_id=google_id).first()
    if not user:
        user = User.query.filter_by(email=email).first()
        if user:
            user.google_id = google_id
        else:
            user = User(email=email, name=name, google_id=google_id, theme="MyTemplate")
            db.session.add(user)
        db.session.commit()

    login_user(user)
    flash("Google login successful!", "success")
    return redirect(url_for("auth.dashboard"))
