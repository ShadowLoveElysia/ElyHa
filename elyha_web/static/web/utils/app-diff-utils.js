(function () {
  "use strict";

  function normalizeDiffKind(value) {
    const text = String(value || "").trim().toLowerCase();
    if (text === "add" || text === "ins" || text === "insert") {
      return "add";
    }
    if (text === "del" || text === "delete" || text === "remove") {
      return "del";
    }
    return "same";
  }

  function diffPrefix(kind) {
    const normalized = normalizeDiffKind(kind);
    if (normalized === "add") {
      return "+";
    }
    if (normalized === "del") {
      return "-";
    }
    return " ";
  }

  window.ElyhaWebDiffUtils = {
    normalizeDiffKind: normalizeDiffKind,
    diffPrefix: diffPrefix
  };
})();
