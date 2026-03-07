(function () {
  "use strict";

  function formatAgentTrace(trace, options) {
    if (!trace || typeof trace !== "object" || Array.isArray(trace)) {
      return "";
    }
    const opts = options || {};
    const t = typeof opts.t === "function" ? opts.t : function (key) {
      return key;
    };
    const normalized = trace;
    const sections = [];
    const preferred = ["planner", "writer", "reviewer", "synthesizer"];
    preferred.forEach(function (agent) {
      const text = String(normalized[agent] || "").trim();
      if (!text) {
        return;
      }
      sections.push("[" + t("web.ai.agent." + agent) + "]\n" + text);
    });
    Object.keys(normalized).forEach(function (agent) {
      if (preferred.indexOf(agent) >= 0) {
        return;
      }
      const text = String(normalized[agent] || "").trim();
      if (!text) {
        return;
      }
      sections.push("[" + agent + "]\n" + text);
    });
    if (sections.length === 0) {
      return "";
    }
    return t("web.ai.agent_trace") + "\n" + sections.join("\n\n");
  }

  function buildDiffSegments(beforeText, afterText) {
    const left = String(beforeText || "");
    const right = String(afterText || "");
    if (!left && !right) {
      return [];
    }
    if (left === right) {
      return [{ type: "same", text: right }];
    }
    const beforeTokens = left.split(/(\s+)/).filter(Boolean);
    const afterTokens = right.split(/(\s+)/).filter(Boolean);
    const maxTokens = 320;
    if (beforeTokens.length > maxTokens || afterTokens.length > maxTokens) {
      return [
        { type: "del", text: left },
        { type: "add", text: right }
      ];
    }
    const rows = beforeTokens.length + 1;
    const cols = afterTokens.length + 1;
    const dp = Array.from({ length: rows }, function () {
      return new Array(cols).fill(0);
    });
    for (let i = 1; i < rows; i += 1) {
      for (let j = 1; j < cols; j += 1) {
        if (beforeTokens[i - 1] === afterTokens[j - 1]) {
          dp[i][j] = dp[i - 1][j - 1] + 1;
        } else {
          dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
        }
      }
    }
    const merged = [];
    let i = beforeTokens.length;
    let j = afterTokens.length;
    while (i > 0 || j > 0) {
      if (i > 0 && j > 0 && beforeTokens[i - 1] === afterTokens[j - 1]) {
        merged.push({ type: "same", text: beforeTokens[i - 1] });
        i -= 1;
        j -= 1;
        continue;
      }
      if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
        merged.push({ type: "add", text: afterTokens[j - 1] });
        j -= 1;
        continue;
      }
      if (i > 0) {
        merged.push({ type: "del", text: beforeTokens[i - 1] });
        i -= 1;
      }
    }
    merged.reverse();
    const compact = [];
    merged.forEach(function (part) {
      const last = compact.length > 0 ? compact[compact.length - 1] : null;
      if (last && last.type === part.type) {
        last.text += part.text;
      } else {
        compact.push({ type: part.type, text: part.text });
      }
    });
    return compact;
  }

  function renderMarkdownPreview(options) {
    const opts = options || {};
    const h = opts.h;
    const text = opts.text;
    const emptyText = String(opts.emptyText || "");
    if (typeof h !== "function") {
      return null;
    }
    const normalized = String(text || "").replace(/\r\n/g, "\n");
    if (!normalized.trim()) {
      return h("div", { className: "muted" }, emptyText);
    }
    const lines = normalized.split("\n");
    const blocks = [];
    let paragraph = [];
    let listItems = [];
    let codeLines = [];
    let inCode = false;

    function flushParagraph() {
      if (paragraph.length === 0) {
        return;
      }
      blocks.push(h("p", { key: "md_p_" + blocks.length.toString() }, paragraph.join(" ")));
      paragraph = [];
    }

    function flushList() {
      if (listItems.length === 0) {
        return;
      }
      blocks.push(
        h(
          "ul",
          { key: "md_ul_" + blocks.length.toString() },
          listItems.map(function (item, index) {
            return h("li", { key: "md_li_" + index.toString() }, item);
          })
        )
      );
      listItems = [];
    }

    function flushCode() {
      if (codeLines.length === 0) {
        return;
      }
      blocks.push(
        h(
          "pre",
          { key: "md_pre_" + blocks.length.toString() },
          h("code", null, codeLines.join("\n"))
        )
      );
      codeLines = [];
    }

    lines.forEach(function (line) {
      const trimmed = line.trim();
      if (trimmed.startsWith("```")) {
        if (inCode) {
          flushCode();
          inCode = false;
        } else {
          flushParagraph();
          flushList();
          inCode = true;
        }
        return;
      }
      if (inCode) {
        codeLines.push(line);
        return;
      }
      if (!trimmed) {
        flushParagraph();
        flushList();
        return;
      }
      const heading = line.match(/^(#{1,6})\s+(.+)$/);
      if (heading) {
        flushParagraph();
        flushList();
        const level = Math.min(6, heading[1].length);
        blocks.push(h("h" + level.toString(), { key: "md_h_" + blocks.length.toString() }, heading[2]));
        return;
      }
      const quote = line.match(/^>\s?(.*)$/);
      if (quote) {
        flushParagraph();
        flushList();
        blocks.push(h("blockquote", { key: "md_q_" + blocks.length.toString() }, quote[1]));
        return;
      }
      const list = line.match(/^[-*]\s+(.+)$/);
      if (list) {
        flushParagraph();
        listItems.push(list[1]);
        return;
      }
      paragraph.push(trimmed);
    });
    flushParagraph();
    flushList();
    if (inCode) {
      flushCode();
    }
    return h("div", { className: "artifact-md" }, blocks);
  }

  function parseWorkflowMode(text) {
    const value = String(text || "").trim().toLowerCase();
    if (!value) {
      return "";
    }
    if (
      value.includes("原创") ||
      value.includes("original") ||
      value.includes("new")
    ) {
      return "original";
    }
    if (
      value.includes("续写") ||
      value.includes("续作") ||
      value.includes("同人") ||
      value.includes("sequel") ||
      value.includes("fanfic")
    ) {
      return "sequel";
    }
    return "";
  }

  function isWorkflowBackgroundConfirmed(text) {
    const raw = String(text || "").trim();
    if (!raw) {
      return false;
    }
    const lower = raw.toLowerCase();
    return (
      lower.includes("confirm background") ||
      raw.includes("确认背景无误") ||
      raw.includes("背景确认")
    );
  }

  function isWorkflowOutlineConfirmed(text) {
    const raw = String(text || "").trim();
    if (!raw) {
      return false;
    }
    const lower = raw.toLowerCase();
    return lower.includes("confirm outline") || raw.includes("确认大纲无误");
  }

  function parseBeatList(value, limit) {
    if (Array.isArray(value)) {
      return value
        .map(function (item) {
          return String(item || "").trim();
        })
        .filter(Boolean)
        .slice(0, limit);
    }
    const lines = String(value || "")
      .split(/\r?\n/)
      .map(function (line) {
        return line.replace(/^\s*(?:[-*]|\d+[.)、])\s*/, "").trim();
      })
      .filter(Boolean);
    return lines.slice(0, limit);
  }

  function beatTitle(beat, index, options) {
    const opts = options || {};
    const prefix = String(opts.defaultPrefix || "Scene");
    const text = String(beat || "").trim();
    if (!text) {
      return prefix + " " + String(index + 1);
    }
    const parts = text.split(/[:：]/);
    const head = String(parts[0] || "").trim();
    if (head && head.length <= 32) {
      return head;
    }
    return text.slice(0, 28);
  }

  window.ElyhaWebTextUtils = {
    formatAgentTrace: formatAgentTrace,
    buildDiffSegments: buildDiffSegments,
    renderMarkdownPreview: renderMarkdownPreview,
    parseWorkflowMode: parseWorkflowMode,
    isWorkflowBackgroundConfirmed: isWorkflowBackgroundConfirmed,
    isWorkflowOutlineConfirmed: isWorkflowOutlineConfirmed,
    parseBeatList: parseBeatList,
    beatTitle: beatTitle
  };
})();
