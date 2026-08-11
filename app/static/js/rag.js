/* EvidenceAI · rag.js — vector search across the document base. */
(function () {
  "use strict";

  function loadStats() {
    api
      .get("/api/v1/rag/stats")
      .then(function (stats) {
        var el = document.getElementById("ragStats");
        if (!el) return;
        var dim = stats.vector_dimension != null ? " · " + stats.vector_dimension + " dims" : "";
        el.textContent =
          stats.vector_count + " vectors · " + stats.source_count + " sources" + dim;
      })
      .catch(function () { /* stats are informational */ });
  }

  function doSearch() {
    var container = document.getElementById("searchResults");
    var query = (document.getElementById("ragQuery") || {}).value || "";
    var status = document.getElementById("ragStatus");
    if (!container) return;
    if (!query.trim()) {
      container.innerHTML =
        '<div class="text-center text-body-secondary py-5">Enter a question above to search the evidence base.</div>';
      return;
    }

    container.innerHTML =
      '<div class="text-center py-5"><div class="spinner-border text-primary" role="status"></div>' +
      '<div class="text-body-secondary small mt-2">Searching document vectors…</div></div>';
    if (status) status.textContent = "";

    api
      .post("/api/v1/rag/search", { query: query.trim(), top_k: 10 }, 120000)
      .then(function (results) {
        var items = Array.isArray(results) ? results : (results.results || []);
        if (items.length === 0) {
          container.innerHTML =
            '<div class="text-center text-body-secondary py-5">No relevant passages found.</div>';
          if (status) status.textContent = "0 results";
          return;
        }
        if (status) status.textContent = items.length + " results";
        container.innerHTML = items
          .map(function (r) {
            var title = (r.metadata && r.metadata.title) || r.source_id || "Document";
            var location =
              (r.metadata && (r.metadata.section || r.metadata.location)) || null;
            var percent = Math.round(Math.max(0, Math.min(1, r.similarity_score)) * 100);
            return (
              '<div class="card ai-card ai-rag-result mb-3">' +
              '<div class="d-flex justify-content-between align-items-start gap-3 flex-wrap">' +
              '<div class="fw-semibold">' + aiEscape(title) + "</div>" +
              '<span class="ai-rag-score">' + percent + "% match</span>" +
              "</div>" +
              '<p class="ai-rag-text">' + aiEscape(r.text || "") + "</p>" +
              '<div class="ai-progress-track">' +
              '<div class="progress-bar" style="width:' + percent + '%"></div>' +
              "</div>" +
              '<div class="ai-rag-meta">' +
              '<span><i class="bi bi-hash me-1"></i> chunk ' + (r.metadata && r.metadata.chunk_index) + "</span>" +
              '<span><i class="bi bi-globe2 me-1"></i> ' + aiEscape(r.source_id) + "</span>" +
              (location ? "<span><i class=\"bi bi-geo me-1\"></i> " + aiEscape(location) + "</span>" : "") +
              '<span><i class="bi bi-database me-1"></i> score ' + Number(r.similarity_score).toFixed(4) + "</span>" +
              "</div>" +
              "</div>"
            );
          })
          .join("");
      })
      .catch(function (err) {
        container.innerHTML =
          '<div class="text-center text-danger py-4">' + aiEscape(err.message) + "</div>";
      });
  }

  document.addEventListener("DOMContentLoaded", function () {
    loadStats();
    var form = document.getElementById("ragForm");
    if (!form) return;
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      doSearch();
    });
    var sample = document.getElementById("ragSample");
    if (sample) {
      sample.addEventListener("click", function (event) {
        var target = event.target.closest("a[data-query]");
        if (!target) return;
        event.preventDefault();
        var input = document.getElementById("ragQuery");
        input.value = target.getAttribute("data-query");
        doSearch();
      });
    }
  });
})();
