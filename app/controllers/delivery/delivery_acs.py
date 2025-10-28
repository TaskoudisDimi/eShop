# app/controllers/delivery/acs.py
from flask import Blueprint, request, jsonify, session, current_user
from flask_login import login_required
from app.models import Product, Order
from app.db import db_transaction
import requests
import os
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

delivery = Blueprint('delivery', __name__, url_prefix='/delivery')

ACS_API_KEY = os.getenv("ACS_API_KEY")
ACS_BASE_URL = "https://webservices.acscourier.net/ACSRestServices/api/ACSAutoRest"


def acs_request(alias, params):
    headers = {
        "ACSApiKey": ACS_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "ACSAlias": alias,
        "ACSInputParameters": params
    }
    try:
        resp = requests.post(ACS_BASE_URL, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("ACSExecution_HasError"):
            return {"error": data.get("ACSExecutionErrorMessage", "ACS error")}, 500
        return data, 200
    except requests.exceptions.RequestException as e:
        logger.error(f"ACS network error: {e}")
        return {"error": "ACS service unavailable"}, 503


@delivery.route("/options", methods=["GET"])
def get_delivery_options():
    destination = request.args.get("destination", "Thessaloniki")
    weight_kg = float(request.args.get("weight", 2.0))

    params = {
        "Origin": "Athens",
        "Destination": destination,
        "Weight_Kg": weight_kg,
        "Delivery_Type": "Standard"
    }
    result, status = acs_request("ACS_Price_Lookup", params)
    if status != 200:
        return jsonify(result), status

    opts = result.get("ACSOutputResponse", {})
    delivery_option = {
        "method": "ACS Standard",
        "cost": float(opts.get("Total_Amount", 0)),
        "days": 2
    }
    return jsonify({"options": [delivery_option]})


@delivery.route("/select", methods=["POST"])
def select_delivery():
    data = request.get_json()
    session["delivery"] = {
        "method": data.get("method"),
        "cost": data.get("cost"),
        "days": data.get("days")
    }
    session.modified = True
    return jsonify({"message": "Delivery selected"})


@delivery.route("/create-voucher", methods=["POST"])
@login_required
@db_transaction
def create_voucher():
    if "delivery" not in session or session["delivery"]["method"] != "ACS Standard":
        return jsonify({"error": "Invalid delivery method"}), 400

    if "cart" not in session or not session["cart"]:
        return jsonify({"error": "Cart is empty"}), 400

    # Calculate weight
    total_weight = sum(
        item["quantity"] * (Product.query.get(item["product_id"]).weight or 1.0)
        for item in session["cart"]
    )

    params = {
        "Company_ID": os.getenv("ACS_COMPANY_ID"),
        "Company_Password": os.getenv("ACS_COMPANY_PASSWORD"),
        "User_ID": os.getenv("ACS_USER_ID"),
        "User_Password": os.getenv("ACS_USER_PASSWORD"),
        "Sender_Address": "Athens, Greece",
        "Recipient_Address": session["delivery_info"]["address"],
        "Weight_Kg": total_weight,
        "Item_Quantity": len(session["cart"]),
        "Reference_Key1": f"ORDER-{Order.query.count() + 1}",
        "Recipient_Name": current_user.name or "Customer",
        "Recipient_Phone": session["delivery_info"]["phone"],
        "Recipient_Zipcode": session["delivery_info"]["zipcode"],
        "Recipient_Region": session["delivery_info"]["region"]
    }

    result, status = acs_request("ACS_Create_Voucher", params)
    if status != 200:
        return jsonify(result), status

    voucher_no = result.get("ACSOutputResponse", {}).get("Voucher_No")
    if voucher_no:
        session["voucher_no"] = voucher_no
        return jsonify({"message": "Voucher created", "voucher_no": voucher_no})
    return jsonify({"error": "Failed to create voucher"}), 500