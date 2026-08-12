/* EvidenceAI · investigate.js — run a real agentic investigation. */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var form = document.getElementById("investigateForm");
    if (!form) return;

    var submitBtn = document.getElementById("investigateSubmit");
    var spinner = submitBtn ? submitBtn.querySelector(".spinner-border") : null;
    var buttonLabel = submitBtn ? submitBtn.querySelector("span:not(.spinner-border)") : null;
    var progress = document.getElementById("investigateProgress");
    var progressBar = document.getElementById("investigateProgressBar");
    var progressText = document.getElementById("investigateProgressText");
    var workflow = document.getElementById("investigateWorkflow");
    var startedAt = null;

    var MESSAGES = [
      "Planning sub-questions…",
      "Researching sources…",
      "Extracting evidence…",
      "Running critic review…",
      "Synthesizing the report…",
    ];

    var STEPS = ["plan", "research", "extract", "critic", "synthesize"];

    /* Depth picker cards back the hidden <select id="depth">. */
    var depthSelect = document.getElementById("depth");
    var depthCards = Array.prototype.slice.call(document.querySelectorAll(".ai-depth-card"));
    function syncDepthSelect() {
      if (!depthSelect) return;
      var selected = depthCards.filter(function (card) {
        return card.classList.contains("selected");
      })[0];
      if (selected && selected.getAttribute("data-depth") !== depthSelect.value) {
        depthSelect.value = selected.getAttribute("data-depth");
      }
    }
    depthCards.forEach(function (card) {
      card.addEventListener("click", function () {
        depthCards.forEach(function (c) {
          c.classList.toggle("selected", c === card);
          c.setAttribute("aria-checked", c === card ? "true" : "false");
        });
        syncDepthSelect();
      });
    });
    if (depthSelect && depthCards.length) {
      depthSelect.addEventListener("change", function () {
        depthCards.forEach(function (card) {
          var isSelected = card.getAttribute("data-depth") === depthSelect.value;
          card.classList.toggle("selected", isSelected);
          card.setAttribute("aria-checked", isSelected ? "true" : "false");
        });
      });
    }
    syncDepthSelect();

    function setWorkflow(phaseIndex) {
      if (!workflow) return;
      var steps = workflow.querySelectorAll("[data-wf-step]");
      Array.prototype.forEach.call(steps, function (el) {
        var idx = STEPS.indexOf(el.getAttribute("data-wf-step"));
        el.classList.toggle("done", idx < phaseIndex);
        el.classList.toggle("active", idx === phaseIndex);
      });
    }

    function setProgress(message) {
      var elapsed = startedAt ? Math.round((Date.now() - startedAt) / 1000) : 0;
      var minutes = Math.floor(elapsed / 60);
      var seconds = elapsed % 60;
      var timer = (minutes > 0 ? minutes + "m " : "") + seconds + "s";
      if (progressBar) {
        var phase = Math.min(90, Math.floor(elapsed / 30) * 20);
        progressBar.style.width = phase + "%";
        progressBar.setAttribute("aria-valuenow", phase);
      }
      if (progressText) progressText.textContent = message + " (" + timer + ")";
      if (progress) progress.classList.remove("d-none");
      if (workflow) workflow.classList.remove("d-none");
    }

    function setBusy(busy) {
      if (!submitBtn) return;
      submitBtn.disabled = busy;
      if (spinner) spinner.classList.toggle("d-none", !busy);
      if (buttonLabel) buttonLabel.textContent = busy ? "Running…" : "Run investigation";
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();

      var query = (document.getElementById("query") || {}).value || "";
      if (query.trim().length < 5) {
        aiToast("Enter an investigation question (at least 5 characters).", "warning");
        return;
      }

      var depth = depthSelect ? depthSelect.value : "quick";
      var data = {
        query: query.trim(),
        depth: depth,
        run_critic: !!(document.getElementById("runCritic") || {}).checked,
        use_rag: !!(document.getElementById("useRag") || {}).checked,
        use_graph_rag: !!(document.getElementById("useGraphRag") || {}).checked,
      };

      startedAt = Date.now();
      setBusy(true);
      setWorkflow(1);
      setProgress(MESSAGES[0]);
      var messageIndex = 0;
      var messageTimer = window.setInterval(function () {
        messageIndex = Math.min(messageIndex + 1, MESSAGES.length - 1);
        setWorkflow(messageIndex);
        setProgress(MESSAGES[messageIndex]);
      }, 45000);

      api
        .post("/api/investigations/run", data, 900000)
        .then(function (result) {
          window.clearInterval(messageTimer);
          setBusy(false);
          if (progress) progress.classList.add("d-none");
          if (workflow) workflow.classList.add("d-none");
          var id = result.investigation_id;
          if (id) {
            aiToast("Investigation completed.", "success");
            window.location.href = "/investigation/" + id;
          } else {
            aiToast("The investigation finished but no result was persisted.", "warning");
          }
        })
        .catch(function (err) {
          window.clearInterval(messageTimer);
          setBusy(false);
          if (progress) progress.classList.add("d-none");
          if (workflow) workflow.classList.add("d-none");
          aiToast(err.message, "danger");
        });
    });
  });
})();
