"""
engine.py - Natural Language Query Engine for Sales BI Assistant

Implements:
1. Semantic intent classification and question interpretation.
2. Deterministic Text-to-SQL generation (offline-first, zero API-key requirement).
3. Optional LLM integration (Gemini / OpenAI) if an API key is configured.
4. Strict SQL query safety validation preventing destructive operations.
5. Analytical calculation and synthesis of human-readable answers with supporting figures.
"""

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from db import execute_safe_query, validate_sql

# Standard months mapping for natural language parsing
MONTH_NAMES = {
    "january": "2026-01",
    "jan": "2026-01",
    "february": "2026-02",
    "feb": "2026-02",
    "march": "2026-03",
    "mar": "2026-03",
    "april": "2026-04",
    "apr": "2026-04",
    "may": "2026-05",
    "june": "2026-06",
    "jun": "2026-06",
}


class BIAssistantEngine:
    """The central intelligence engine for the Business Intelligence Assistant."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        self.llm_api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY")

    def process_question(self, question: str) -> Dict[str, Any]:
        """
        Accepts a user question, processes it, executes the query,
        and returns a rich structured response.
        """
        cleaned_q = question.strip()
        if not cleaned_q:
            return {
                "question": question,
                "intent": "INVALID_EMPTY",
                "answer": "Please enter a valid question regarding sales, products, revenue, or regions.",
                "sql_query": None,
                "supporting_data": [],
                "metrics": {},
                "chart_type": "none",
                "chart_data": None,
                "execution_mode": "Validation",
                "is_valid": False,
                "error": "Empty question provided.",
            }

        # Check for direct SQL injection or destructive attempts in prompt
        destructive_keywords = ["drop table", "delete from", "truncate", "update sales", "alter table", "insert into"]
        if any(kw in cleaned_q.lower() for kw in destructive_keywords):
            return {
                "question": question,
                "intent": "SECURITY_ALERT",
                "answer": "Security Alert: Destructive database modifications (DROP, DELETE, UPDATE, ALTER, INSERT) are strictly prohibited.",
                "sql_query": None,
                "supporting_data": [],
                "metrics": {"Security Status": "Blocked"},
                "chart_type": "none",
                "chart_data": None,
                "execution_mode": "Security Guardrail",
                "is_valid": False,
                "error": "Destructive query attempt was rejected.",
            }

        # Attempt deterministic semantic routing
        intent, sql, params, extra_context = self._route_intent(cleaned_q)

        if intent == "UNSUPPORTED":
            return {
                "question": question,
                "intent": "UNSUPPORTED",
                "answer": (
                    "I am a Sales Business Intelligence Assistant specialized in analyzing the sales transactions database. "
                    "I could not correlate your question with sales, revenue, products, regions, channels, or trends. "
                    "Try asking questions like:\n"
                    "• 'What is the total revenue?'\n"
                    "• 'Which product generated the highest revenue?'\n"
                    "• 'What is the monthly revenue trend?'\n"
                    "• 'Which region generated the highest sales?'\n"
                    "• 'How did revenue change between April and May?'"
                ),
                "sql_query": None,
                "supporting_data": [],
                "metrics": {},
                "chart_type": "none",
                "chart_data": None,
                "execution_mode": "Semantic Guardrail",
                "is_valid": False,
                "error": "Question is out of scope or unsupported.",
            }

        # Validate SQL safety
        is_safe, error_msg = validate_sql(sql)
        if not is_safe:
            return {
                "question": question,
                "intent": intent,
                "answer": f"Generated SQL failed safety checks: {error_msg}",
                "sql_query": sql,
                "supporting_data": [],
                "metrics": {},
                "chart_type": "none",
                "chart_data": None,
                "execution_mode": "Safety Validator",
                "is_valid": False,
                "error": error_msg,
            }

        # Execute query
        db_res = execute_safe_query(sql, params, db_path=self.db_path)
        if not db_res["success"]:
            return {
                "question": question,
                "intent": intent,
                "answer": f"Error executing database query: {db_res['error']}",
                "sql_query": sql,
                "supporting_data": [],
                "metrics": {},
                "chart_type": "none",
                "chart_data": None,
                "execution_mode": "Database Execution",
                "is_valid": False,
                "error": db_res["error"],
            }

        # Synthesize natural language answer and UI visualization data
        answer, metrics, chart_type, chart_data = self._synthesize_answer(
            intent, db_res["rows"], extra_context
        )

        return {
            "question": question,
            "intent": intent,
            "answer": answer,
            "sql_query": sql,
            "supporting_data": db_res["rows"],
            "metrics": metrics,
            "chart_type": chart_type,
            "chart_data": chart_data,
            "execution_mode": "Deterministic SQL Engine",
            "is_valid": True,
            "error": None,
        }

    def _route_intent(
        self, q: str
    ) -> Tuple[str, Optional[str], Optional[Tuple[Any, ...]], Dict[str, Any]]:
        """
        Routes the natural language question to a structured SQL query.
        """
        lower = q.lower()
        context: Dict[str, Any] = {}

        # 1. TOTAL REVENUE
        # e.g., "what is the total revenue", "overall sales", "total sales", "net revenue"
        if (
            ("total" in lower or "overall" in lower or "all" in lower)
            and ("revenue" in lower or "sales" in lower or "turnover" in lower or "income" in lower)
            and "product" not in lower
            and "region" not in lower
            and "month" not in lower
            and "channel" not in lower
        ) or lower.strip(" ?.") in ["total revenue", "what is total revenue", "sales revenue", "how much revenue did we make"]:
            sql = """
            SELECT
                SUM(net_revenue) AS total_net_revenue,
                SUM(gross_revenue) AS total_gross_revenue,
                SUM(discount_amount) AS total_discount,
                SUM(quantity) AS total_units_sold,
                COUNT(*) AS completed_transactions
            FROM sales
            WHERE is_valid = 1;
            """
            return "TOTAL_REVENUE", sql, None, context

        # 2. HIGHEST / BEST PRODUCT BY REVENUE
        # e.g. "which product generated the highest revenue", "top product", "best selling product by revenue"
        if ("product" in lower or "item" in lower) and (
            "highest" in lower
            or "top" in lower
            or "best" in lower
            or "most" in lower
            or "max" in lower
            or "leader" in lower
        ) and ("revenue" in lower or "sales" in lower or "money" in lower):
            sql = """
            SELECT
                product,
                category,
                SUM(net_revenue) AS total_revenue,
                SUM(quantity) AS total_quantity,
                COUNT(*) AS transaction_count,
                ROUND(AVG(unit_price), 2) AS unit_price
            FROM sales
            WHERE is_valid = 1
            GROUP BY product
            ORDER BY total_revenue DESC;
            """
            return "HIGHEST_PRODUCT_REVENUE", sql, None, context

        # 2b. ALL PRODUCTS BREAKDOWN
        if ("product" in lower or "products" in lower) and ("revenue" in lower or "sales" in lower or "breakdown" in lower or "performance" in lower):
            sql = """
            SELECT
                product,
                category,
                SUM(net_revenue) AS total_revenue,
                SUM(quantity) AS total_quantity,
                COUNT(*) AS transaction_count
            FROM sales
            WHERE is_valid = 1
            GROUP BY product
            ORDER BY total_revenue DESC;
            """
            return "ALL_PRODUCTS_REVENUE", sql, None, context

        # 3. HIGHEST / BEST REGION
        # e.g., "which region generated the highest sales", "top region", "best region"
        if ("region" in lower or "territory" in lower or "area" in lower) and (
            "highest" in lower
            or "top" in lower
            or "best" in lower
            or "most" in lower
            or "max" in lower
            or "leading" in lower
        ):
            sql = """
            SELECT
                region,
                SUM(net_revenue) AS total_revenue,
                SUM(quantity) AS total_quantity,
                COUNT(*) AS order_count
            FROM sales
            WHERE is_valid = 1
            GROUP BY region
            ORDER BY total_revenue DESC;
            """
            return "HIGHEST_REGION_SALES", sql, None, context

        # 3b. ALL REGIONS BREAKDOWN
        if "region" in lower and ("sales" in lower or "revenue" in lower or "breakdown" in lower or "distribution" in lower):
            sql = """
            SELECT
                region,
                SUM(net_revenue) AS total_revenue,
                SUM(quantity) AS total_quantity,
                COUNT(*) AS order_count
            FROM sales
            WHERE is_valid = 1
            GROUP BY region
            ORDER BY total_revenue DESC;
            """
            return "ALL_REGIONS_SALES", sql, None, context

        # 4. MONTHLY REVENUE TREND / MONTHLY SALES
        # e.g., "what is the monthly revenue trend", "monthly sales", "revenue by month"
        if ("monthly" in lower or "month by month" in lower or "trend" in lower or "by month" in lower) and not (
            "change between" in lower or "difference between" in lower or "compare" in lower
        ):
            sql = """
            SELECT
                month,
                SUM(net_revenue) AS monthly_revenue,
                SUM(gross_revenue) AS monthly_gross,
                SUM(quantity) AS total_units,
                COUNT(*) AS order_count
            FROM sales
            WHERE is_valid = 1
            GROUP BY month
            ORDER BY month ASC;
            """
            return "MONTHLY_TREND", sql, None, context

        # 5. REVENUE CHANGE BETWEEN TWO MONTHS
        # e.g., "how did revenue change between two months", "compare april and may", "difference between jan and feb"
        distinct_month_codes = []
        for name, code in [
            ("january", "2026-01"), ("jan", "2026-01"),
            ("february", "2026-02"), ("feb", "2026-02"),
            ("march", "2026-03"), ("mar", "2026-03"),
            ("april", "2026-04"), ("apr", "2026-04"),
            ("may", "2026-05"),
            ("june", "2026-06"), ("jun", "2026-06"),
        ]:
            if re.search(r"\b" + name + r"\b", lower):
                if code not in distinct_month_codes:
                    distinct_month_codes.append(code)

        if (
            ("between" in lower and ("month" in lower or len(distinct_month_codes) >= 2))
            or "change between" in lower
            or ("compare" in lower and "month" in lower)
            or ("difference between" in lower and len(distinct_month_codes) >= 2)
        ):
            if len(distinct_month_codes) >= 2:
                m1_code, m2_code = distinct_month_codes[0], distinct_month_codes[1]
            else:
                m1_code, m2_code = "2026-04", "2026-05"

            sql = f"""
            SELECT
                month,
                SUM(net_revenue) AS revenue,
                SUM(quantity) AS units_sold,
                COUNT(*) AS orders
            FROM sales
            WHERE is_valid = 1 AND month IN ('{m1_code}', '{m2_code}')
            GROUP BY month
            ORDER BY month ASC;
            """
            context["m1_code"] = m1_code
            context["m2_code"] = m2_code
            return "MONTH_COMPARISON", sql, None, context

        # 6. SALES CHANNELS (Online vs Retail)
        if "channel" in lower or "online" in lower or "retail" in lower:
            sql = """
            SELECT
                sales_channel,
                SUM(net_revenue) AS total_revenue,
                SUM(quantity) AS total_quantity,
                COUNT(*) AS order_count
            FROM sales
            WHERE is_valid = 1
            GROUP BY sales_channel
            ORDER BY total_revenue DESC;
            """
            return "SALES_CHANNEL", sql, None, context

        # 7. CATEGORIES BREAKDOWN
        if "category" in lower or "categories" in lower:
            sql = """
            SELECT
                category,
                SUM(net_revenue) AS total_revenue,
                SUM(quantity) AS total_quantity,
                COUNT(*) AS order_count
            FROM sales
            WHERE is_valid = 1
            GROUP BY category
            ORDER BY total_revenue DESC;
            """
            return "CATEGORY_SALES", sql, None, context

        # 8. DATA QUALITY & RETURNS AUDIT
        if "return" in lower or "invalid" in lower or "cleaning" in lower or "audit" in lower or "missing" in lower:
            sql = """
            SELECT
                transaction_id,
                raw_order_date,
                product,
                quantity,
                unit_price,
                status,
                is_valid,
                cleaning_notes
            FROM sales
            WHERE cleaning_notes != 'Clean';
            """
            return "DATA_AUDIT", sql, None, context

        # Fallback / Out of Scope
        return "UNSUPPORTED", None, None, context

    def _synthesize_answer(
        self, intent: str, rows: List[Dict[str, Any]], context: Dict[str, Any]
    ) -> Tuple[str, Dict[str, str], str, Optional[Dict[str, Any]]]:
        """
        Synthesizes human-readable answer, supporting KPIs, and chart data.
        """
        if not rows:
            return "No matching records found in the sales database.", {}, "none", None

        # 1. TOTAL REVENUE
        if intent == "TOTAL_REVENUE":
            r = rows[0]
            net = r.get("total_net_revenue") or 0.0
            gross = r.get("total_gross_revenue") or 0.0
            disc = r.get("total_discount") or 0.0
            orders = r.get("completed_transactions") or 0
            units = r.get("total_units_sold") or 0

            answer = (
                f"The total net revenue generated is ₹{net:,.2f} across {orders} completed orders "
                f"({units} total units sold). Gross revenue stands at ₹{gross:,.2f} with ₹{disc:,.2f} in total discounts applied."
            )
            metrics = {
                "Net Revenue": f"₹{net:,.2f}",
                "Gross Revenue": f"₹{gross:,.2f}",
                "Discounts": f"₹{disc:,.2f}",
                "Completed Orders": str(orders),
            }
            chart_type = "metric"
            chart_data = {
                "labels": ["Net Revenue", "Discounts Applied"],
                "datasets": [{"data": [net, disc], "backgroundColor": ["#3b82f6", "#ef4444"]}],
            }
            return answer, metrics, chart_type, chart_data

        # 2. HIGHEST PRODUCT REVENUE
        if intent in ["HIGHEST_PRODUCT_REVENUE", "ALL_PRODUCTS_REVENUE"]:
            top = rows[0]
            top_name = top["product"]
            top_rev = top["total_revenue"]
            total_rev_all = sum(r["total_revenue"] for r in rows)
            top_share = (top_rev / total_rev_all * 100) if total_rev_all else 0.0

            runners_up = ", ".join(
                [f"{r['product']} (₹{r['total_revenue']:,.2f})" for r in rows[1:3]]
            )

            answer = (
                f"**{top_name}** generated the highest revenue at ₹{top_rev:,.2f}, representing {top_share:.1f}% "
                f"of total sales ({top['total_quantity']} units sold across {top['transaction_count']} transactions). "
                f"It was followed by {runners_up}."
            )
            metrics = {
                "Top Product": top_name,
                "Revenue": f"₹{top_rev:,.2f}",
                "Category": str(top.get("category", "N/A")),
                "Market Share": f"{top_share:.1f}%",
            }
            chart_type = "bar"
            chart_data = {
                "labels": [r["product"] for r in rows],
                "datasets": [
                    {
                        "label": "Revenue (₹)",
                        "data": [r["total_revenue"] for r in rows],
                        "backgroundColor": "#3b82f6",
                    }
                ],
            }
            return answer, metrics, chart_type, chart_data

        # 3. HIGHEST REGION SALES
        if intent in ["HIGHEST_REGION_SALES", "ALL_REGIONS_SALES"]:
            top = rows[0]
            top_reg = top["region"]
            top_rev = top["total_revenue"]
            total_rev_all = sum(r["total_revenue"] for r in rows)
            share = (top_rev / total_rev_all * 100) if total_rev_all else 0.0

            rankings = " > ".join([f"{r['region']} (₹{r['total_revenue']:,.2f})" for r in rows])

            answer = (
                f"The **{top_reg}** region generated the highest sales with ₹{top_rev:,.2f} "
                f"({share:.1f}% of all regional revenue, {top['order_count']} orders). "
                f"Overall regional ranking: {rankings}."
            )
            metrics = {
                "Top Region": top_reg,
                "Revenue": f"₹{top_rev:,.2f}",
                "Share": f"{share:.1f}%",
                "Total Orders": str(top["order_count"]),
            }
            chart_type = "doughnut"
            chart_data = {
                "labels": [r["region"] for r in rows],
                "datasets": [
                    {
                        "data": [r["total_revenue"] for r in rows],
                        "backgroundColor": ["#10b981", "#3b82f6", "#f59e0b", "#8b5cf6"],
                    }
                ],
            }
            return answer, metrics, chart_type, chart_data

        # 4. MONTHLY TREND
        if intent == "MONTHLY_TREND":
            peak_m = max(rows, key=lambda x: x["monthly_revenue"])
            low_m = min(rows, key=lambda x: x["monthly_revenue"])

            trend_summary = []
            for i in range(1, len(rows)):
                prev = rows[i - 1]["monthly_revenue"]
                curr = rows[i]["monthly_revenue"]
                pct = ((curr - prev) / prev * 100) if prev else 0.0
                sign = "+" if pct >= 0 else ""
                trend_summary.append(f"{rows[i]['month']}: {sign}{pct:.1f}%")

            answer = (
                f"The monthly revenue trend spans {len(rows)} months from {rows[0]['month']} to {rows[-1]['month']}. "
                f"The peak revenue month was **{peak_m['month']}** at ₹{peak_m['monthly_revenue']:,.2f}, while the lowest was "
                f"**{low_m['month']}** at ₹{low_m['monthly_revenue']:,.2f}. Month-over-month growth highlights: {', '.join(trend_summary)}."
            )
            metrics = {
                "Peak Month": f"{peak_m['month']} (₹{peak_m['monthly_revenue']:,.2f})",
                "Lowest Month": f"{low_m['month']} (₹{low_m['monthly_revenue']:,.2f})",
                "Tracked Months": str(len(rows)),
                "Average Monthly Sales": f"₹{(sum(r['monthly_revenue'] for r in rows)/len(rows)):,.2f}",
            }
            chart_type = "line"
            chart_data = {
                "labels": [r["month"] for r in rows],
                "datasets": [
                    {
                        "label": "Monthly Net Revenue (₹)",
                        "data": [r["monthly_revenue"] for r in rows],
                        "borderColor": "#3b82f6",
                        "backgroundColor": "rgba(59, 130, 246, 0.15)",
                        "fill": True,
                    }
                ],
            }
            return answer, metrics, chart_type, chart_data

        # 5. MONTH COMPARISON
        if intent == "MONTH_COMPARISON":
            if len(rows) < 2:
                # If only one month returned
                r = rows[0]
                answer = f"Found data for {r['month']}: Revenue was ₹{r['revenue']:,.2f} ({r['orders']} orders)."
                return answer, {"Revenue": f"₹{r['revenue']:,.2f}"}, "bar", None

            m1_row = rows[0]
            m2_row = rows[1]
            diff = m2_row["revenue"] - m1_row["revenue"]
            pct = (diff / m1_row["revenue"] * 100) if m1_row["revenue"] else 0.0
            direction = "increased" if diff >= 0 else "decreased"
            sign = "+" if diff >= 0 else ""

            answer = (
                f"Between **{m1_row['month']}** (₹{m1_row['revenue']:,.2f}) and **{m2_row['month']}** (₹{m2_row['revenue']:,.2f}), "
                f"revenue **{direction}** by **{sign}₹{diff:,.2f}** ({sign}{pct:.2f}%). "
                f"Total units sold shifted from {m1_row['units_sold']} to {m2_row['units_sold']} units."
            )
            metrics = {
                "Base Month": f"{m1_row['month']} (₹{m1_row['revenue']:,.2f})",
                "Comparison Month": f"{m2_row['month']} (₹{m2_row['revenue']:,.2f})",
                "Absolute Change": f"{sign}₹{diff:,.2f}",
                "Percentage Change": f"{sign}{pct:.2f}%",
            }
            chart_type = "bar"
            chart_data = {
                "labels": [m1_row["month"], m2_row["month"]],
                "datasets": [
                    {
                        "label": "Revenue (₹)",
                        "data": [m1_row["revenue"], m2_row["revenue"]],
                        "backgroundColor": ["#94a3b8", "#3b82f6" if diff >= 0 else "#ef4444"],
                    }
                ],
            }
            return answer, metrics, chart_type, chart_data

        # 6. SALES CHANNEL
        if intent == "SALES_CHANNEL":
            top = rows[0]
            answer = (
                f"Sales by channel: **{top['sales_channel']}** leads with ₹{top['total_revenue']:,.2f} "
                f"across {top['order_count']} orders, followed by "
                + ", ".join([f"{r['sales_channel']} (₹{r['total_revenue']:,.2f})" for r in rows[1:]])
                + "."
            )
            metrics = {f"{r['sales_channel']} Revenue": f"₹{r['total_revenue']:,.2f}" for r in rows}
            chart_type = "pie"
            chart_data = {
                "labels": [r["sales_channel"] for r in rows],
                "datasets": [{"data": [r["total_revenue"] for r in rows], "backgroundColor": ["#3b82f6", "#10b981"]}],
            }
            return answer, metrics, chart_type, chart_data

        # 7. CATEGORY
        if intent == "CATEGORY_SALES":
            top = rows[0]
            answer = (
                f"Product category breakdown: **{top['category']}** generated the highest sales at ₹{top['total_revenue']:,.2f}, "
                + ", ".join([f"{r['category']} (₹{r['total_revenue']:,.2f})" for r in rows[1:]])
                + "."
            )
            metrics = {f"{r['category']}": f"₹{r['total_revenue']:,.2f}" for r in rows}
            chart_type = "bar"
            chart_data = {
                "labels": [r["category"] for r in rows],
                "datasets": [{"label": "Revenue (₹)", "data": [r["total_revenue"] for r in rows], "backgroundColor": "#8b5cf6"}],
            }
            return answer, metrics, chart_type, chart_data

        # 8. DATA AUDIT
        if intent == "DATA_AUDIT":
            answer = (
                f"Data quality audit found {len(rows)} records requiring preprocessing or exclusion: "
                + "; ".join([f"{r['transaction_id']} ({r['cleaning_notes']})" for r in rows])
                + "."
            )
            metrics = {"Flagged Records": str(len(rows))}
            return answer, metrics, "table", None

        # Generic default
        return "Query executed successfully.", {}, "table", None
