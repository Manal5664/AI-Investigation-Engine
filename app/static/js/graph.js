/* EvidenceAI · graph.js — interactive investigation graph with Cytoscape.js. */
(function () {
  "use strict";

  var NODE_COLORS = {
    investigation: "#4f46e5",
    claim: "#d97706",
    source: "#0284c7",
    evidence: "#16a34a",
    person: "#7c3aed",
    organization: "#0891b2",
    location: "#b45309",
    event: "#dc2626",
    topic: "#6b7280",
  };

  function nodeColor(type) {
    return NODE_COLORS[type] || "#6b7280";
  }

  function isDark() {
    return document.documentElement.getAttribute("data-bs-theme") === "dark";
  }

  function showMessage(message) {
    var msg = document.getElementById("graphMessage");
    if (msg) {
      msg.textContent = message;
      msg.classList.remove("d-none");
    }
  }

  function hideMessage() {
    var msg = document.getElementById("graphMessage");
    if (msg) msg.classList.add("d-none");
  }

  var cy = null;
  var currentData = { nodes: [], edges: [] };
  var currentFilter = "";
  var currentTypeFilter = "";

  function showEmptyState(message) {
    var container = document.getElementById("graphCanvas");
    if (container) {
      container.innerHTML =
        '<div class="ai-graph-empty">' +
        '<i class="bi bi-diagram-3" aria-hidden="true"></i>' +
        "<span>" + aiEscape(message) + "</span>" +
        "</div>";
    }
  }

  function buildElements(data) {
    var elements = [];
    (data.nodes || []).forEach(function (node) {
      elements.push({
        data: {
          id: node.id,
          label: node.label || node.id,
          color: nodeColor(node.node_type),
          kind: node.node_type || "unknown",
          description: node.description || "",
          investigation_id: node.investigation_id || null,
        },
      });
    });
    (data.edges || []).forEach(function (edge) {
      elements.push({
        data: {
          id: edge.id,
          source: edge.source,
          target: edge.target,
          label: edge.relation_type || "related to",
          weight: edge.confidence != null ? edge.confidence : 1,
          investigation_id: edge.investigation_id || null,
        },
      });
    });
    return elements;
  }

  function renderGraph(data) {
    var container = document.getElementById("graphCanvas");
    if (!container) return;
    container.innerHTML = "";
    if (!window.cytoscape) {
      showMessage("The graph library could not be loaded.");
      return;
    }

    var elements = buildElements(data);
    var nodeIds = new Set();
    elements.forEach(function (el) {
      if (el.data && !el.data.source) nodeIds.add(el.data.id);
    });
    var filteredElements = elements.filter(function (el) {
      if (el.data && el.data.source) {
        return nodeIds.has(el.data.source) && nodeIds.has(el.data.target);
      }
      return true;
    });

    if (nodeIds.size === 0) {
      showMessage("No graph data yet — run an investigation with graph extraction to populate the graph.");
      showEmptyState(
        "No graph data yet — run an investigation with graph extraction to populate the graph."
      );
      return;
    }
    hideMessage();

    var isDarkTheme = isDark();
    var fg = isDarkTheme ? "#e8eaed" : "#202124";
    var edgeColor = isDarkTheme ? "rgba(255,255,255,0.3)" : "rgba(32,33,36,0.3)";
    var bg = isDarkTheme ? "rgba(232,234,237,0.9)" : "rgba(255,255,255,0.9)";

    cy = cytoscape({
      container: container,
      elements: filteredElements,
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            label: "data(label)",
            color: fg,
            "font-size": 10,
            "text-valign": "bottom",
            "text-margin-y": 6,
            width: 24,
            height: 24,
            "overlay-opacity": 0,
          },
        },
        {
          selector: "edge",
          style: {
            width: "mapData(weight, 0, 1, 0.8, 3)",
            "line-color": edgeColor,
            "curve-style": "bezier",
            "target-arrow-shape": "triangle",
            "target-arrow-color": edgeColor,
            "arrow-scale": 0.7,
            label: "data(label)",
            "font-size": 8,
            color: fg,
            "text-rotation": "autorotate",
            "text-background-color": bg,
            "text-background-opacity": 0.85,
            "text-background-padding": "2px",
            "overlay-opacity": 0,
          },
        },
        {
          selector: "node:selected",
          style: { "border-width": 2, "border-color": "#4f46e5" },
        },
        {
          selector: "edge:selected",
          style: { "line-color": "#4f46e5", "target-arrow-color": "#4f46e5" },
        },
      ],
      layout: { name: "cose", animate: false, padding: 30, nodeRepulsion: 9000 },
      minZoom: 0.2,
      maxZoom: 2.5,
    });

    cy.on("tap", "node", function (event) {
      var node = event.target.data();
      var details = document.getElementById("graphDetails");
      if (!details) return;
      details.innerHTML =
        '<div class="d-flex align-items-center gap-2 mb-2 flex-wrap">' +
        '<span class="legend-dot" style="background:' + node.color + '"></span>' +
        '<span class="fw-semibold">' + aiEscape(node.label) + "</span>" +
        '<span class="ai-mono text-uppercase small text-body-secondary">' +
        aiEscape(node.kind) +
        "</span></div>" +
        (node.description
          ? '<p class="small text-body-secondary mb-2">' + aiEscape(node.description) + "</p>"
          : "") +
        '<dl class="ai-graph-detail mb-0">' +
        "<dt>Node</dt><dd>" + aiEscape(node.id) + "</dd>" +
        "<dt>Connections</dt><dd>" + event.target.connectedEdges().length + " edge(s)</dd>" +
        (node.investigation_id
          ? "<dt>Investigation</dt><dd><a href=\"/investigation/" +
            aiEscape(node.investigation_id) +
            "\">" +
            aiEscape(node.investigation_id) +
            "</a></dd>"
          : "") +
        "</dl>";
    });

    cy.on("tap", function (event) {
      if (event.target === cy) {
        var details = document.getElementById("graphDetails");
        if (details) {
          details.innerHTML =
            '<div class="text-body-secondary small">Click a node to inspect an entity.</div>';
        }
      }
    });
  }

  function loadGraph() {
    var container = document.getElementById("graphCanvas");
    if (container) {
      container.innerHTML =
        '<div class="d-flex align-items-center justify-content-center h-100 text-body-secondary">' +
        '<div class="spinner-border text-primary me-2"></div> Loading graph…</div>';
    }
    api
      .get("/api/graph")
      .then(function (data) {
        currentData = data;
        var stats = data.stats || {};
        var statsEl = document.getElementById("graphStats");
        if (statsEl) {
          statsEl.textContent =
            "· " + stats.node_count + " nodes · " + stats.edge_count + " edges" +
            (stats.investigation_count ? " · " + stats.investigation_count + " investigations" : "");
        }
        applyFilter();
      })
      .catch(function (err) {
        showMessage(err.message);
        var container2 = document.getElementById("graphCanvas");
        if (container2) container2.innerHTML = "";
      });
  }

  function applyFilter() {
    var data = { nodes: [], edges: [] };
    var sourceNodes = currentData.nodes || [];
    if (currentFilter) {
      sourceNodes = sourceNodes.filter(function (n) {
        return n.investigation_id === currentFilter;
      });
    }
    if (currentTypeFilter) {
      sourceNodes = sourceNodes.filter(function (n) {
        return (n.node_type || "unknown") === currentTypeFilter;
      });
    }
    data.nodes = sourceNodes;
    var allowed = new Set(data.nodes.map(function (n) { return n.id; }));
    data.edges = (currentData.edges || []).filter(function (e) {
      return allowed.has(e.source) && allowed.has(e.target);
    });
    renderGraph(data);
  }

  function populateSelector() {
    var select = document.getElementById("investigationSelect");
    var typeFilter = document.getElementById("graphTypeFilter");
    if (select) {
      api
        .get("/api/v1/investigations?limit=100")
        .then(function (data) {
          var items = data.investigations || [];
          select.innerHTML =
            '<option value="">All investigations</option>' +
            items
              .map(function (r) {
                return '<option value="' + aiEscape(r.id) + '">' + aiEscape(r.query) + "</option>";
              })
              .join("");
        })
        .catch(function () {
          select.innerHTML = '<option value="">All investigations</option>';
        });

      select.addEventListener("change", function () {
        currentFilter = select.value;
        applyFilter();
      });
    }
    if (typeFilter) {
      typeFilter.addEventListener("change", function () {
        currentTypeFilter = typeFilter.value;
        applyFilter();
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    populateSelector();
    loadGraph();
  });
})();
