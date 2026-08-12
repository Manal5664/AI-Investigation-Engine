/* EvidenceAI · app.js — global helpers: escaping, toasts, confirm, formatting, theme, sidebar. */
(function () {
  "use strict";

  function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  window.aiEscape = escapeHtml;

  function formatBytes(bytes) {
    if (bytes === null || bytes === undefined) return "—";
    var value = Number(bytes);
    if (!isFinite(value) || value < 0) return "—";
    if (value < 1024) return Math.round(value) + " B";
    var units = ["KB", "MB", "GB", "TB"];
    var unit = "B";
    for (var i = 0; i < units.length; i += 1) {
      value = value / 1024;
      unit = units[i];
      if (value < 1024) break;
    }
    var digits = value >= 10 || Math.floor(value) === value ? 0 : 1;
    return value.toFixed(digits) + " " + unit;
  }

  window.aiFormatBytes = formatBytes;

  function showToast(message, kind) {
    kind = kind || "info";
    var stack = document.getElementById("aiToasts");
    if (!stack) return;
    var icon =
      kind === "success" ? "check-circle-fill" :
      kind === "danger" ? "x-circle-fill" :
      kind === "warning" ? "exclamation-triangle-fill" : "info-circle-fill";
    var toast = document.createElement("div");
    toast.className = "toast align-items-center text-bg-" + kind + " border-0";
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");
    toast.setAttribute("aria-atomic", "true");
    toast.innerHTML =
      '<div class="d-flex">' +
      '<div class="toast-body"><i class="bi bi-' + icon + ' me-2"></i>' +
      escapeHtml(message) +
      "</div>" +
      '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>' +
      "</div>";
    stack.appendChild(toast);
    if (window.bootstrap && window.bootstrap.Toast) {
      var instance = new window.bootstrap.Toast(toast, { delay: 5000 });
      instance.show();
      toast.addEventListener("hidden.bs.toast", function () { toast.remove(); });
    } else {
      window.setTimeout(function () { toast.remove(); }, 5000);
    }
  }

  window.aiToast = showToast;

  var confirmCallback = null;

  function askConfirm(message, onOk) {
    var modal = document.getElementById("confirmModal");
    var body = document.getElementById("confirmModalBody");
    if (!modal) {
      if (onOk) onOk();
      return;
    }
    if (body) body.textContent = message;
    confirmCallback = onOk || null;
    if (window.bootstrap && window.bootstrap.Modal) {
      window.bootstrap.Modal.getOrCreateInstance(modal).show();
    } else if (confirmCallback) {
      var callback = confirmCallback;
      confirmCallback = null;
      callback();
    }
  }

  window.aiConfirm = askConfirm;

  function initConfirmModal() {
    var ok = document.getElementById("confirmModalOk");
    var modal = document.getElementById("confirmModal");
    if (!ok || !modal) return;
    ok.addEventListener("click", function () {
      if (window.bootstrap && window.bootstrap.Modal) {
        window.bootstrap.Modal.getOrCreateInstance(modal).hide();
      } else {
        modal.classList.remove("show");
      }
      if (confirmCallback) {
        var callback = confirmCallback;
        confirmCallback = null;
        callback();
      }
    });
    modal.addEventListener("hidden.bs.modal", function () { confirmCallback = null; });
  }

  function initThemeToggle() {
    var buttons = document.querySelectorAll("[data-theme-toggle]");
    if (!buttons.length) return;
    var root = document.documentElement;
    function apply(theme) {
      root.setAttribute("data-bs-theme", theme);
      try { window.localStorage.setItem("aie-theme", theme); } catch (_e) { /* noop */ }
      var dark = theme === "dark";
      Array.prototype.forEach.call(buttons, function (btn) {
        var icon = btn.querySelector("i");
        if (icon) icon.className = "bi bi-" + (dark ? "sun" : "moon-stars");
      });
    }
    try {
      var saved = window.localStorage.getItem("aie-theme");
      if (saved === "dark" || saved === "light") apply(saved);
    } catch (_e) { /* noop */ }
    Array.prototype.forEach.call(buttons, function (btn) {
      btn.addEventListener("click", function () {
        apply(root.getAttribute("data-bs-theme") === "dark" ? "light" : "dark");
      });
    });
  }

  function setSidebar(open) {
    var sidebar = document.getElementById("aiSidebar");
    var layout = document.getElementById("aiLayout");
    var backdrop = document.getElementById("sidebarBackdrop");
    if (sidebar) sidebar.classList.toggle("open", open);
    if (layout) layout.classList.toggle("sidebar-open", open);
    if (backdrop) backdrop.classList.toggle("show", open);
  }

  function initSidebarToggle() {
    var button = document.getElementById("sidebarToggle");
    var sidebar = document.getElementById("aiSidebar");
    var backdrop = document.getElementById("sidebarBackdrop");
    if (!button || !sidebar) return;
    button.addEventListener("click", function () {
      setSidebar(!sidebar.classList.contains("open"));
    });
    if (backdrop) {
      backdrop.addEventListener("click", function () { setSidebar(false); });
    }
    Array.prototype.forEach.call(
      sidebar.querySelectorAll(".ai-nav-item"),
      function (item) {
        item.addEventListener("click", function () {
          if (window.matchMedia("(max-width: 991.98px)").matches) setSidebar(false);
        });
      }
    );
  }

  document.addEventListener("DOMContentLoaded", function () {
    initConfirmModal();
    initThemeToggle();
    initSidebarToggle();
  });
})();
