# app/controllers/payment/viva.py
from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, jsonify, session, current_app
)
from flask_login import login_required, current_user
from app import db                    
from app.models import Order, OrderItem, Product
from app.db import db_error_msg      
from app.config import AppConfig
from sqlalchemy.exc import SQLAlchemyError
import os
import requests
import logging
import base64
from app.db import db_transaction

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

payment = Blueprint("payment", __name__)


def _commit_or_rollback():
    """Commit the current session; on error → rollback + flash + return None."""
    try:
        db.session.commit()
        return True
    except SQLAlchemyError as exc:
        db.session.rollback()
        msg = db_error_msg(exc)
        if request.path.startswith("/api/") or request.headers.get("Accept") == "application/json":
            return jsonify({"error": "database_error", "message": msg}), 503
        flash(msg, "danger")
        return None


@payment.route("/checkout", methods=["GET", "POST"])
@login_required
@db_transaction
def checkout():
    client_id = AppConfig.get("VIVA_CLIENT_ID") or os.getenv("VIVA_CLIENT_ID")
    client_secret = AppConfig.get("VIVA_CLIENT_SECRET") or os.getenv("VIVA_CLIENT_SECRET")
    source_code = AppConfig.get("VIVA_SOURCE_CODE") or os.getenv("VIVA_SOURCE_CODE", "eShop")

    if not client_id or not client_secret:
        flash("Payment credentials are not configured. Please contact admin.", "error")
        return redirect(url_for("shop.view_cart"))

    # ---- 2. Cart validation ----------------------------------------------------
    if "cart" not in session or not session["cart"]:
        flash("Your cart is empty.", "error")
        return redirect(url_for("shop.view_cart"))
    cart_items = []
    total = 0.0
    for item in session["cart"]:
        product = Product.query.get(item["product_id"])
        if not product:
            flash("One of the products no longer exists.", "error")
            return redirect(url_for("shop.view_cart"))
        cart_items.append({
            "product": product,
            "quantity": item["quantity"],
            "subtotal": product.price * item["quantity"]
        })
        total += product.price * item["quantity"]
    delivery_info = session.get("delivery_info", {})
    required = ["address", "zipcode", "region", "phone"]
    if not all(delivery_info.get(k) for k in required):
        flash("Please provide delivery information first.", "error")
        return redirect(url_for("shop.delivery_info"))

    if request.method == "GET":
        return render_template("checkout.html", cart_items=cart_items, total=total)

    address = request.form.get("address", delivery_info.get("address"))
    phone   = request.form.get("phone",   delivery_info.get("phone"))
    floor   = request.form.get("floor",   delivery_info.get("floor"))
    zipcode = request.form.get("zipcode", delivery_info.get("zipcode"))
    region  = request.form.get("region",  delivery_info.get("region"))
    payment_method = request.form.get("payment_method", "card")

    if not all([address, phone, zipcode, region]):
        flash("All required fields (Address, Phone, Zipcode, Region) must be filled.", "error")
        return render_template("checkout.html", cart_items=cart_items, total=total)
    order = Order(
        user_id=current_user.id,
        total_amount=0,
        status="Pending",
        payment_status="Pending",
        shipping_address=address,
        payment_method=payment_method,
        shipping_phone=phone,
        shipping_floor=floor,
        shipping_zipcode=zipcode,
        shipping_region=region
    )
    db.session.add(order)
    db.session.flush()

    total_amount = 0.0
    for item in session["cart"]:
        product = Product.query.get(item["product_id"])
        if not product or product.stock < item["quantity"]:
            flash(f"Out of stock: {product.name}", "error")
            raise SQLAlchemyError("Stock error")  # will trigger rollback

        order_item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=item["quantity"],
            unit_price=product.price
        )
        total_amount += product.price * item["quantity"]
        product.stock -= item["quantity"]
        db.session.add(order_item)

    order.total_amount = total_amount
    session["order_id"] = order.id
    session.modified = True

    try:
        token_url = "https://demo-accounts.vivapayments.com/connect/token"
        auth_str = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        token_resp = requests.post(
            token_url,
            data={"grant_type": "client_credentials"},
            headers={"Authorization": f"Basic {auth_str}", "Content-Type": "application/x-www-form-urlencoded"}
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        checkout_url = "https://demo-api.vivapayments.com/checkout/v2/orders"
        payload = {
            "amount": int(total_amount * 100),
            "customerTrns": f"Order {order.id} for {current_user.email}",
            "customer": {
                "email": current_user.email,
                "fullName": current_user.name or "Customer",
                "phone": phone,
                "countryCode": "GR"
            },
            "paymentTimeout": 300,
            "webhookUrl": url_for("payment.payment_viva_callback", order_id=order.id, _external=True),
            "merchantTrns": f"Order-{order.id}",
            "sourceCode": source_code,
            "requestLang": "el-GR",
            "successUrl": url_for("payment.payment_success", order_id=order.id, _external=True),
            "failureUrl": url_for("payment.payment_cancel", order_id=order.id, _external=True)
        }

        checkout_resp = requests.post(
            checkout_url,
            json=payload,
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        )
        checkout_resp.raise_for_status()
        order_code = checkout_resp.json()["orderCode"]
        session["viva_order_code"] = order_code
        session.modified = True

        
        payment_method_id = None
        if payment_method == "card":
            payment_method_id = os.getenv("VIVA_CARD_METHOD_ID")
        elif payment_method == "paypal":
            payment_method_id = os.getenv("VIVA_PAYPAL_METHOD_ID")

        redirect_url = f"https://demo.vivapayments.com/web/checkout?ref={order_code}"
        if payment_method_id:
            redirect_url += f"&paymentMethodId={payment_method_id}"

        return redirect(redirect_url)

    except requests.exceptions.HTTPError as e:
        logger.error(f"Viva API error: {e.response.status_code} – {e.response.text}")
        flash(f"Payment gateway error: {e.response.text}", "danger")
        db.session.rollback()
        return render_template("checkout.html", cart_items=cart_items, total=total)
    except Exception as e:
        logger.exception("Unexpected error during Viva checkout")
        flash(f"Unexpected error: {str(e)}", "danger")
        db.session.rollback()
        return render_template("checkout.html", cart_items=cart_items, total=total)


@payment.route("/viva/callback/<int:order_id>", methods=["POST"])
def payment_viva_callback(order_id):
    webhook_key = request.headers.get("Key")
    if webhook_key != os.getenv("VIVA_WEBHOOK_KEY"):
        logger.warning(f"Invalid webhook key for order {order_id}")
        return jsonify({"error": "Invalid webhook key"}), 403

    data = request.get_json(silent=True) or {}
    order = Order.query.get_or_404(order_id)
    if not order:
        logger.error(f"Webhook received for non-existent order {order_id}")
        return jsonify({"error": "Order not found"}), 404

    if data.get("statusId") == "F":
        order.payment_status = "Paid"
        order.status = "Completed"
        session.pop("cart", None)
        session.pop("delivery_info", None)
        return jsonify({"status": "success"}), 200
    else:
        order.payment_status = "Failed"
        order.status = "Cancelled"
        return jsonify({"status": "failed"}), 400


@payment.route("/success")
@login_required
@db_transaction
def payment_success():
    order_id = session.get("order_id")
    if not order_id:
        flash("Order ID missing.", "warning")
        return redirect(url_for("shop.orders"))

    order = Order.query.get(order_id)
    if not order or order.user_id != current_user.id:
        flash("Unauthorized.", "danger")
        return redirect(url_for("shop.orders"))

    order.payment_status = "Paid"
    order.status = "Completed"
    flash("Payment confirmed!", "success")
    session.pop("cart", None)
    session.pop("delivery_info", None)
    return render_template("payment_success.html", order=order)


@payment.route("/cancel")
@login_required
@db_transaction
def payment_cancel():
    order_id = session.get("order_id")
    if order_id:
        order = Order.query.get(order_id)
        if order:
            order.payment_status = "Failed"
            order.status = "Cancelled"

    session.pop("cart", None)
    session.pop("delivery_info", None)
    flash("Payment cancelled.", "info")
    return render_template("payment_cancel.html")