/* EvidenceAI · result_graph.js — per-investigation subgraph on the result page. */
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

  function showEmpty(message) {
    var container = document.getElementById("resultGraphCanvas");
    if (!container) return;
    container.innerHTML =
      '<div class="ai-graph-empty">' +
      '<i class="bi bi-diagram-3" aria-hidden="true"></i>' +
      "<span>" + aiEscape(message) + "</span>" +
      "</div>";
  }

  function showNodeInfo(node, edgeCount) {
    var host = document.getElementById("resultGraphDetails");
    if (!host) return;
    var inner = host.querySelector(".card");
    if (inner) {
      inner.innerHTML =
        '<div class="d-flex align-items-center gap-2 mb-2 flex-wrap">' +
        '<span class="legend-dot" style="background:' + node.color + '"></span>' +
        '<span class="fw-semibold">' + aiEscape(node.label) + "</span>" +
        '<span class="ai-mono text-uppercase small text-body-secondary">' +
        aiEscape(node.kind) +
        "</span></div>" +
        '<dl class="ai-graph-detail mb-0">' +
        "<dt>Node</dt><dd>" + aiEscape(node.id) + "</dd>" +
        "<dt>Connections</dt><dd>" + edgeCount + " edge(s)</dd>" +
        "</dl>";
    }
    host.classList.remove("d-none");
  }

  function hideNodeInfo() {
    var host = document.getElementById("resultGraphDetails");
    if (host) host.classList.add("d-none");
  }

  function render(data) {
    var container = document.getElementById("resultGraphCanvas");
    if (!container) return;
    container.innerHTML = "";
    if (!window.cytoscape) {
      showEmpty("The graph library could not be loaded.");
      return;
    }

    var elements = [];
    (data.nodes || []).forEach(function (node) {
      elements.push({
        data: {
          id: node.id,
          label: node.label || node.id,
          color: nodeColor(node.node_type),
          kind: node.node_type || "unknown",
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
        },
      });
    });

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
      showEmpty("No graph entities were extracted for this investigation.");
      return;
    }

    var dark = isDark();
    var fg = dark ? "#e8eaed" : "#202124";
    var edgeColor = dark ? "rgba(255,255,255,0.3)" : "rgba(32,33,36,0.3)";
    var bg = dark ? "rgba(232,234,237,0.9)" : "rgba(255,255,255,0.9)";

    var cy = cytoscape({
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
      showNodeInfo(node, event.target.connectedEdges().length);
    });

    cy.on("tap", function (event) {
      if (event.target === cy) hideNodeInfo();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var container = document.getElementById("resultGraphCanvas");
    if (!container) return;
    var caseId = document.body.getAttribute("data-case-id");
    container.innerHTML =
      '<div class="d-flex align-items-center justify-content-center h-100 text-body-secondary">' +
      '<div class="spinner-border text-primary me-2"></div> Loading graph…</div>';

    api
      .get("/api/graph")
      .then(function (data) {
        var nodes = (data.nodes || []).filter(function (n) {
          return caseId && n.investigation_id === caseId;
        });
        var allowed = new Set(nodes.map(function (n) { return n.id; }));
        var edges = (data.edges || []).filter(function (e) {
          return allowed.has(e.source) && allowed.has(e.target);
        });
        render({ nodes: nodes, edges: edges });
      })
      .catch(function (err) {
        showEmpty(err.message);
      });
  });
})();
