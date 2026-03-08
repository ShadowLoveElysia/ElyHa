(function () {
  "use strict";

  const helpers = window.ElyhaWebHelpers || {};
  const stateUtils = window.ElyhaWebStateUtils || {};
  const asNumber = helpers.asNumber || function (value, fallbackValue) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallbackValue;
  };
  const safeArray = stateUtils.safeArray || function (value) {
    return Array.isArray(value) ? value : [];
  };
  const GHOST_OUTLINE_LIMIT = 8;

  function ghostIdWithSeed(seed) {
    const suffix = String(seed || "").replace(/[^a-zA-Z0-9_]/g, "").slice(0, 16);
    return (
      "ghost_" +
      Date.now().toString(36) +
      "_" +
      Math.random().toString(36).slice(2, 8) +
      (suffix ? "_" + suffix : "")
    );
  }

  function normalizeGhostSentiment(value) {
    const raw = String(value || "")
      .trim()
      .toLowerCase()
      .replace(/[ -]/g, "_");
    const aliasMap = {
      conflict: "conflict",
      high_pressure: "conflict",
      pressure: "conflict",
      combat: "conflict",
      "冲突": "conflict",
      "高压": "conflict",
      "対峙": "conflict",
      "衝突": "conflict",
      calm: "calm",
      memory: "calm",
      flashback: "calm",
      "平缓": "calm",
      "回忆": "calm",
      "穏やか": "calm",
      suspense: "suspense",
      mystery: "suspense",
      "悬疑": "suspense",
      "疑云": "suspense",
      "サスペンス": "suspense",
      twist: "twist",
      turning: "twist",
      "转折": "twist",
      "反转": "twist",
      "転換": "twist",
      neutral: "neutral",
      "中性": "neutral",
      "中立": "neutral"
    };
    return aliasMap[raw] || "neutral";
  }

  function inferGhostSentimentFromText(title, description) {
    const text = (String(title || "") + "\n" + String(description || "")).toLowerCase();
    const groups = [
      {
        sentiment: "conflict",
        keywords: ["对峙", "冲突", "追杀", "厮杀", "高压", "fight", "battle", "duel", "chase", "conflict", "対峙", "衝突"]
      },
      {
        sentiment: "calm",
        keywords: ["回忆", "回想", "平缓", "日常", "memory", "flashback", "calm", "quiet", "静か"]
      },
      {
        sentiment: "suspense",
        keywords: ["悬疑", "疑云", "谜", "协议", "线索", "suspense", "mystery", "clue", "protocol", "謎", "不穏"]
      },
      {
        sentiment: "twist",
        keywords: ["反转", "转折", "背叛", "揭示", "twist", "reveal", "betray", "反転", "どんでん返し"]
      }
    ];
    for (let index = 0; index < groups.length; index += 1) {
      const group = groups[index];
      if (group.keywords.some(function (keyword) {
        return text.includes(keyword);
      })) {
        return group.sentiment;
      }
    }
    return "neutral";
  }

  function normalizeGhostOutlineSteps(value, limit) {
    const maxItems = Math.max(1, Math.floor(asNumber(limit, 3)));
    if (Array.isArray(value)) {
      return value
        .map(function (item) {
          return String(item || "").trim();
        })
        .filter(Boolean)
        .slice(0, maxItems);
    }
    const text = String(value || "").trim();
    if (!text) {
      return [];
    }
    return text
      .split(/\n|\/|->|→|\|/)
      .map(function (line) {
        return String(line || "")
          .replace(/^\s*(?:[-*]|\d+[.)、])\s*/, "")
          .trim();
      })
      .filter(Boolean)
      .slice(0, maxItems);
  }

  function pickGhostOutlineSteps(option, fallbackText) {
    if (!option || typeof option !== "object") {
      return normalizeGhostOutlineSteps(fallbackText, GHOST_OUTLINE_LIMIT);
    }
    let steps = normalizeGhostOutlineSteps(
      option.outline_steps || option.beats || option.next_steps || option.future_steps,
      GHOST_OUTLINE_LIMIT
    );
    if (steps.length === 0) {
      const compact = [];
      ["next_1", "next_2", "next_3"].forEach(function (field) {
        const value = String(option[field] || "").trim();
        if (value) {
          compact.push(value);
        }
      });
      steps = compact.slice(0, 3);
    }
    if (steps.length === 0) {
      steps = normalizeGhostOutlineSteps(fallbackText, GHOST_OUTLINE_LIMIT);
    }
    if (steps.length === 0 && fallbackText) {
      steps = [String(fallbackText)];
    }
    return steps.slice(0, GHOST_OUTLINE_LIMIT);
  }

  function normalizePersistedGhostArchive(value) {
    return safeArray(value)
      .map(function (item, index) {
        if (!item || typeof item !== "object") {
          return null;
        }
        const id = String(item.id || "ghost_arc_" + index.toString());
        const projectId = String(item.project_id || "");
        const payload = item.payload && typeof item.payload === "object" ? item.payload : {};
        const title = String(payload.title || item.title || "").trim();
        const description = String(payload.description || item.description || "").trim();
        return {
          id: id,
          project_id: projectId,
          archived_at: String(item.archived_at || new Date().toISOString()),
          payload: {
            id: String(payload.id || ghostIdWithSeed("restored")),
            source_id: String(payload.source_id || ""),
            source_ghost_id: String(payload.source_ghost_id || ""),
            chain_root_id: String(payload.chain_root_id || ""),
            chain_index: Math.max(0, Math.floor(asNumber(payload.chain_index, 0))),
            source_title: String(payload.source_title || ""),
            title: title || "Ghost",
            description: description || "-",
            storyline_id: String(payload.storyline_id || ""),
            sentiment: normalizeGhostSentiment(payload.sentiment),
            outline_steps: normalizeGhostOutlineSteps(payload.outline_steps || description, GHOST_OUTLINE_LIMIT),
            pos_x: asNumber(payload.pos_x, 0),
            pos_y: asNumber(payload.pos_y, 0),
            locked: Boolean(payload.locked),
            created_at: String(payload.created_at || new Date().toISOString())
          }
        };
      })
      .filter(Boolean)
      .slice(0, 240);
  }

  function ghostOutlineText(plan) {
    if (!plan) {
      return "-";
    }
    const steps = normalizeGhostOutlineSteps(plan.outline_steps || plan.description, GHOST_OUTLINE_LIMIT);
    if (steps.length > 1) {
      return steps.map(function (step, index) {
        return (index + 1).toString() + ". " + step;
      }).join("\n");
    }
    if (steps.length === 1) {
      return steps[0];
    }
    return String(plan.description || "-");
  }

  function sentimentToneColor(sentiment) {
    const normalized = normalizeGhostSentiment(sentiment);
    const palette = {
      conflict: "#ff8d86",
      calm: "#7ec6f3",
      suspense: "#b487ff",
      twist: "#ffc976",
      neutral: "#84ceeb"
    };
    return palette[normalized] || palette.neutral;
  }

  function pruneGhostStateMap(prev, validIds) {
    const source = prev && typeof prev === "object" ? prev : {};
    const next = {};
    let changed = false;
    Object.keys(source).forEach(function (ghostId) {
      if (source[ghostId] && validIds.has(ghostId)) {
        next[ghostId] = true;
        return;
      }
      if (source[ghostId]) {
        changed = true;
      }
    });
    if (!changed && Object.keys(source).length === Object.keys(next).length) {
      return source;
    }
    return next;
  }

  window.ElyhaWebGhostUtils = {
    ghostIdWithSeed: ghostIdWithSeed,
    normalizeGhostSentiment: normalizeGhostSentiment,
    inferGhostSentimentFromText: inferGhostSentimentFromText,
    normalizeGhostOutlineSteps: normalizeGhostOutlineSteps,
    pickGhostOutlineSteps: pickGhostOutlineSteps,
    normalizePersistedGhostArchive: normalizePersistedGhostArchive,
    ghostOutlineText: ghostOutlineText,
    sentimentToneColor: sentimentToneColor,
    pruneGhostStateMap: pruneGhostStateMap
  };
})();
