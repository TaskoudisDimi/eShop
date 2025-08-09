from flask import Blueprint, request, jsonify, session
import requests
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from eShop.app.models import Product, Order

delivery = Blueprint('delivery', __name__)

ACS_API_KEY = "your_acs_api_key"
ACS_BASE_URL = "https://api.acscourier.net/v1"



def make_acs_request(alias, params):
    headers = {"ACSAlias": alias, "Authorization": f"Bearer {ACS_API_KEY}"}
    response = requests.post(ACS_BASE_URL, json=params, headers=headers, verify=True)
    if response.status_code == 200:
        data = response.json()
        if data.get("ACSExecution_HasError", False):
            return jsonify({"error": data.get("ACSExecutionErrorMessage", "Unknown error")}), 500
        return data
    else:
        return jsonify({"error": f"ACS API error: {response.status_code}"}), response.status_code

@delivery.route("/delivery/options", methods=["GET"])
def get_delivery_options():
    destination = request.args.get("destination", "Thessaloniki")
    weight_kg = float(request.args.get("weight", 2.0))
    
    acs_params = {
        "ACSAlias": "ACS_Price_Lookup",
        "ACSInputParameters": {
            "Origin": "Athens",
            "Destination": destination,
            "Weight_Kg": weight_kg,
            "Delivery_Type": "Standard"
        }
    }
    acs_response = make_acs_request("ACS_Price_Lookup", acs_params)
    if "error" in acs_response:
        return acs_response
    acs_options = acs_response.get("ACSCutputResponse", {})
    acs_delivery = {
        "method": "ACS Standard",
        "cost": acs_options.get("Total_Amount", 0.0),
        "days": 2  # Placeholder, adjust based on ACS response
    }

    delivery_options = [acs_delivery]
    return jsonify({"options": delivery_options})

@delivery.route("/delivery/select", methods=["POST"])
def select_delivery():
    data = request.json
    method = data.get("method")
    cost = data.get("cost")
    days = data.get("days")
    
    if "delivery" not in session:
        session["delivery"] = {}
    session["delivery"] = {"method": method, "cost": cost, "days": days}
    session.modified = True
    
    return jsonify({"message": "Delivery method selected", "method": method, "cost": cost})

@delivery.route("/delivery/create-voucher", methods=["POST"])
def create_voucher():
    if "delivery" not in session or "cart" not in session:
        return jsonify({"error": "No delivery or cart data available"}), 400
    
    if session["delivery"]["method"] != "ACS Standard":
        return jsonify({"error": "Unsupported delivery method"}), 400
    
    order_data = {
        "ACSAlias": "ACS_Create_Voucher",
        "ACSInputParameters": {
            "Company_ID": os.environ.get("ACS_COMPANY_ID", "demo"),
            "Company_Password": os.environ.get("ACS_COMPANY_PASSWORD", "demo"),
            "User_ID": os.environ.get("ACS_USER_ID", "demo"),
            "User_Password": os.environ.get("ACS_USER_PASSWORD", "demo"),
            "Sender_Address": "Athens, Greece",
            "Recipient_Address": request.json.get("destination", "Thessaloniki, Greece"),
            "Weight_Kg": sum(item["quantity"] * Product.query.get(item["product_id"]).weight for item in session["cart"]),
            "Item_Quantity": len(session["cart"]),
            "Reference_Key1": f"ORDER-{Order.query.count() + 1}"
        }
    }
    response = make_acs_request("ACS_Create_Voucher", order_data)
    
    if "error" in response:
        return response
    
    voucher_no = response.get("ACSCutputResponse", {}).get("Voucher_NO")
    if voucher_no:
        session["voucher_no"] = voucher_no
        return jsonify({"message": "Voucher created", "voucher_no": voucher_no})
    return jsonify({"error": "Failed to create voucher"}), 500