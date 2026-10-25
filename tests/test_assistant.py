"""
test_assistant.py - Automated Unit & Integration Tests for Sales BI Assistant

Covers:
1. Core Example Questions (Total Revenue, Top Product, Monthly Trend, Top Region, MoM Change)
2. Edge cases in Data Cleaning (Returns, Zero Quantities, Missing Price Imputation)
3. Security Guardrails (SQL Injection prevention, Destructive Command Blocking)
4. Out-of-scope / Invalid inputs
5. REST API endpoint responses
"""

import os
import pytest
from app import app
from db import clean_and_load_data, DEFAULT_CSV_PATH, DEFAULT_DB_PATH, execute_safe_query
from engine import BIAssistantEngine


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Ensure clean test database is initialized before test suite runs."""
    clean_and_load_data(DEFAULT_CSV_PATH, DEFAULT_DB_PATH)


@pytest.fixture
def engine():
    return BIAssistantEngine(DEFAULT_DB_PATH)


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# --- 1. Core Analytics Questions ---

def test_q1_total_revenue(engine):
    """Test Question 1: Total Revenue calculation."""
    res = engine.process_question("What is the total revenue?")
    assert res["is_valid"] is True
    assert res["intent"] == "TOTAL_REVENUE"
    assert "1,445,200.00" in res["answer"]
    assert res["metrics"]["Completed Orders"] == "49"
    assert res["sql_query"] is not None


def test_q2_highest_product_revenue(engine):
    """Test Question 2: Highest revenue product."""
    res = engine.process_question("Which product generated the highest revenue?")
    assert res["is_valid"] is True
    assert res["intent"] == "HIGHEST_PRODUCT_REVENUE"
    assert "Monitor" in res["answer"]
    assert "473,000.00" in res["answer"]
    assert res["metrics"]["Top Product"] == "Monitor"


def test_q3_monthly_revenue_trend(engine):
    """Test Question 3: Monthly revenue trend."""
    res = engine.process_question("What is the monthly revenue trend?")
    assert res["is_valid"] is True
    assert res["intent"] == "MONTHLY_TREND"
    assert "2026-05" in res["answer"]  # Peak month
    assert len(res["supporting_data"]) == 6
    assert res["chart_type"] == "line"


def test_q4_highest_region_sales(engine):
    """Test Question 4: Highest sales region."""
    res = engine.process_question("Which region generated the highest sales?")
    assert res["is_valid"] is True
    assert res["intent"] == "HIGHEST_REGION_SALES"
    assert "South" in res["answer"]
    assert "411,200.00" in res["answer"]
    assert res["metrics"]["Top Region"] == "South"


def test_q5_revenue_change_between_two_months(engine):
    """Test Question 5: Revenue change between April and May."""
    res = engine.process_question("How did revenue change between April and May?")
    assert res["is_valid"] is True
    assert res["intent"] == "MONTH_COMPARISON"
    assert "+77,800.00" in res["answer"] or "77,800.00" in res["answer"]
    assert "+32.32%" in res["answer"] or "32.32%" in res["answer"]
    assert res["metrics"]["Absolute Change"] == "+₹77,800.00"


# --- 2. Data Cleaning & Edge Cases ---

def test_edge_case_returned_transaction():
    """Verify that returned transactions (TXN0033) are excluded from net revenue."""
    res = execute_safe_query("SELECT is_valid, net_revenue, status FROM sales WHERE transaction_id = 'TXN0033';")
    assert res["success"] is True
    row = res["rows"][0]
    assert row["status"] == "Returned"
    assert row["is_valid"] == 0
    assert row["net_revenue"] == 0.0


def test_edge_case_zero_quantity_transaction():
    """Verify that zero-quantity transactions (TXN0034) are marked invalid."""
    res = execute_safe_query("SELECT is_valid, quantity FROM sales WHERE transaction_id = 'TXN0034';")
    assert res["success"] is True
    row = res["rows"][0]
    assert row["quantity"] == 0
    assert row["is_valid"] == 0


def test_edge_case_missing_unit_price_imputation():
    """Verify missing unit price in TXN0051 (Laptop Stand) is imputed to 1200.0."""
    res = execute_safe_query("SELECT unit_price, product, cleaning_notes FROM sales WHERE transaction_id = 'TXN0051';")
    assert res["success"] is True
    row = res["rows"][0]
    assert row["product"] == "Laptop Stand"
    assert row["unit_price"] == 1200.0
    assert "imputed" in row["cleaning_notes"].lower()


# --- 3. Security Guardrails & Destructive Commands ---

def test_security_block_destructive_drop(engine):
    """Ensure DROP TABLE attempt is blocked by security guardrails."""
    res = engine.process_question("DROP TABLE sales;")
    assert res["is_valid"] is False
    assert res["intent"] == "SECURITY_ALERT"
    assert "strictly prohibited" in res["answer"].lower()
    assert res["sql_query"] is None


def test_security_block_destructive_delete(engine):
    """Ensure DELETE FROM attempt is blocked."""
    res = engine.process_question("DELETE FROM sales WHERE region = 'North';")
    assert res["is_valid"] is False
    assert res["intent"] == "SECURITY_ALERT"


def test_security_block_destructive_update(engine):
    """Ensure UPDATE attempt is blocked."""
    res = engine.process_question("UPDATE sales SET net_revenue = 0;")
    assert res["is_valid"] is False
    assert res["intent"] == "SECURITY_ALERT"


# --- 4. Invalid and Unsupported Questions ---

def test_empty_question(engine):
    """Test handling of empty or whitespace query."""
    res = engine.process_question("   ")
    assert res["is_valid"] is False
    assert res["intent"] == "INVALID_EMPTY"


def test_out_of_scope_question(engine):
    """Test handling of irrelevant question outside sales domain."""
    res = engine.process_question("What is the capital of Australia?")
    assert res["is_valid"] is False
    assert res["intent"] == "UNSUPPORTED"
    assert "Try asking questions like" in res["answer"]


# --- 5. REST API Integration ---

def test_api_query_endpoint(client):
    """Test POST /api/query endpoint."""
    response = client.post("/api/query", json={"question": "What is the total revenue?"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["is_valid"] is True
    assert data["intent"] == "TOTAL_REVENUE"


def test_api_stats_endpoint(client):
    """Test GET /api/stats endpoint."""
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.get_json()
    assert data["total_transactions"] == 51
    assert data["valid_transactions"] == 49
    assert data["total_net_revenue"] == 1445200.0
