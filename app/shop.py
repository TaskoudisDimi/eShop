from flask import Blueprint, render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import current_user, login_required
from .models import Product, Category, Order, OrderItem
from . import db
import os
import requests
import logging
import base64
import hmac
import hashlib

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

shop = Blueprint("shop", __name__)

@shop.route("/products")
def products():
    search = request.args.get("search", "")
    sort = request.args.get("sort", "name")
    page = request.args.get("page", 1, type=int)
    per_page = 9
    query = Product.query.filter(Product.name.ilike(f"%{search}%"))
    if sort == "price-asc":
        query = query.order_by(Product.price.asc())
    elif sort == "price-desc":
        query = query.order_by(Product.price.desc())
    else:
        query = query.order_by(Product.name)
    products = query.paginate(page=page, per_page=per_page)
    return render_template("products.html", products=products.items, pagination=products)

@shop.route("/product/<int:product_id>")
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template("product_detail.html", product=product)

@shop.route("/add_to_cart/<int:product_id>", methods=["POST"])
@login_required
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    quantity = int(request.form.get("quantity", 1))

    if quantity > product.stock:
        flash("Not enough stock available.")
        return redirect(url_for("shop.product_detail", product_id=product_id))

    if "cart" not in session:
        session["cart"] = []

    for item in session["cart"]:
        if item["product_id"] == product_id:
            item["quantity"] += quantity
            break
    else:
        session["cart"].append({"product_id": product_id, "quantity": quantity})

    session.modified = True
    flash("Product added to cart.")
    return redirect(url_for("shop.products"))

@shop.route("/cart")
@login_required
def view_cart():
    cart_items = []
    total = 0
    if "cart" in session:
        for item in session["cart"]:
            product = Product.query.get(item["product_id"])
            if product and product.stock >= item["quantity"]:
                cart_items.append({
                    "product": product,
                    "quantity": item["quantity"],
                    "subtotal": product.price * item["quantity"]
                })
                total += product.price * item["quantity"]
            else:
                flash(f"Product {product.name if product else 'Unknown'} is out of stock and removed from cart.")
                session["cart"].remove(item)
                session.modified = True
    return render_template("cart.html", cart_items=cart_items, total=total)

@shop.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    if "cart" not in session or not session["cart"]:
        flash("Your cart is empty.")
        return redirect(url_for("shop.view_cart"))

    cart_items = []
    total = 0
    if "cart" in session:
        for item in session["cart"]:
            product = Product.query.get(item["product_id"])
            if product:
                cart_items.append({
                    "product": product,
                    "quantity": item["quantity"],
                    "subtotal": product.price * item["quantity"]
                })
                total += product.price * item["quantity"]

    if request.method == "POST":
        shipping_address = request.form.get("address")
        payment_method = request.form.get("payment_method", "card")  # Default to card
        if not shipping_address:
            flash("Shipping address is required.")
            return render_template("checkout.html", cart_items=cart_items, total=total)

        # Clear previous payment session data
        session.pop("order_id", None)
        session.pop("viva_order_code", None)

        total_amount = 0
        order = Order(
            user_id=current_user.id,
            total_amount=0,
            status="Pending",
            payment_status="Pending",
            shipping_address=shipping_address,
            payment_method=payment_method
        )
        db.session.add(order)
        db.session.flush()

        for item in session["cart"]:
            product = Product.query.get(item["product_id"])
            if not product or product.stock < item["quantity"]:
                flash(f"Product {product.name if product else 'Unknown'} is out of stock.")
                db.session.rollback()
                return redirect(url_for("shop.view_cart"))

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
        db.session.commit()

        session["order_id"] = order.id
        session.modified = True

        try:
            # Get access token
            token_url = "https://demo-accounts.vivapayments.com/connect/token"
            auth_string = base64.b64encode(
                f"{os.getenv('VIVA_CLIENT_ID')}:{os.getenv('VIVA_CLIENT_SECRET')}".encode()
            ).decode()
            headers = {
                "Authorization": f"Basic {auth_string}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            payload = {
                "grant_type": "client_credentials"
            }
            logger.debug(f"Token request headers: {headers}")
            token_response = requests.post(token_url, data=payload, headers=headers)
            token_response.raise_for_status()
            token_data = token_response.json()
            access_token = token_data["access_token"]
            logger.debug(f"Access token retrieved: {access_token}")

            # Create payment order
            checkout_url = "https://demo-api.vivapayments.com/checkout/v2/orders"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            payload = {
                "amount": int(total_amount * 100),  # Convert to cents
                "customerTrns": f"Order {order.id} for {current_user.email}",
                "customer": {
                    "email": current_user.email,
                    "fullName": current_user.name or "Customer",
                    "countryCode": "GR"  # Adjust to your region
                },
                "paymentTimeout": 300,
                "webhookUrl": url_for("shop.payment_viva_callback", order_id=order.id, _external=True),
                "merchantTrns": f"Order-{order.id}",
                "sourceCode": os.getenv("VIVA_SOURCE_CODE", "eShop"),
                "requestLang": "el-GR",
                "successUrl": url_for("shop.payment_success", order_id=order.id, _external=True),
                "failureUrl": url_for("shop.payment_cancel", order_id=order.id, _external=True)
            }
            logger.debug(f"Checkout request payload: {payload}")
            checkout_response = requests.post(checkout_url, json=payload, headers=headers)
            checkout_response.raise_for_status()
            checkout_data = checkout_response.json()
            order_code = checkout_data["orderCode"]
            session["viva_order_code"] = order_code
            session.modified = True
            logger.debug(f"Viva.com order created: {order_code}")

            # Redirect to Viva Wallet checkout page
            checkout_url = f"https://demo.vivapayments.com/web/checkout?ref={order_code}"
            if payment_method != "card":
                checkout_url += f"&paymentMethod={payment_method}"
            return redirect(checkout_url)

        except requests.exceptions.HTTPError as e:
            logger.error(f"Viva.com API error: {str(e)}, response: {e.response.text}")
            flash(f"Payment processing error: {e.response.text}")
            db.session.rollback()
            return render_template("checkout.html", cart_items=cart_items, total=total)
        except Exception as e:
            logger.error(f"Viva.com payment processing error: {str(e)}")
            flash(f"Payment processing error: {str(e)}")
            db.session.rollback()
            return render_template("checkout.html", cart_items=cart_items, total=total)

    return render_template("checkout.html", cart_items=cart_items, total=total)

