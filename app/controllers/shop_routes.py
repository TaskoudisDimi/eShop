from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import logging
import os
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.auth.transport import requests
import pathlib
from app.models import Product, Category, Order, OrderItem


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

shop = Blueprint("shop", __name__)

@shop.route("/")
@shop.route("/index")
def index():
    return render_template("index.html")

@shop.route("/dashboard")
@login_required
def dashboard():
    orders_count = Order.query.filter_by(user_id=current_user.id).count()
    return render_template("dashboard.html", orders_count=orders_count, is_admin=current_user.is_admin())

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

@shop.route("/delivery_info", methods=["GET", "POST"])
@login_required
def delivery_info():
    if request.method == "POST":
        address = request.form.get("address")
        phone = request.form.get("phone")
        floor = request.form.get("floor")
        zipcode = request.form.get("zipcode")
        region = request.form.get("region")

        if not all([address, phone, zipcode, region]):
            flash("All required fields (Address, Phone, Zipcode, Region) must be filled.", "error")
            return redirect(url_for("shop.delivery_info"))

        session["delivery_info"] = {
            "address": address,
            "phone": phone,
            "floor": floor,
            "zipcode": zipcode,
            "region": region
        }
        session.modified = True
        return redirect(url_for("payment.checkout"))
    return render_template("delivery_info.html")

@shop.route("/orders")
@login_required
def orders():
    orders = Order.query.filter_by(user_id=current_user.id).all()
    return render_template("orders.html", orders=orders)