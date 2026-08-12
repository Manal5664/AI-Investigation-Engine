/* EvidenceAI · documents.js — upload, filter, delete (real document store). */
(function () {
  "use strict";

  var KIND_LABELS = {
    pdf: "PDF",
    docx: "DOCX",
    text: "Text",
    image: "Image",
  };

  var KIND_ICONS = {
    pdf: "bi-file-earmark-pdf",
    docx: "bi-file-earmark-word",
    text: "bi-file-earmark-text",
    image: "bi-file-earmark-image",
  };

  function kindLabel(kind) {
    return KIND_LABELS[kind] || kind || "Document";
  }

  function kindIcon(kind) {
    return KIND_ICONS[kind] || "bi-file-earmark";
  }

  function buildRows(docs) {
    return docs
      .map(function (doc) {
        return (
          '<div class="col-md-6 col-xl-4">' +
          '<div class="card ai-card h-100">' +
          '<div class="card-body d-flex flex-column">' +
          '<div class="d-flex justify-content-between align-items-start gap-2">' +
          '<div class="ai-doc-cell">' +
          '<i class="bi ' + kindIcon(doc.kind) + " ai-doc-icon\"></i>" +
          '<div><span class="ai-doc-name">' + aiEscape(doc.filename) + "</span>" +
          '<span class="ai-doc-hash">' + aiEscape(doc.document_id) + "</span></div>" +
          "</div>" +
          '<button class="btn btn-sm btn-outline-danger ai-icon-btn delete-doc" data-id="' +
          aiEscape(doc.document_id) +
          '" data-name="' +
          aiEscape(doc.filename).replace(/"/g, "&quot;") +
          '" title="Delete document"><i class="bi bi-trash3"></i></button>' +
          "</div>" +
          '<div class="mt-2 d-flex flex-wrap gap-1">' +
          '<span class="badge rounded-pill text-bg-light border ai-mono">' + kindLabel(doc.kind) + "</span>" +
          '<span class="badge rounded-pill text-bg-light border">' + doc.page_count + " pages</span>" +
          "</div>" +
          '<div class="d-flex justify-content-between align-items-center mt-auto pt-3">' +
          '<span class="ai-mono small text-body-tertiary">' + aiFormatBytes(doc.file_size_bytes) + "</span>" +
          '<span class="ai-mono small text-body-tertiary">' + aiEscape(doc.received_at) + "</span>" +
          "</div>" +
          "</div></div></div>"
        );
      })
      .join("");
  }

  function emptyRow() {
    return (
      '<div class="col-12 text-center text-body-secondary py-5">' +
      '<i class="bi bi-folder2-open fs-1 d-block mb-2"></i>' +
      "No documents here yet — upload evidence to get started." +
      "</div>"
    );
  }

  function showCount(total) {
    var el = document.getElementById("docCount");
    if (el) el.textContent = total;
  }

  var allDocs = [];

  function render(filter) {
    var grid = document.getElementById("docGrid");
    if (!grid) return;
    filter = (filter || "").toLowerCase();
    var docs = filter
      ? allDocs.filter(function (d) {
          return (d.filename || "").toLowerCase().indexOf(filter) !== -1;
        })
      : allDocs;
    grid.innerHTML = docs.length ? buildRows(docs) : emptyRow();
    hookDelete();
  }

  function renderFileList(files) {
    var list = document.getElementById("fileList");
    var zone = document.getElementById("docDropzone");
    if (!list || !zone) return;
    zone.classList.toggle("has-files", files.length > 0);
    if (files.length === 0) {
      list.classList.add("d-none");
      list.innerHTML = "";
      return;
    }
    list.classList.remove("d-none");
    list.innerHTML =
      '<div class="small fw-semibold text-body-secondary mb-1">' +
      files.length + " file(s) selected</div>" +
      files
        .map(function (file) {
          return (
            '<div class="ai-upload-item">' +
            '<i class="bi bi-file-earmark" aria-hidden="true"></i>' +
            '<span class="ai-upload-name">' + aiEscape(file.name) + "</span>" +
            '<span class="ai-upload-size">' + aiFormatBytes(file.size) + "</span>" +
            "</div>"
          );
        })
        .join("");
  }

  function initDropzone() {
    var zone = document.getElementById("docDropzone");
    var input = document.getElementById("documentFile");
    if (!zone || !input) return;
    ["dragenter", "dragover"].forEach(function (name) {
      zone.addEventListener(name, function (event) {
        event.preventDefault();
        event.stopPropagation();
        zone.classList.add("dragging");
      });
    });
    ["dragleave", "drop"].forEach(function (name) {
      zone.addEventListener(name, function (event) {
        event.preventDefault();
        event.stopPropagation();
        zone.classList.remove("dragging");
      });
    });
    zone.addEventListener("drop", function (event) {
      var files = event.dataTransfer && event.dataTransfer.files;
      if (files && files.length) {
        input.files = files;
        renderFileList(input.files);
      }
    });
    zone.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        input.click();
      }
    });
    input.addEventListener("change", function () {
      renderFileList(input.files);
    });
  }

  function hookUpload(form) {
    var result = document.getElementById("uploadResult");
    var button = document.getElementById("uploadBtn");
    var input = document.getElementById("documentFile");
    var progressWrap = document.getElementById("uploadProgress");
    var progressBar = document.getElementById("uploadProgressBar");
    var progressText = document.getElementById("uploadProgressText");

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (!input || !input.files || input.files.length === 0) {
        aiToast("Choose at least one file to upload.", "warning");
        return;
      }

      var fd = new FormData();
      Array.prototype.forEach.call(input.files, function (file) {
        fd.append("files", file, file.name);
      });

      button.disabled = true;
      button.querySelector(".spinner-border").classList.remove("d-none");
      if (result) {
        result.classList.add("d-none");
        result.textContent = "";
      }
      if (progressWrap) progressWrap.classList.remove("d-none");

      var xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/v1/documents/upload");
      xhr.setRequestHeader("Accept", "application/json");
      xhr.upload.addEventListener("progress", function (event) {
        if (!event.lengthComputable || !progressBar) return;
        var percent = Math.round((event.loaded / event.total) * 100);
        progressBar.style.width = percent + "%";
        progressBar.setAttribute("aria-valuenow", percent);
        if (progressText) progressText.textContent = "Uploading… " + percent + "%";
      });
      xhr.addEventListener("load", function () {
        var payload = null;
        try { payload = JSON.parse(xhr.responseText || "null"); } catch (_e) { payload = null; }
        if (xhr.status >= 200 && xhr.status < 300) {
          var count = (payload && payload.documents && payload.documents.length) || 0;
          var duplicated = 0;
          (payload && payload.documents || []).forEach(function (d) {
            if (d.duplicate) duplicated += 1;
          });
          aiToast("Uploaded " + count + " document(s).", "success");
          if (result) {
            result.classList.remove("d-none", "text-danger");
            result.textContent =
              "Uploaded " + count + " document(s)." +
              (duplicated ? " " + duplicated + " skipped as duplicates." : "");
          }
          if (input) input.value = "";
          renderFileList(input ? input.files : []);
          loadList();
        } else {
          var msg = (payload && (payload.message || payload.detail)) ||
            "Upload failed with status " + xhr.status;
          aiToast(msg, "danger");
          if (result) {
            result.classList.remove("d-none");
            result.classList.add("text-danger");
            result.textContent = msg;
          }
        }
      });
      xhr.addEventListener("error", function () {
        aiToast("Network error during upload.", "danger");
        if (result) {
          result.classList.remove("d-none");
          result.classList.add("text-danger");
          result.textContent = "Network error during upload.";
        }
      });
      xhr.addEventListener("loadend", function () {
        button.disabled = false;
        button.querySelector(".spinner-border").classList.add("d-none");
        if (progressWrap) progressWrap.classList.add("d-none");
        if (progressBar) {
          progressBar.style.width = "0%";
          progressBar.setAttribute("aria-valuenow", 0);
        }
      });
      xhr.send(fd);
    });
  }

  function loadList() {
    var grid = document.getElementById("docGrid");
    if (!grid) return;
    api
      .get("/api/v1/documents?limit=100")
      .then(function (data) {
        allDocs = data.documents || [];
        showCount(allDocs.length);
        var filterInput = document.getElementById("docFilter");
        render(filterInput ? filterInput.value : "");
      })
      .catch(function (err) {
        allDocs = [];
        grid.innerHTML =
          '<div class="col-12 text-center text-danger py-4">' + aiEscape(err.message) + "</div>";
        var errBox = document.getElementById("docError");
        if (errBox) {
          errBox.textContent = err.message;
          errBox.classList.remove("d-none");
        }
      });
  }

  function hookDelete() {
    var buttons = document.querySelectorAll(".delete-doc");
    Array.prototype.forEach.call(buttons, function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-id");
        var name = btn.getAttribute("data-name");
        aiConfirm(
          'Delete "' + name + '"? This cannot be undone.',
          function () {
            api
              .del("/api/v1/documents/" + id)
              .then(function () {
                aiToast("Document deleted.", "success");
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
    var form = document.getElementById("uploadForm");
    if (form) hookUpload(form);
    initDropzone();
    var filterInput = document.getElementById("docFilter");
    if (filterInput) {
      filterInput.addEventListener("input", function () {
        render(filterInput.value);
      });
    }
    loadList();
  });
})();
