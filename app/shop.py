from flask import Blueprint, render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import current_user, login_required
from .models import Product, Category, Order, OrderItem
from . import db
import logging


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

@shop.route("/orders")
@login_required
def orders():
    orders = Order.query.filter_by(user_id=current_user.id).all()
    return render_template("orders.html", orders=orders)