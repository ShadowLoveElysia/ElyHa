(function () {
  "use strict";

  function splitNodeMetadata(metadata) {
    if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) {
      return {
        agentPreset: "",
        groupKind: "phase",
        groupParentId: "",
        groupBinding: "independent",
        plainMetadata: {}
      };
    }
    const source = Object.assign({}, metadata);
    const rawAgent = source.agent_preset;
    const agentPreset = typeof rawAgent === "string" ? rawAgent : "";
    const rawGroupKind = source.group_kind;
    const groupKind = rawGroupKind === "chapter" ? "chapter" : "phase";
    const rawGroupParentId = source.group_parent_id;
    const groupParentId = typeof rawGroupParentId === "string" ? rawGroupParentId.trim() : "";
    const rawGroupBinding = source.group_binding;
    const groupBinding = rawGroupBinding === "bound" ? "bound" : "independent";
    delete source.agent_preset;
    delete source.group_kind;
    delete source.group_parent_id;
    delete source.group_binding;
    return {
      agentPreset: agentPreset,
      groupKind: groupKind,
      groupParentId: groupParentId,
      groupBinding: groupBinding,
      plainMetadata: source
    };
  }

  function asBoolean(value, fallbackValue) {
    if (value === null || value === undefined) {
      return Boolean(fallbackValue);
    }
    if (typeof value === "boolean") {
      return value;
    }
    if (typeof value === "number") {
      return value !== 0;
    }
    const text = String(value).trim().toLowerCase();
    if (["1", "true", "yes", "on"].includes(text)) {
      return true;
    }
    if (["0", "false", "no", "off"].includes(text)) {
      return false;
    }
    return Boolean(fallbackValue);
  }

  function inferRuntimePreset(settings, presets) {
    if (!settings || !Array.isArray(presets) || presets.length === 0) {
      return "";
    }
    const provider = String(settings.llm_provider || "").toLowerCase();
    if (provider !== "llmrequester" && provider !== "legacy") {
      return "";
    }
    const apiUrl = String(settings.api_url || "").trim();
    const model = String(settings.model_name || "").trim();
    const exact = presets.find(function (item) {
      return (
        String(item.api_url || "").trim() === apiUrl &&
        String(item.default_model || "").trim() === model
      );
    });
    if (exact) {
      return String(exact.tag || "");
    }
    const byUrl = presets.find(function (item) {
      return String(item.api_url || "").trim() === apiUrl;
    });
    return byUrl ? String(byUrl.tag || "") : "";
  }

  function loadWebState(stateKey) {
    const key = String(stateKey || "elyha_web_state_v1");
    try {
      const raw = window.localStorage.getItem(key);
      if (!raw) {
        return {};
      }
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (_error) {
      return {};
    }
  }

  function saveWebState(stateKey, payload) {
    const key = String(stateKey || "elyha_web_state_v1");
    try {
      window.localStorage.setItem(key, JSON.stringify(payload));
    } catch (_error) {
      // ignore local storage quota/runtime errors
    }
  }

  function safeArray(value) {
    return Array.isArray(value) ? value : [];
  }

  function normalizeChatDiffSegments(value) {
    return safeArray(value)
      .map(function (segment) {
        const type = String(segment && segment.type ? segment.type : "same");
        const text = String(segment && segment.text ? segment.text : "");
        return { type: type, text: text.slice(0, 300) };
      })
      .slice(0, 120);
  }

  function normalizePersistedChatMessages(value) {
    return safeArray(value)
      .map(function (item, index) {
        const id = String(item && item.id ? item.id : "chat_cached_" + index.toString());
        const role = String(item && item.role ? item.role : "assistant");
        const text = String(item && item.text ? item.text : "");
        const meta = String(item && item.meta ? item.meta : "");
        const at = String(item && item.at ? item.at : new Date().toISOString());
        return {
          id: id,
          role: role === "user" ? "user" : "assistant",
          text: text.slice(0, 12000),
          meta: meta.slice(0, 200),
          at: at,
          diffSegments: normalizeChatDiffSegments(item && item.diffSegments)
        };
      })
      .slice(-120);
  }

  function normalizePersistedMainView(value) {
    const text = String(value || "").trim().toLowerCase();
    return text === "insight" ? "insight" : "story";
  }

  function normalizePersistedSidebarTab(value) {
    const text = String(value || "").trim().toLowerCase();
    if (["project", "runtime", "node", "ai", "ops", "tutorial"].includes(text)) {
      return text;
    }
    return "project";
  }

  window.ElyhaWebStateUtils = {
    splitNodeMetadata: splitNodeMetadata,
    asBoolean: asBoolean,
    inferRuntimePreset: inferRuntimePreset,
    loadWebState: loadWebState,
    saveWebState: saveWebState,
    safeArray: safeArray,
    normalizeChatDiffSegments: normalizeChatDiffSegments,
    normalizePersistedChatMessages: normalizePersistedChatMessages,
    normalizePersistedMainView: normalizePersistedMainView,
    normalizePersistedSidebarTab: normalizePersistedSidebarTab
  };
})();
