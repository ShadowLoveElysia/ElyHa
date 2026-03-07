(function () {
  "use strict";

  function isJsonResponse(response) {
    const contentType = response.headers.get("content-type") || "";
    return contentType.includes("application/json");
  }

  function extractErrorMessage(payload, status) {
    if (payload && typeof payload === "object") {
      if (typeof payload.detail === "string" && payload.detail.trim()) {
        return payload.detail.trim();
      }
      if (Array.isArray(payload.detail)) {
        return payload.detail.map(String).join("; ");
      }
      if (typeof payload.message === "string" && payload.message.trim()) {
        return payload.message.trim();
      }
    }
    if (typeof payload === "string" && payload.trim()) {
      return payload.trim();
    }
    return "HTTP " + status;
  }

  async function apiRequest(path, options) {
    const init = Object.assign({ method: "GET" }, options || {});
    const timeoutMsRaw = Number(init.timeout_ms);
    const timeoutMs = Number.isFinite(timeoutMsRaw) && timeoutMsRaw > 0 ? Math.floor(timeoutMsRaw) : 95000;
    delete init.timeout_ms;
    if (init.body && typeof init.body !== "string") {
      init.headers = Object.assign({}, init.headers, { "Content-Type": "application/json" });
      init.body = JSON.stringify(init.body);
    }

    const controller = new AbortController();
    const timer = window.setTimeout(function () {
      controller.abort();
    }, timeoutMs);
    init.signal = controller.signal;

    try {
      const response = await fetch(path, init);
      const payload = isJsonResponse(response) ? await response.json() : await response.text();
      if (!response.ok) {
        throw new Error(extractErrorMessage(payload, response.status));
      }
      return payload;
    } catch (error) {
      if (error && error.name === "AbortError") {
        throw new Error("request timeout after " + Math.round(timeoutMs / 1000).toString() + "s");
      }
      throw error;
    } finally {
      window.clearTimeout(timer);
    }
  }

  function formatValue(template, variables) {
    if (!variables) {
      return template;
    }
    return template.replace(/\{(\w+)\}/g, function (_match, name) {
      const value = variables[name];
      return value === undefined || value === null ? "" : String(value);
    });
  }

  function shortIso(value) {
    if (!value) {
      return "-";
    }
    try {
      return new Date(value).toLocaleString();
    } catch (_error) {
      return String(value);
    }
  }

  function asNumber(input, fallbackValue) {
    const parsed = Number(input);
    return Number.isFinite(parsed) ? parsed : fallbackValue;
  }

  window.ElyhaWebHelpers = {
    apiRequest: apiRequest,
    formatValue: formatValue,
    shortIso: shortIso,
    asNumber: asNumber
  };
})();
