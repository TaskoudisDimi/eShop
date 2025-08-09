from flask import Flask, Blueprint, request, jsonify
from delivery_acs import delivery as acs_delivery
from delivery_geniki import delivery as geniki_delivery

app = Flask(__name__)

# Register blueprints
app.register_blueprint(acs_delivery, url_prefix='/acs')
app.register_blueprint(geniki_delivery, url_prefix='/geniki')

if app == '__main__':
    app.run(debug=True)
    