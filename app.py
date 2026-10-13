"""
Flask Web Server and REST API for TaskOperator-AI Dashboard
"""
import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from agent.operator import AutonomousOperator
from sandbox.erp_system import EnterpriseERPSystem

app = Flask(__name__, static_folder="static")
CORS(app)

erp_system = EnterpriseERPSystem()
operator = AutonomousOperator(erp_system=erp_system)


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:path>")
def static_proxy(path):
    return send_from_directory(app.static_folder, path)


@app.route("/api/task/start", methods=["POST"])
def start_task():
    data = request.json or {}
    goal = data.get("goal", "").strip()
    if not goal:
        return jsonify({"error": "Goal cannot be empty"}), 400

    state = operator.initialize_task(goal)
    return jsonify({
        "status": "INITIALIZED",
        "state": state.model_dump()
    })


@app.route("/api/task/step", methods=["POST"])
def step_task():
    data = request.json or {}
    auto_approve = data.get("auto_approve", False)
    
    result = operator.step(auto_approve=auto_approve)
    return jsonify({
        "step_result": result,
        "state": operator.state.model_dump() if operator.state else None
    })


@app.route("/api/task/run-all", methods=["POST"])
def run_all():
    data = request.json or {}
    auto_approve = data.get("auto_approve", False)
    
    state = operator.run_to_completion(auto_approve=auto_approve)
    return jsonify({
        "status": "COMPLETED" if state.is_completed else ("AWAITING_APPROVAL" if state.waiting_for_approval else "IN_PROGRESS"),
        "state": state.model_dump()
    })


@app.route("/api/task/approve", methods=["POST"])
def approve_step():
    data = request.json or {}
    approved = data.get("approved", True)
    
    res = operator.submit_human_approval(approved=approved)
    return jsonify({
        "result": res,
        "state": operator.state.model_dump() if operator.state else None
    })


@app.route("/api/task/state", methods=["GET"])
def get_state():
    if not operator.state:
        return jsonify({"state": None})
    return jsonify({"state": operator.state.model_dump()})


@app.route("/api/erp/invoices", methods=["GET"])
def get_erp_invoices():
    invoices = erp_system.list_invoices()
    return jsonify({"invoices": invoices})


@app.route("/api/erp/reset", methods=["POST"])
def reset_erp():
    erp_system.reset_database()
    return jsonify({"status": "SUCCESS", "message": "ERP database wiped for fresh demonstration."})


if __name__ == "__main__":
    print("[SERVER] Starting TaskOperator-AI Dashboard on http://localhost:5000 ...")
    app.run(host="127.0.0.1", port=5000, debug=False)
