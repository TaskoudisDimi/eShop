from flask import Blueprint, request, jsonify, session
import requests
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from eShop.app.models import Order


delivery = Blueprint("geniki_delivery", __name__)

# Geniki Taxydromiki API configuration
GENIKI_BASE_URL = "https://voucher.taxydromiki.gr/JobServicesV2.asmx"
GENIKI_AUTH_USERNAME = os.environ.get("GENIKI_AUTH_USERNAME", "your_username")
GENIKI_AUTH_PASSWORD = os.environ.get("GENIKI_AUTH_PASSWORD", "your_password")
GENIKI_APPLICATION_KEY = os.environ.get("GENIKI_APPLICATION_KEY", "your_application_key")

class JobServicesApiClient:
    def __init__(self, username, password, application_key):
        self.username = username
        self.password = password
        self.application_key = application_key
        self.base_url = GENIKI_BASE_URL
        self.auth_key = self._authenticate()

    def _authenticate(self):
        headers = {
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': 'http://voucher.taxydromiki.gr/JobServicesV2.asmx/Authenticate'
        }
        soap_body = f"""
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <Authenticate xmlns="http://voucher.taxydromiki.gr/JobServicesV2.asmx">
      <sUsrName>{self.username}</sUsrName>
      <sUsrPwd>{self.password}</sUsrPwd>
      <applicationKey>{self.application_key}</applicationKey>
    </Authenticate>
  </soap:Body>
</soap:Envelope>"""
        response = requests.post(self.base_url, data=soap_body, headers=headers)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            key = root.find('.//{http://voucher.taxydromiki.gr/JobServicesV2.asmx}Key')
            return key.text if key is not None else None
        return None

    def get_jobs_from_order_id(self, order_id):
        if not self.auth_key:
            return {'status': 'error', 'message': 'Authentication failed'}
        headers = {
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': 'http://voucher.taxydromiki.gr/JobServicesV2.asmx/GetJobsFromOrderId'
        }
        soap_body = f"""
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetJobsFromOrderId xmlns="http://voucher.taxydromiki.gr/JobServicesV2.asmx">
      <authKey>{self.auth_key}</authKey>
      <orderId>{order_id}</orderId>
    </GetJobsFromOrderId>
  </soap:Body>
</soap:Envelope>"""
        response = requests.post(self.base_url, data=soap_body, headers=headers)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            jobs = root.find('.//{http://voucher.taxydromiki.gr/JobServicesV2.asmx}GetJobsFromOrderIdResult')
            if jobs is not None:
                return {'status': 'success', 'data': {'order_id': order_id, 'jobs': jobs.text}}  # Adjust based on schema
            return {'status': 'error', 'message': 'No jobs found'}
        return {'status': 'error', 'message': f'Failed to fetch jobs: {response.status_code}'}

    def create_voucher_pickup_order(self, voucher_number, pickup_date, day_quarter):
        if not self.auth_key:
            return {'status': 'error', 'message': 'Authentication failed'}
        headers = {
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': 'http://voucher.taxydromiki.gr/JobServicesV2.asmx/CreateGetVoucherPickUpOrder'
        }
        soap_body = f"""
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <CreateGetVoucherPickUpOrder xmlns="http://voucher.taxydromiki.gr/JobServicesV2.asmx">
      <authKey>{self.auth_key}</authKey>
      <voucherNumber>{voucher_number}</voucherNumber>
      <pickupDate>{pickup_date.isoformat()}</pickupDate>
      <dayQuarter>{day_quarter}</dayQuarter>
    </CreateGetVoucherPickUpOrder>
  </soap:Body>
</soap:Envelope>"""
        response = requests.post(self.base_url, data=soap_body, headers=headers)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            result = root.find('.//{http://voucher.taxydromiki.gr/JobServicesV2.asmx}CreateGetVoucherPickUpOrderResult')
            if result is not None and result.text == 'Success':  # Adjust based on schema
                return {'status': 'success', 'data': {'voucher_number': voucher_number, 'status': 'created'}}
            return {'status': 'error', 'message': 'Voucher creation failed'}
        return {'status': 'error', 'message': f'Failed to create pickup order: {response.status_code}'}

    def get_job_status(self, job_id):
        if not self.auth_key:
            return {'status': 'error', 'message': 'Authentication failed'}
        headers = {
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': 'http://voucher.taxydromiki.gr/JobServicesV2.asmx/GetJobStatus'
        }
        soap_body = f"""
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetJobStatus xmlns="http://voucher.taxydromiki.gr/JobServicesV2.asmx">
      <authKey>{self.auth_key}</authKey>
      <jobId>{job_id}</jobId>
    </GetJobStatus>
  </soap:Body>
</soap:Envelope>"""
        response = requests.post(self.base_url, data=soap_body, headers=headers)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            status = root.find('.//{http://voucher.taxydromiki.gr/JobServicesV2.asmx}GetJobStatusResult')
            if status is not None:
                return {'status': 'success', 'data': {'job_id': job_id, 'status': status.text}}  # Adjust based on schema
            return {'status': 'error', 'message': 'No status found'}
        return {'status': 'error', 'message': f'Failed to get job status: {response.status_code}'}

    def get_voucher_pickup_status(self, voucher_number):
        if not self.auth_key:
            return {'status': 'error', 'message': 'Authentication failed'}
        headers = {
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': 'http://voucher.taxydromiki.gr/JobServicesV2.asmx/GetVoucherPickUpStatus'
        }
        soap_body = f"""
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetVoucherPickUpStatus xmlns="http://voucher.taxydromiki.gr/JobServicesV2.asmx">
      <authKey>{self.auth_key}</authKey>
      <voucherNumber>{voucher_number}</voucherNumber>
    </GetVoucherPickUpStatus>
  </soap:Body>
</soap:Envelope>"""
        response = requests.post(self.base_url, data=soap_body, headers=headers)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            status = root.find('.//{http://voucher.taxydromiki.gr/JobServicesV2.asmx}GetVoucherPickUpStatusResult')
            if status is not None:
                return {'status': 'success', 'data': {'voucher_number': voucher_number, 'status': status.text}}  # Adjust based on schema
            return {'status': 'error', 'message': 'No status found'}
        return {'status': 'error', 'message': f'Failed to get voucher pickup status: {response.status_code}'}

    def cancel_voucher_pickup_order(self, voucher_number):
        if not self.auth_key:
            return {'status': 'error', 'message': 'Authentication failed'}
        headers = {
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': 'http://voucher.taxydromiki.gr/JobServicesV2.asmx/CancelVoucherPickUpOrder'
        }
        soap_body = f"""
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <CancelVoucherPickUpOrder xmlns="http://voucher.taxydromiki.gr/JobServicesV2.asmx">
      <authKey>{self.auth_key}</authKey>
      <voucherNumber>{voucher_number}</voucherNumber>
    </CancelVoucherPickUpOrder>
  </soap:Body>
</soap:Envelope>"""
        response = requests.post(self.base_url, data=soap_body, headers=headers)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            result = root.find('.//{http://voucher.taxydromiki.gr/JobServicesV2.asmx}CancelVoucherPickUpOrderResult')
            if result is not None and result.text == 'Success':  # Adjust based on schema
                return {'status': 'success', 'data': {'voucher_number': voucher_number, 'status': 'cancelled'}}
            return {'status': 'error', 'message': 'Cancellation failed'}
        return {'status': 'error', 'message': f'Failed to cancel voucher pickup: {response.status_code}'}

    def get_available_pickup_times(self, pickup_date):
        if not self.auth_key:
            return {'status': 'error', 'message': 'Authentication failed'}
        headers = {
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': 'http://voucher.taxydromiki.gr/JobServicesV2.asmx/GetAvailablePickupTimes'
        }
        soap_body = f"""
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetAvailablePickupTimes xmlns="http://voucher.taxydromiki.gr/JobServicesV2.asmx">
      <authKey>{self.auth_key}</authKey>
      <pickupDate>{pickup_date.isoformat()}</pickupDate>
    </GetAvailablePickupTimes>
  </soap:Body>
</soap:Envelope>"""
        response = requests.post(self.base_url, data=soap_body, headers=headers)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            times = root.findall('.//{http://voucher.taxydromiki.gr/JobServicesV2.asmx}GetAvailablePickupTimesResult/time')
            if times:
                return {'status': 'success', 'data': {'pickup_date': pickup_date.isoformat(), 'times': [time.text for time in times]}}  # Adjust based on schema
            return {'status': 'error', 'message': 'No times found'}
        return {'status': 'error', 'message': f'Failed to get available pickup times: {response.status_code}'}

