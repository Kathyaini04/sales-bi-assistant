// Client-side interactions and visualizations for Sales BI Assistant
document.addEventListener("DOMContentLoaded", () => {
    const questionInput = document.getElementById("question-input");
    const askBtn = document.getElementById("ask-btn");
    const emptyState = document.getElementById("empty-state");
    const loadingState = document.getElementById("loading-state");
    const resultCard = document.getElementById("result-card");
    const resultIntent = document.getElementById("result-intent");
    const resultAnswer = document.getElementById("result-answer");
    const metricsRow = document.getElementById("metrics-row");
    const chartWrapper = document.getElementById("chart-wrapper");
    const sqlCodeDisplay = document.getElementById("sql-code-display");
    const sqlToggleBtn = document.getElementById("sql-toggle-btn");
    const sqlContent = document.getElementById("sql-content");
    const tableHeadRow = document.getElementById("table-head-row");
    const tableBody = document.getElementById("table-body");
    const viewDataBtn = document.getElementById("view-data-btn");
    const auditModal = document.getElementById("audit-modal");
    const closeModalBtn = document.getElementById("close-modal-btn");
    const auditTableBody = document.getElementById("audit-table-body");

    let currentChart = null;

    // Load initial stats
    fetchStats();

    // Toggle SQL accordion
    sqlToggleBtn.addEventListener("click", () => {
        sqlContent.classList.toggle("hidden");
    });

    // Handle submit
    askBtn.addEventListener("click", () => {
        submitQuestion(questionInput.value);
    });

    questionInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            submitQuestion(questionInput.value);
        }
    });

    // Quick Prompt Chips
    document.querySelectorAll(".chip-btn").forEach((chip) => {
        chip.addEventListener("click", () => {
            const promptText = chip.getAttribute("data-question");
            questionInput.value = promptText;
            submitQuestion(promptText);
        });
    });

    // View Data Audit Modal
    viewDataBtn.addEventListener("click", () => {
        loadDataAudit();
        auditModal.classList.remove("hidden");
    });

    closeModalBtn.addEventListener("click", () => {
        auditModal.classList.add("hidden");
    });

    window.addEventListener("click", (e) => {
        if (e.target === auditModal) {
            auditModal.classList.add("hidden");
        }
    });

    async function fetchStats() {
        try {
            const res = await fetch("/api/stats");
            if (res.ok) {
                const data = await res.json();
                if (data.total_net_revenue) {
                    document.getElementById("kpi-net-rev").innerText =
                        "₹" + Number(data.total_net_revenue).toLocaleString("en-IN");
                }
            }
        } catch (err) {
            console.error("Could not fetch KPI stats:", err);
        }
    }

    async function submitQuestion(question) {
        const q = (question || "").trim();
        if (!q) return;

        // UI state transitions
        emptyState.classList.add("hidden");
        resultCard.classList.add("hidden");
        loadingState.classList.remove("hidden");

        try {
            const response = await fetch("/api/query", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ question: q }),
            });

            const data = await response.json();
            renderResponse(data);
        } catch (error) {
            renderResponse({
                intent: "NETWORK_ERROR",
                answer: "Failed to connect to the backend server. Please check your network and try again.",
                sql_query: null,
                supporting_data: [],
                metrics: {},
                chart_type: "none",
            });
        } finally {
            loadingState.classList.add("hidden");
            resultCard.classList.remove("hidden");
        }
    }

    function renderResponse(data) {
        resultIntent.innerText = data.intent || "QUERY_RESULT";
        resultAnswer.innerHTML = formatMarkdown(data.answer || "");

        // Render metrics pills
        metricsRow.innerHTML = "";
        if (data.metrics && Object.keys(data.metrics).length > 0) {
            Object.entries(data.metrics).forEach(([key, val]) => {
                const pill = document.createElement("div");
                pill.className = "metric-pill";
                pill.innerHTML = `<span class="label">${escapeHtml(key)}</span><span class="val">${escapeHtml(String(val))}</span>`;
                metricsRow.appendChild(pill);
            });
        }

        // Render SQL Query
        if (data.sql_query) {
            sqlCodeDisplay.innerText = data.sql_query.trim();
            sqlToggleBtn.parentElement.classList.remove("hidden");
        } else {
            sqlCodeDisplay.innerText = "-- No database query was executed for this prompt";
            sqlToggleBtn.parentElement.classList.add("hidden");
        }

        // Render Chart
        renderChart(data.chart_type, data.chart_data);

        // Render Supporting Table
        renderTable(data.supporting_data || []);
    }

    function renderChart(type, chartData) {
        if (currentChart) {
            currentChart.destroy();
            currentChart = null;
        }

        if (!chartData || type === "none" || type === "metric" || !chartData.datasets) {
            chartWrapper.classList.add("hidden");
            return;
        }

        chartWrapper.classList.remove("hidden");
        const ctx = document.getElementById("analytics-chart").getContext("2d");

        const chartConfigType = type === "doughnut" ? "doughnut" : (type === "line" ? "line" : "bar");

        currentChart = new Chart(ctx, {
            type: chartConfigType,
            data: chartData,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: { color: "#94a3b8", font: { family: "Plus Jakarta Sans" } },
                    },
                },
                scales: chartConfigType === "doughnut" ? {} : {
                    x: {
                        ticks: { color: "#94a3b8" },
                        grid: { color: "rgba(255,255,255,0.05)" },
                    },
                    y: {
                        ticks: {
                            color: "#94a3b8",
                            callback: (val) => "₹" + Number(val).toLocaleString("en-IN"),
                        },
                        grid: { color: "rgba(255,255,255,0.05)" },
                    },
                },
            },
        });
    }

    function renderTable(rows) {
        tableHeadRow.innerHTML = "";
        tableBody.innerHTML = "";

        if (!rows || rows.length === 0) {
            tableHeadRow.innerHTML = "<th>Result</th>";
            tableBody.innerHTML = "<tr><td colspan='1'>No tabular rows returned.</td></tr>";
            return;
        }

        const headers = Object.keys(rows[0]);
        headers.forEach((h) => {
            const th = document.createElement("th");
            th.innerText = h.replace(/_/g, " ");
            tableHeadRow.appendChild(th);
        });

        rows.forEach((r) => {
            const tr = document.createElement("tr");
            headers.forEach((h) => {
                const td = document.createElement("td");
                let val = r[h];
                if (typeof val === "number") {
                    val = h.includes("revenue") || h.includes("price") || h.includes("discount")
                        ? "₹" + Number(val).toLocaleString("en-IN", { minimumFractionDigits: 2 })
                        : val.toLocaleString();
                }
                td.innerText = val !== null && val !== undefined ? val : "-";
                tr.appendChild(td);
            });
            tableBody.appendChild(tr);
        });
    }

    async function loadDataAudit() {
        if (auditTableBody.children.length > 0) return; // already loaded

        try {
            const res = await fetch("/api/data");
            const result = await res.json();
            const rows = result.rows || [];

            auditTableBody.innerHTML = "";
            rows.forEach((r) => {
                const tr = document.createElement("tr");
                const isFlagged = r.cleaning_notes && r.cleaning_notes !== "Clean";
                if (isFlagged) {
                    tr.style.backgroundColor = "rgba(245, 158, 11, 0.08)";
                }

                tr.innerHTML = `
                    <td><strong>${escapeHtml(r.transaction_id)}</strong></td>
                    <td>${escapeHtml(r.raw_order_date)}</td>
                    <td>${escapeHtml(r.product)}</td>
                    <td>${escapeHtml(r.category)}</td>
                    <td>${escapeHtml(r.region)}</td>
                    <td>${r.quantity}</td>
                    <td>₹${Number(r.unit_price).toFixed(2)}</td>
                    <td>₹${Number(r.discount_amount).toFixed(2)}</td>
                    <td><strong>₹${Number(r.net_revenue).toLocaleString("en-IN", { minimumFractionDigits: 2 })}</strong></td>
                    <td><span class="badge ${r.status === 'Completed' ? 'badge-ok' : 'badge-warn'}">${escapeHtml(r.status)}</span></td>
                    <td><small style="color:${isFlagged ? '#facc15' : '#94a3b8'}">${escapeHtml(r.cleaning_notes || 'Clean')}</small></td>
                `;
                auditTableBody.appendChild(tr);
            });
        } catch (err) {
            auditTableBody.innerHTML = `<tr><td colspan="11">Error loading audit data: ${err}</td></tr>`;
        }
    }

    function formatMarkdown(text) {
        return text
            .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
            .replace(/\n/g, "<br>");
    }

    function escapeHtml(text) {
        if (!text) return "";
        return String(text)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
    }
});
