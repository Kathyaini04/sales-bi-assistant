"""
db.py - SQLite Database Management and ETL Pipeline for Sales BI Assistant

Handles:
1. Loading and cleaning data from CSV.
2. Data quality checks, price imputation, invalid record flagging.
3. Safe read-only SQL query execution with AST/regex safety validation.
"""

import csv
import os
import re
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DEFAULT_CSV_PATH = os.path.join(DEFAULT_DATA_DIR, "sales_data.csv")
DEFAULT_DB_PATH = os.path.join(DEFAULT_DATA_DIR, "sales.db")

FORBIDDEN_SQL_PATTERNS = [
    r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE|REPLACE|ATTACH|DETACH|PRAGMA)\b",
    r"\b(CREATE\s+(TABLE|VIEW|INDEX|TRIGGER))\b",
    r";\s*\S",  # Prevent multiple statements chained with semicolon
]


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Return an active connection to the SQLite database with Row factory."""
    path = db_path or DEFAULT_DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def parse_date(date_str: str) -> Tuple[str, str]:
    """
    Parses 'DD-MM-YYYY' into ISO 'YYYY-MM-DD' and 'YYYY-MM'.
    Returns ('YYYY-MM-DD', 'YYYY-MM').
    """
    date_str = date_str.strip()
    dt = datetime.strptime(date_str, "%d-%m-%Y")
    return dt.strftime("%Y-%m-%d"), dt.strftime("%Y-%m")


def clean_and_load_data(
    csv_path: Optional[str] = None, db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    ETL Pipeline:
    - Reads raw CSV
    - Computes catalog pricing for imputation
    - Flags invalid records (returns, zero quantity)
    - Normalizes dates to ISO-8601
    - Calculates gross and net revenue
    - Inserts into SQLite database
    """
    source_csv = csv_path or DEFAULT_CSV_PATH
    target_db = db_path or DEFAULT_DB_PATH

    if not os.path.exists(source_csv):
        raise FileNotFoundError(f"Source CSV not found at {source_csv}")

    with open(source_csv, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        raw_rows = list(reader)

    # Step 1: Build known price catalog for imputation
    catalog_prices: Dict[str, float] = {}
    for r in raw_rows:
        prod = (r.get("Product") or "").strip()
        price_val = (r.get("Unit_price") or "").strip()
        if prod and price_val:
            try:
                p = float(price_val)
                if p > 0:
                    catalog_prices[prod] = p
            except ValueError:
                pass

    conn = get_connection(target_db)
    cursor = conn.cursor()

    # Create schema
    cursor.execute("DROP TABLE IF EXISTS sales;")
    cursor.execute("DROP VIEW IF EXISTS v_active_sales;")

    cursor.execute(
        """
        CREATE TABLE sales (
            transaction_id TEXT PRIMARY KEY,
            order_date TEXT NOT NULL,         -- YYYY-MM-DD
            raw_order_date TEXT NOT NULL,     -- Original DD-MM-YYYY
            month TEXT NOT NULL,              -- YYYY-MM
            product TEXT NOT NULL,
            category TEXT NOT NULL,
            region TEXT NOT NULL,
            sales_channel TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            discount_amount REAL NOT NULL,
            gross_revenue REAL NOT NULL,
            net_revenue REAL NOT NULL,
            status TEXT NOT NULL,
            is_valid INTEGER NOT NULL,        -- 1 = valid completed sale, 0 = flagged/returned/zero qty
            cleaning_notes TEXT
        );
        """
    )

    audit_log = []
    cleaned_records = []

    for r in raw_rows:
        tid = (r.get("Transaction_Id") or "").strip()
        raw_date = (r.get("Order_date") or "").strip()
        prod = (r.get("Product") or "").strip()
        cat = (r.get("Category") or "").strip()
        reg = (r.get("Region") or "").strip()
        channel = (r.get("Sales_channel") or "").strip()
        status = (r.get("Status") or "Completed").strip()

        notes = []
        is_valid = 1

        # Date parsing
        try:
            iso_date, month_key = parse_date(raw_date)
        except Exception:
            iso_date, month_key = raw_date, "UNKNOWN"
            notes.append(f"Unrecognized date format: {raw_date}")

        # Quantity parsing
        try:
            qty = int((r.get("Quantity") or "0").strip())
            if qty <= 0:
                is_valid = 0
                notes.append(f"Invalid quantity ({qty}): flagged non-revenue")
        except ValueError:
            qty = 0
            is_valid = 0
            notes.append("Non-numeric quantity: defaulted to 0")

        # Unit price parsing & imputation
        price_str = (r.get("Unit_price") or "").strip()
        if not price_str:
            imputed = catalog_prices.get(prod, 0.0)
            unit_price = imputed
            notes.append(f"Missing unit_price imputed as {imputed:.2f} from {prod} catalog")
        else:
            try:
                unit_price = float(price_str)
            except ValueError:
                unit_price = catalog_prices.get(prod, 0.0)
                notes.append(f"Invalid unit_price imputed as {unit_price:.2f}")

        # Discount parsing
        try:
            discount = float((r.get("Discount_amount") or "0").strip())
        except ValueError:
            discount = 0.0
            notes.append("Invalid discount: defaulted to 0.0")

        # Status check
        if status.lower() != "completed":
            is_valid = 0
            notes.append(f"Order status is '{status}' (excluded from net revenue)")

        gross_revenue = qty * unit_price
        net_revenue = gross_revenue - discount if is_valid else 0.0

        cleaning_notes_str = "; ".join(notes) if notes else "Clean"
        if notes:
            audit_log.append({
                "transaction_id": tid,
                "product": prod,
                "status": status,
                "notes": cleaning_notes_str,
            })

        cleaned_records.append((
            tid,
            iso_date,
            raw_date,
            month_key,
            prod,
            cat,
            reg,
            channel,
            qty,
            unit_price,
            discount,
            gross_revenue,
            net_revenue,
            status,
            is_valid,
            cleaning_notes_str,
        ))

    cursor.executemany(
        """
        INSERT INTO sales (
            transaction_id, order_date, raw_order_date, month,
            product, category, region, sales_channel,
            quantity, unit_price, discount_amount,
            gross_revenue, net_revenue, status, is_valid, cleaning_notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        cleaned_records,
    )

    # Create Indexes for fast querying
    cursor.execute("CREATE INDEX idx_sales_month ON sales(month);")
    cursor.execute("CREATE INDEX idx_sales_prod ON sales(product);")
    cursor.execute("CREATE INDEX idx_sales_reg ON sales(region);")
    cursor.execute("CREATE INDEX idx_sales_valid ON sales(is_valid);")

    # Create View for active sales only
    cursor.execute(
        """
        CREATE VIEW v_active_sales AS
        SELECT * FROM sales WHERE is_valid = 1;
        """
    )

    conn.commit()
    conn.close()

    return {
        "total_records": len(cleaned_records),
        "valid_records": sum(1 for c in cleaned_records if c[14] == 1),
        "flagged_records": len(audit_log),
        "audit_log": audit_log,
    }


def validate_sql(sql: str) -> Tuple[bool, Optional[str]]:
    """
    Validates that a SQL query:
    1. Starts with SELECT or WITH.
    2. Contains no destructive statements (DROP, DELETE, UPDATE, INSERT, ALTER, etc.).
    3. Contains no multiple statement delimiters.
    """
    cleaned = sql.strip()
    if not cleaned:
        return False, "Query is empty."

    # Must start with SELECT or WITH (case-insensitive)
    if not re.match(r"^(SELECT|WITH)\b", cleaned, re.IGNORECASE):
        return False, "Only read-only SELECT queries are permitted."

    # Check for forbidden destructive patterns
    for pat in FORBIDDEN_SQL_PATTERNS:
        if re.search(pat, cleaned, re.IGNORECASE):
            return False, f"Potentially unsafe or forbidden SQL pattern detected: {pat}"

    return True, None


def execute_safe_query(
    sql: str, params: Optional[Tuple[Any, ...]] = None, db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Safely executes a read-only SQL query against the SQLite sales database.
    Returns:
    {
        "success": bool,
        "columns": List[str],
        "rows": List[Dict[str, Any]],
        "row_count": int,
        "error": Optional[str],
        "sql": str
    }
    """
    is_valid, error_msg = validate_sql(sql)
    if not is_valid:
        return {
            "success": False,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "error": error_msg,
            "sql": sql,
        }

    conn = get_connection(db_path)
    cursor = conn.cursor()
    try:
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)

        columns = [col[0] for col in cursor.description] if cursor.description else []
        raw_rows = cursor.fetchall()
        rows = [dict(zip(columns, r)) for r in raw_rows]

        return {
            "success": True,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "error": None,
            "sql": sql,
        }
    except Exception as e:
        return {
            "success": False,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "error": str(e),
            "sql": sql,
        }
    finally:
        conn.close()


def get_database_summary(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Return high-level summary KPIs for the dashboard."""
    query = """
    SELECT
        COUNT(*) AS total_transactions,
        SUM(CASE WHEN is_valid = 1 THEN 1 ELSE 0 END) AS valid_transactions,
        SUM(CASE WHEN is_valid = 1 THEN net_revenue ELSE 0 END) AS total_net_revenue,
        SUM(gross_revenue) AS total_gross_revenue,
        SUM(discount_amount) AS total_discounts,
        COUNT(DISTINCT product) AS unique_products,
        COUNT(DISTINCT region) AS unique_regions,
        MIN(order_date) AS min_date,
        MAX(order_date) AS max_date
    FROM sales;
    """
    res = execute_safe_query(query, db_path=db_path)
    if res["success"] and res["rows"]:
        return res["rows"][0]
    return {}


if __name__ == "__main__":
    result = clean_and_load_data()
    print("Database ETL complete:", result)
    summary = get_database_summary()
    print("Summary:", summary)