# Initialize API client
geniki_client = JobServicesApiClient(GENIKI_AUTH_USERNAME, GENIKI_AUTH_PASSWORD, GENIKI_APPLICATION_KEY)

@delivery.route("/delivery/options", methods=["GET"])
def get_delivery_options():
    destination = request.args.get("destination", "Thessaloniki")
    weight_kg = float(request.args.get("weight", 2.0))
    
    geniki_response = geniki_client.get_jobs_from_order_id("sample_order_id")  # Replace with actual logic
    geniki_delivery = {
        "method": "Geniki Standard",
        "cost": 5.0,  # Placeholder, replace with actual cost from API
        "days": 3     # Placeholder, replace with actual days from API
    } if geniki_response['status'] == 'success' else None

    delivery_options = [geniki_delivery] if geniki_delivery else []
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
    
    if session["delivery"]["method"] != "Geniki Standard":
        return jsonify({"error": "Unsupported delivery method"}), 400
    
    order_data = {
        "voucher_number": f"GENIKI-{Order.query.count() + 1}",
        "pickup_date": datetime.now(),
        "day_quarter": "200"  
    }
    response = geniki_client.create_voucher_pickup_order(
        order_data["voucher_number"],
        order_data["pickup_date"],
        order_data["day_quarter"]
    )
    if response['status'] == 'error':
        return jsonify(response), 500
    
    voucher_no = response['data']['voucher_number']
    if voucher_no:
        session["voucher_no"] = voucher_no
        return jsonify({"message": "Voucher created", "voucher_no": voucher_no})
    return jsonify({"error": "Failed to create voucher"}), 500

@delivery.route("/delivery/job-status", methods=["GET"])
def get_job_status():
    job_id = request.args.get("job_id", "sample_job_id")
    response = geniki_client.get_job_status(job_id)
    if response['status'] == 'error':
        return jsonify(response), 500
    return jsonify(response)

@delivery.route("/delivery/voucher-pickup-status", methods=["GET"])
def get_voucher_pickup_status():
    voucher_number = request.args.get("voucher_number", "sample_voucher")
    response = geniki_client.get_voucher_pickup_status(voucher_number)
    if response['status'] == 'error':
        return jsonify(response), 500
    return jsonify(response)

@delivery.route("/delivery/cancel-voucher", methods=["POST"])
def cancel_voucher_pickup():
    voucher_number = request.json.get("voucher_number", "sample_voucher")
    response = geniki_client.cancel_voucher_pickup_order(voucher_number)
    if response['status'] == 'error':
        return jsonify(response), 500
    return jsonify(response)

@delivery.route("/delivery/available-pickup-times", methods=["GET"])
def get_available_pickup_times():
    pickup_date = datetime.now()  # Use current date or from request
    response = geniki_client.get_available_pickup_times(pickup_date)
    if response['status'] == 'error':
        return jsonify(response), 500
    return jsonify(response)