@shop.route("/payment/viva/callback/<int:order_id>", methods=["POST"])
def payment_viva_callback(order_id):
    # Verify webhook authenticity
    webhook_key = request.headers.get("Key")
    if not webhook_key:
        logger.error(f"Missing webhook key for order {order_id}")
        return jsonify({"error": "Missing webhook key"}), 400

    expected_key = os.getenv("VIVA_WEBHOOK_KEY")
    if not expected_key or webhook_key != expected_key:
        logger.error(f"Invalid webhook key for order {order_id}")
        return jsonify({"error": "Invalid webhook key"}), 403

    order = Order.query.get_or_404(order_id)
    data = request.get_json()
    logger.debug(f"Payment callback data: {data}")

    if data and data.get("statusId") == "F":
        order.payment_status = "Paid"
        order.status = "Completed"
        db.session.commit()
        session.pop("cart", None)
        session.pop("order_id", None)
        session.pop("viva_order_code", None)
        logger.debug(f"Viva.com payment captured for order {order_id}")
        return jsonify({"status": "success"}), 200
    else:
        order.payment_status = "Failed"
        order.status = "Cancelled"
        db.session.commit()
        logger.error(f"Viva.com payment not completed for order {order_id}: {data.get('statusId')}")
        return jsonify({"status": "failed", "reason": data.get("statusId")}), 400

@shop.route("/payment/success/<int:order_id>")
@login_required
def payment_success(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        flash("Unauthorized access to order.")
        logger.error(f"Unauthorized access to order {order_id} by user {current_user.id}")
        return redirect(url_for("shop.orders"))
    flash("Payment successful! Order placed.")
    return render_template("payment_success.html", order=order)

@shop.route("/payment/cancel/<int:order_id>")
@login_required
def payment_cancel(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        flash("Unauthorized access to order.")
        logger.error(f"Unauthorized access to order {order_id} by user {current_user.id}")
        return redirect(url_for("shop.orders"))
    order.payment_status = "Failed"
    order.status = "Cancelled"
    db.session.commit()
    session.pop("cart", None)
    session.pop("order_id", None)
    session.pop("viva_order_code", None)
    flash("Payment cancelled. Please try again.")
    return render_template("payment_cancel.html", order=order)

@shop.route("/orders")
@login_required
def orders():
    orders = Order.query.filter_by(user_id=current_user.id).all()
    return render_template("orders.html", orders=orders)