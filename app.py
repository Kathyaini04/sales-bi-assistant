"""
app.py - Main Web Server and API for Sales BI Assistant

Runs Flask web server providing:
- Web UI at http://localhost:5000
- REST API at POST /api/query
- Database KPI stats at GET /api/stats
- Transaction sample and data quality audit at GET /api/data
"""

import os
import sys
from flask import Flask, jsonify, render_template, request

from db import clean_and_load_data, DEFAULT_CSV_PATH, DEFAULT_DB_PATH, get_database_summary, execute_safe_query
from engine import BIAssistantEngine

app = Flask(__name__)
engine = BIAssistantEngine()


@app.before_request
def ensure_db():
    """Ensure database exists and is loaded before handling requests."""
    if not os.path.exists(DEFAULT_DB_PATH):
        print("Database not found. Initializing ETL pipeline...")
        clean_and_load_data(DEFAULT_CSV_PATH, DEFAULT_DB_PATH)


@app.route("/")
def index():
    """Serve the modern Business Intelligence Dashboard."""
    return render_template("index.html")


@app.route("/api/query", methods=["POST"])
def query_assistant():
    """
    Accepts natural language business questions and returns structured answers
    supported by verified SQL queries and data.
    """
    payload = request.get_json(silent=True) or {}
    question = payload.get("question", "")

    if not question:
        return jsonify({
            "success": False,
            "error": "Missing 'question' parameter in request body.",
            "answer": "Please provide a valid question.",
        }), 400

    response = engine.process_question(question)
    status_code = 200 if response["is_valid"] else 400
    if response["intent"] in ["SECURITY_ALERT", "UNSUPPORTED"]:
        status_code = 200  # Return 200 with structured alert for graceful UI handling

    return jsonify(response), status_code


@app.route("/api/stats", methods=["GET"])
def get_stats():
    """Return live summary metrics from the database."""
    summary = get_database_summary()
    return jsonify(summary)


@app.route("/api/data", methods=["GET"])
def get_data_preview():
    """Return transactions and data quality audit records."""
    query = """
    SELECT
        transaction_id,
        raw_order_date,
        product,
        category,
        region,
        sales_channel,
        quantity,
        unit_price,
        discount_amount,
        net_revenue,
        status,
        is_valid,
        cleaning_notes
    FROM sales
    ORDER BY order_date ASC;
    """
    res = execute_safe_query(query)
    return jsonify(res)


if __name__ == "__main__":
    # Ensure database is ready before server starts
    if not os.path.exists(DEFAULT_DB_PATH):
        print("Initializing sales database from CSV...")
        clean_and_load_data(DEFAULT_CSV_PATH, DEFAULT_DB_PATH)

    port = int(os.environ.get("PORT", 5000))
    host = "0.0.0.0"

    print("\n" + "=" * 65)
    print("🚀 Sales Business Intelligence Assistant Server Running")
    print(f"👉 Local Access:     http://localhost:{port}")
    print(f"👉 Network / Cloud:  http://127.0.0.1:{port} or 0.0.0.0:{port}")
    print("=" * 65 + "\n")

    app.run(host=host, port=port, debug=False)
