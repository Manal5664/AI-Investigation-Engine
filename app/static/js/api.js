/* EvidenceAI · api.js — tiny JSON fetch wrapper with error normalization. */
(function () {
  "use strict";

  function parseError(payload, status) {
    if (payload && typeof payload === "object") {
      if (payload.message) return payload.message;
      if (payload.detail) {
        return typeof payload.detail === "string"
          ? payload.detail
          : JSON.stringify(payload.detail);
      }
    }
    return "Request failed with status " + status;
  }

  async function request(method, url, body, timeoutMs) {
    var controller = new AbortController();
    var timer = window.setTimeout(function () {
      controller.abort();
    }, timeoutMs || 60000);

    var options = {
      method: method,
      headers: { Accept: "application/json" },
      signal: controller.signal,
    };
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }

    var response;
    try {
      response = await fetch(url, options);
    } catch (err) {
      window.clearTimeout(timer);
      if (err.name === "AbortError") {
        throw new Error("Request timed out after " + (timeoutMs || 60000) + "ms");
      }
      throw new Error("Network error: " + err.message);
    }
    window.clearTimeout(timer);

    var payload = null;
    var text = await response.text();
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch (_e) {
        payload = null;
      }
    }

    if (!response.ok) {
      throw new Error(parseError(payload, response.status));
    }
    return payload;
  }

  window.api = {
    get: function (url, timeoutMs) { return request("GET", url, undefined, timeoutMs); },
    post: function (url, body, timeoutMs) { return request("POST", url, body, timeoutMs); },
    put: function (url, body, timeoutMs) { return request("PUT", url, body, timeoutMs); },
    del: function (url, timeoutMs) { return request("DELETE", url, undefined, timeoutMs); },
  };
})();
