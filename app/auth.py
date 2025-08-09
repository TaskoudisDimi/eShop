from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from .models import User, Order  # Import only defined models
from . import db
from werkzeug.security import generate_password_hash, check_password_hash
import logging
import os
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.auth.transport import requests
import pathlib

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

auth = Blueprint("auth", __name__)

# Google OAuth configuration
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = "http://localhost:5000/google/callback"  # Must match Google Cloud Console
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]
# Path to client_secret.json (optional, if not using environment variables)
CLIENT_SECRETS_FILE = os.path.join(pathlib.Path(__file__).parent, "client_secret.json")
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # Allow HTTP for local development
# Ensure secret key is set for sessions
auth.secret_key = os.environ.get("FLASK_SECRET_KEY", "thisIsSecret")

@auth.route("/")
@auth.route("/index")
def index():
    return render_template("index.html")

@auth.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        logger.debug(f"Attempting login for email: {email}")

        # Find user by email
        user = User.query.filter_by(email=email).first()

        # Validate credentials
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash("Login successful!", "success")
            logger.info(f"User {email} logged in successfully")
            return redirect(url_for("auth.dashboard"))
        else:
            flash("Invalid email or password.", "error")
            logger.warning(f"Failed login attempt for email: {email}")
            return redirect(url_for("auth.login"))

    # Handle GET request (render login page)
    return render_template("login.html")

@auth.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        name = request.form.get("name")  # Optional, as per User model

        # Validate input
        if not email or not password:
            flash("Email and password are required.", "error")
            logger.warning("Registration failed: Missing email or password")
            return redirect(url_for("auth.register"))

        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "error")
            logger.warning("Registration failed: Password too short")
            return redirect(url_for("auth.register"))

        # Check if email or google_id is already registered
        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "error")
            logger.warning(f"Registration failed: Email {email} already exists")
            return redirect(url_for("auth.register"))

        # Create new user
        try:
            new_user = User(email=email, name=name, theme="MyTemplate")
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash("Registration successful! Please log in.", "success")
            logger.info(f"User {email} registered successfully")
            return redirect(url_for("auth.login"))
        except Exception as e:
            db.session.rollback()
            flash("An error occurred during registration. Please try again.", "error")
            logger.error(f"Registration error: {e}")
            return redirect(url_for("auth.register"))

    # Handle GET request (render register page)
    return render_template("register.html")

@auth.route("/dashboard")
@login_required
def dashboard():
    orders_count = Order.query.filter_by(user_id=current_user.id).count()
    logger.debug(f"Dashboard stats for {current_user.email}: Orders={orders_count}")
    return render_template("dashboard.html", orders_count=orders_count)

@auth.route("/logout")
@login_required
def logout():
    logger.info(f"User {current_user.email} logged out")
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.index"))

@auth.route("/set_theme", methods=["POST"])
@login_required
def set_theme():
    theme = request.form.get("theme")
    if theme in ["light", "dark", "MyTemplate"]:  # Validate theme
        current_user.theme = theme
        db.session.commit()
        flash("Theme updated!", "success")
        logger.info(f"User {current_user.email} updated theme to {theme}")
    else:
        flash("Invalid theme selected.", "error")
        logger.warning(f"Invalid theme {theme} selected by {current_user.email}")
    return redirect(request.referrer or url_for("auth.dashboard"))

# Google OAuth routes
@auth.route("/google/login")
def google_login():
    # Initialize the OAuth flow
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI,
    )
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
    )
    # Store state in session for CSRF protection
    session["state"] = state
    return redirect(authorization_url)

@auth.route("/google/callback")
def google_callback():
    # Verify state to prevent CSRF
    if request.args.get("state") != session.get("state"):
        flash("Invalid state parameter.", "error")
        logger.warning("Google OAuth failed: Invalid state parameter")
        return redirect(url_for("auth.login"))

    # Initialize the OAuth flow
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI,
    )

    # Fetch token
    try:
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials

        # Verify the ID token
        idinfo = id_token.verify_oauth2_token(
            credentials.id_token,
            requests.Request(),
            GOOGLE_CLIENT_ID,
        )

        # Get user info
        google_id = idinfo["sub"]
        email = idinfo["email"]
        name = idinfo.get("name", "")

        # Check if user exists
        user = User.query.filter_by(google_id=google_id).first()
        if not user:
            # Check if email is already registered
            user = User.query.filter_by(email=email).first()
            if user:
                # Link Google account to existing user
                user.google_id = google_id
                db.session.commit()
            else:
                # Create new user
                user = User(email=email, name=name, google_id=google_id, theme="MyTemplate")
                db.session.add(user)
                db.session.commit()

        login_user(user)
        flash("Google login successful!", "success")
        logger.info(f"User {email} logged in with Google")
        return redirect(url_for("auth.dashboard"))

    except Exception as e:
        flash("Google login failed. Please try again.", "error")
        logger.error(f"Google OAuth error: {e}")
        return redirect(url_for("auth.login"))
