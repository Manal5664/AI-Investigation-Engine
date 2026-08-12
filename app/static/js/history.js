/* EvidenceAI · history.js — investigation list with delete (real engine). */
(function () {
  "use strict";

  var allItems = [];

  function renderRows(items) {
    var body = document.getElementById("historyBody");
    if (!body) return;
    if (items.length === 0) {
      body.innerHTML =
        '<tr><td colspan="8" class="text-center text-body-secondary py-5">' +
        '<i class="bi bi-clock-history fs-3 d-block mb-2"></i>' +
        'No investigations match. <a href="/investigate">Start one</a>.' +
        "</td></tr>";
      return;
    }

    body.innerHTML = items
      .map(function (r) {
        var badge =
          r.status === "completed"
            ? '<span class="badge rounded-pill text-bg-success">Completed</span>'
            : r.status === "failed"
            ? '<span class="badge rounded-pill text-bg-danger">Failed</span>'
            : '<span class="badge rounded-pill text-bg-warning">Partial</span>';
        var confidence = r.confidence
          ? '<span class="ai-mono small text-body-secondary">' + aiEscape(r.confidence) + "</span>"
          : '<span class="text-body-tertiary">—</span>';
        return (
          "<tr>" +
          '<td><a class="ai-table-link" href="/investigation/' + aiEscape(r.id) + '">' +
          aiEscape(r.query) +
          "</a></td>" +
          '<td class="ai-mono small text-body-secondary">' + aiEscape(r.depth) + "</td>" +
          "<td>" + badge + "</td>" +
          "<td>" + confidence + "</td>" +
          '<td class="text-body-secondary">' + r.total_source_count + "</td>" +
          '<td class="text-body-secondary">' + r.total_evidence_count + "</td>" +
          '<td class="text-body-secondary">' + aiEscape(r.created_at) + "</td>" +
          '<td class="text-end">' +
          '<a class="btn btn-sm btn-outline-secondary ai-icon-btn me-1" href="/investigation/' +
          aiEscape(r.id) +
          '" title="Open"><i class="bi bi-box-arrow-up-right"></i></a>' +
          '<button class="btn btn-sm btn-outline-danger ai-icon-btn delete-case" data-id="' +
          aiEscape(r.id) +
          '" data-query="' +
          aiEscape(r.query).replace(/"/g, "&quot;") +
          '" title="Delete"><i class="bi bi-trash3"></i></button>' +
          "</td>" +
          "</tr>"
        );
      })
      .join("");
    hookDelete();
  }

  function applyFilters() {
    var filter = (document.getElementById("historyFilter") || {}).value || "";
    var status = (document.getElementById("historyStatus") || {}).value || "";
    filter = filter.toLowerCase();
    var items = allItems.filter(function (r) {
      if (status && r.status !== status) return false;
      if (filter && (r.query || "").toLowerCase().indexOf(filter) === -1) return false;
      return true;
    });
    renderRows(items);
  }

  function loadList() {
    var body = document.getElementById("historyBody");
    var errBox = document.getElementById("historyError");
    if (!body) return;

    api
      .get("/api/v1/investigations?limit=100")
      .then(function (data) {
        allItems = data.investigations || [];
        applyFilters();
      })
      .catch(function (err) {
        allItems = [];
        body.innerHTML =
          '<tr><td colspan="8" class="text-center text-danger py-4">' +
          aiEscape(err.message) +
          "</td></tr>";
        if (errBox) {
          errBox.textContent = err.message;
          errBox.classList.remove("d-none");
        }
      });
  }

  function hookDelete() {
    var buttons = document.querySelectorAll(".delete-case");
    Array.prototype.forEach.call(buttons, function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-id");
        var query = btn.getAttribute("data-query");
        aiConfirm(
          'Delete the investigation "' + query + '"? This removes its results.',
          function () {
            api
              .del("/api/v1/investigations/" + id)
              .then(function () {
                aiToast("Investigation deleted.", "success");
                loadList();
              })
              .catch(function (err) {
                aiToast(err.message, "danger");
              });
          }
        );
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var filterInput = document.getElementById("historyFilter");
    var statusSelect = document.getElementById("historyStatus");
    if (filterInput) filterInput.addEventListener("input", applyFilters);
    if (statusSelect) statusSelect.addEventListener("change", applyFilters);
    loadList();
  });
})();
