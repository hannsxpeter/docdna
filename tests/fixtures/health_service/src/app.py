from flask import Flask, jsonify
from fhirclient import client

app = Flask(__name__)


@app.route("/Patient/<pid>")
def read_patient(pid):
    return jsonify({"resourceType": "Patient", "id": pid})
