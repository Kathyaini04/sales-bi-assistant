# AI Usage & Engineering Reflection Report

## 1. Candidate Information
- **Candidate Name:** Kathyaini
- **Role Applied For:** Graduate Engineer Trainee (GET) - AI / Backend Development
- **Project Name:** AI-Assisted Sales Business Intelligence Assistant (`sales-bi-assistant`)
- **Evaluation Date:** October 25, 2026

---

## 2. Which AI Tools You Used
During the architecture, implementation, and testing of this application, the following AI tools and platforms were utilized:
- **Google Antigravity (Advanced Agentic AI Assistant with Gemini 3.8 Flash):** Used as the primary pair-programming and reasoning agent for rapid prototyping, architecture brainstorming, test-case authoring, and automated code review.
- **Python AST & Regular Expression Guardrails:** Implemented as a deterministic security filter to inspect and validate generated SQL queries against destructive SQL syntax (DROP, DELETE, UPDATE, INSERT, ALTER).
- **Chart.js CDN (Interactive Visualization Engine):** Synthesized alongside dynamic JSON datasets to render clean visual feedback for business metrics.

---

## 3. How You Used AI During Development

### A. Architectural Ideation & System Design
I used the AI assistant to formulate a **two-tiered query architecture**:
1. **Tier 1 (AI / LLM Natural Language Understanding):** Translates user questions into analytical SQL queries.
2. **Tier 2 (Deterministic Semantic Fallback Engine):** Ensures 100% test coverage and out-of-the-box offline functionality with zero external API key dependencies, guaranteeing reliable answers for the core 5 business questions and their variants.

### B. Data Cleaning Strategy & Anomaly Detection
Through automated data profiling with the AI assistant, three key anomalies were detected in `sales_data.csv`:
1. **`TXN0033` (Monitor):** Had status `'Returned'`. We flagged this record (`is_valid = 0`), excluding it from net revenue while preserving it in the transaction ledger for return-rate audits.
2. **`TXN0034` (Keyboard):** Had `Quantity = 0`. Marked `is_valid = 0` to prevent zero-sale transactions from distorting order volume calculations.
3. **`TXN0051` (Laptop Stand):** Had a missing `Unit_price`. The assistant identified other `Laptop Stand` orders in the dataset to construct a catalog price lookup (`₹1,200.00`) and successfully imputed the price, logging the transformation in the audit column `cleaning_notes`.

### C. Test-Driven Development (TDD)
I tasked the AI with constructing a comprehensive 15-test automated test suite in `pytest` to validate:
- Accuracy of all five required business analytics questions.
- Data anomaly handling and imputation logic.
- SQL injection rejection and destructive query blocking.
- Out-of-scope and empty query handling.
- Flask REST API endpoint status codes and JSON payloads.

---

## 4. Problems Encountered During Development

### Problem 1: Windows Console Character Encoding (`cp1252` vs `UnicodeEncodeError`)
- **Symptom:** When running unit scripts directly in PowerShell, printing the Indian Rupee symbol `₹` (`\u20b9`) threw `UnicodeEncodeError: 'charmap' codec can't encode character '\u20b9'`.
- **Root Cause:** Standard Windows consoles default to OEM code pages (such as `cp1252`) which do not contain the Rupee symbol.
- **Solution:** Enforced UTF-8 output encoding across CLI scripts (`PYTHONIOENCODING=utf-8`) and serialized web responses using clean UTF-8 JSON payloads with `toLocaleString("en-IN")` on the client side.

### Problem 2: Overlapping Month Token Extraction in Natural Language Queries
- **Symptom:** When parsing the comparison question *"How did revenue change between April and May?"*, the substring matching logic matched both `"april"` and `"apr"` to `2026-04`, resulting in duplicate month codes (`['2026-04', '2026-04']`).
- **Root Cause:** The parser checked for substring occurrences without word boundaries or month-code deduplication.
- **Solution:** Upgraded the regex parser to use regex word boundaries (`\b` + month + `\b`) and distinct set deduplication, cleanly resolving `2026-04` and `2026-05`.

### Problem 3: Preventing Destructive SQL Operations (Text-to-SQL Guardrails)
- **Symptom:** Text-to-SQL engines risk executing destructive operations if prompted maliciously (e.g., *"DROP TABLE sales;"* or prompt injection).
- **Root Cause:** Raw database connections accept any valid SQL unless restricted.
- **Solution:** Implemented `validate_sql()` which strictly enforces that incoming queries must begin with `SELECT` or `WITH`, prohibits multi-statement semicolons, and blocks all mutation verbs (`DROP`, `DELETE`, `UPDATE`, `ALTER`, `TRUNCATE`, `INSERT`, `REPLACE`).

---

## 5. How You Debugged Them
1. **Interactive Shell Execution:** Wrote dedicated scratch scripts (`analyze_sales.py`) to verify data integrity, compute ground truth figures (Total Net Revenue: `₹1,445,200.00`), and benchmark against database query outputs.
2. **Automated Pytest Suite:** Continuously ran `pytest -q` after every code revision, ensuring zero regression across edge cases and core questions.
3. **Payload Inspection:** Validated Flask API responses and HTTP status codes using Postman / curl equivalents and Flask test client fixtures.

---

## 6. What You Would Improve With Another Day of Work
If given an additional working day, I would implement the following enhancements:
1. **Full RAG / Hybrid Semantic Search:** Integrate a local vector embedding model (e.g., `sentence-transformers/all-MiniLM-L6-v2` or Google Gemini Embeddings) with SQLite VSS (Vector Similarity Search) for hybrid semantic retrieval of vague product descriptions.
2. **Multi-Turn Conversational Memory:** Add session context and conversational state to allow follow-up questions (e.g., *"Which region was top?"* followed by *"What about in March?"*).
3. **Database Migration to PostgreSQL with Data Connect:** Move from SQLite to an enterprise relational database with automated schema migrations and read-only database user permissions at the database driver level.
4. **Enhanced Data Export & PDF Reporting:** Provide one-click CSV and PDF report generation for executive stakeholders directly from the UI.
5. **Continuous Integration (CI):** Add a GitHub Actions workflow (`.github/workflows/test.yml`) to automatically run `pytest` and linter checks on every pull request.
