/* EvidenceAI · dashboard.js — renders overview charts and recent list. */
(function () {
  "use strict";

  function isDark() {
    return document.documentElement.getAttribute("data-bs-theme") === "dark";
  }

  function themeColor() {
    return isDark() ? "#8ab4f8" : "#4f46e5";
  }

  function gridColor() {
    return isDark() ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.06)";
  }

  function tickColor() {
    return isDark() ? "rgba(255,255,255,0.7)" : "rgba(0,0,0,0.65)";
  }

  function chartDefaults() {
    if (!window.Chart) return;
    Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
    Chart.defaults.color = tickColor();
  }

  function renderLine(canvasId, labels, series) {
    var canvas = document.getElementById(canvasId);
    if (!canvas || !window.Chart || !labels || labels.length === 0) return;
    var datasets = (series || []).map(function (s) {
      return {
        label: s.label,
        data: s.data,
        borderColor: s.color,
        backgroundColor: s.color + "22",
        borderWidth: 2,
        pointRadius: 2.5,
        tension: 0.3,
        fill: true,
      };
    });
    new Chart(canvas.getContext("2d"), {
      type: "line",
      data: { labels: labels, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { labels: { boxWidth: 10, usePointStyle: true } },
        },
        scales: {
          x: { grid: { color: gridColor() }, ticks: { maxTicksLimit: 8 } },
          y: { grid: { color: gridColor() }, beginAtZero: true, ticks: { precision: 0 } },
        },
      },
    });
  }

  function renderDoughnut(canvasId, labels, data) {
    var canvas = document.getElementById(canvasId);
    if (!canvas || !window.Chart || !labels || labels.length === 0) return;
    var palette = ["#16a34a", "#d97706", "#dc2626"];
    new Chart(canvas.getContext("2d"), {
      type: "doughnut",
      data: {
        labels: labels,
        datasets: [
          {
            data: data,
            backgroundColor: palette.slice(0, labels.length),
            borderWidth: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "65%",
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 10, usePointStyle: true } },
        },
      },
    });
  }

  function renderBar(canvasId, labels, data) {
    var canvas = document.getElementById(canvasId);
    if (!canvas || !window.Chart || !labels || labels.length === 0) return;
    new Chart(canvas.getContext("2d"), {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            data: data,
            backgroundColor: themeColor(),
            borderRadius: 4,
            maxBarThickness: 34,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false } },
          y: { grid: { color: gridColor() }, beginAtZero: true, ticks: { precision: 0 } },
        },
      },
    });
  }

  function setText(id, value) {
    var el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  async function load() {
    chartDefaults();
    var stats;
    try {
      stats = await api.get("/api/dashboard");
    } catch (err) {
      var el = document.getElementById("dashboardError");
      if (el) {
        el.textContent = err.message;
        el.classList.remove("d-none");
      }
      return;
    }

    var inv = stats.investigations || {};
    var recent = stats.recent_investigations || [];

    setText("statTotal", inv.total);
    setText("statComplete", inv.completed);
    setText("statPartial", inv.partial);
    setText("statDocs", inv.total_documents);
    setText("statSources", stats.sources);
    setText("statEvidence", stats.evidence);

    var rag = stats.rag || {};
    var graph = stats.graph || {};
    setText("statVectors", rag.vector_count);
    setText("statGraphNodes", graph.node_count);

    renderLine(
      "chartTrend",
      stats.trend_dates || [],
      [
        { label: "Investigations", data: stats.trend_counts || [], color: "#4f46e5" },
        { label: "Documents", data: stats.trend_document_counts || [], color: "#16a34a" },
      ]
    );

    renderDoughnut(
      "chartStatus",
      (stats.status_labels || []).map(function (s) { return s || "—"; }),
      stats.status_counts || []
    );

    renderBar("chartSources", stats.source_labels || [], stats.source_counts || []);

    var recentBody = document.getElementById("recentBody");
    if (recentBody) {
      var rows = "";
      (recent || []).forEach(function (r) {
        var badge =
          r.status === "completed"
            ? '<span class="badge rounded-pill text-bg-success">Completed</span>'
            : r.status === "failed"
            ? '<span class="badge rounded-pill text-bg-danger">Failed</span>'
            : '<span class="badge rounded-pill text-bg-warning">Partial</span>';
        var confidence =
          r.confidence
            ? '<span class="ai-mono small text-body-secondary">' + aiEscape(r.confidence) + "</span>"
            : '<span class="text-body-tertiary">—</span>';
        rows +=
          '<tr>' +
          '<td><a class="ai-table-link" href="/investigation/' + aiEscape(r.id) + '">' +
          aiEscape(r.query) + "</a></td>" +
          "<td>" + badge + "</td>" +
          "<td>" + confidence + "</td>" +
          '<td class="text-body-secondary">' + aiEscape(r.created_at) + "</td>" +
          "</tr>";
      });
      recentBody.innerHTML =
        rows ||
        '<tr><td colspan="4" class="text-center text-body-secondary py-4">' +
        "No investigations yet — start one to see it here.</td></tr>";
    }

    if ((inv.total || 0) > 0) {
      var cta = document.getElementById("noDataCta");
      if (cta) cta.remove();
    }
  }

  document.addEventListener("DOMContentLoaded", load);
})();
