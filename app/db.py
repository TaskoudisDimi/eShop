# app/db.py
import os
from flask import current_app, g, jsonify, render_template, request, flash, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError
import logging
from contextlib import contextmanager
from functools import wraps

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db = SQLAlchemy()


def db_error_msg(e: SQLAlchemyError) -> str:
    msg = "Database error. Please try again later."
    low = str(e).lower()
    if "connection refused" in low:
        msg = "Cannot reach the database server – check your network."
    elif "database does not exist" in low:
        msg = "The database does not exist. Contact the administrator."
    elif "deadlock" in low:
        msg = "A temporary deadlock occurred – please retry."
    logger.error(f"DB error: {msg} | Original: {e}")
    return msg


def init_db(app):
    with app.app_context():
        try:
            db.init_app(app)
            logger.info("Database initialized successfully.")
            db.create_all()
            logger.info("Database tables created.")
        except SQLAlchemyError as e:
            logger.error(f"Failed to initialize database: {str(e)}")
            raise


def get_db():
    if 'db' not in g:
        g.db = db
    return g.db


@contextmanager
def db_session():
    session = get_db().session
    try:
        yield session
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        raise
    finally:
        session.close()


def register_event_listeners(app):
    with app.app_context():
        @event.listens_for(db.engine, "connect")
        def on_connect(dbapi_connection, connection_record):
            logger.info("Connected to DB")

        @event.listens_for(db.engine, "checkout")
        def on_checkout(dbapi_connection, connection_record, connection_proxy):
            try:
                cur = dbapi_connection.cursor()
                cur.execute("SELECT 1")
                cur.close()
            except dbapi_connection.OperationalError as exc:
                logger.error(f"Checkout failed: {exc}")
                raise SQLAlchemyError("Unhealthy connection") from exc



def db_transaction(f):
    """
    Wraps a view function:
    - Commits on success
    - Rolls back + flashes/returns JSON on SQLAlchemyError
    - Works for both HTML and JSON API routes
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            result = f(*args, **kwargs)
            db.session.commit()
            return result
        except SQLAlchemyError as exc:
            db.session.rollback()
            msg = db_error_msg(exc)
            logger.error(f"DB error in {f.__name__}: {exc}", exc_info=True)

            # Detect JSON API
            is_json = (
                request.path.startswith("/api/") or
                request.headers.get("Accept") == "application/json" or
                request.headers.get("Content-Type") == "application/json"
            )

            if is_json:
                return jsonify({"error": "database_error", "message": msg}), 503
            else:
                flash(msg, "danger")
                return redirect(url_for("shop.dashboard" if current_user.is_authenticated else "shop.index"))
    return decorated



def init_app(app):
    init_db(app)
    register_event_listeners(app)
    app.teardown_appcontext(close_db)

    @app.errorhandler(SQLAlchemyError)
    def handle_sqlalchemy_error(error):
        msg = db_error_msg(error)
        if request.path.startswith("/api/") or request.headers.get("Accept") == "application/json":
            return jsonify({"error": "database_error", "message": msg}), 503
        flash(msg, "danger")
        return redirect(url_for("auth.index"))


def close_db(e=None):
    db_sess = g.pop('db', None)
    if db_sess is not None:
        db_sess.close()
        logger.debug("DB session closed on teardown")