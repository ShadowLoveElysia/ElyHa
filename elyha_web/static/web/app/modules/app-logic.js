(function () {
  "use strict";

  window.ElyhaWebAppModules = window.ElyhaWebAppModules || {};

  window.ElyhaWebAppModules.createAppLogic = function createAppLogic(deps) {
    const {
      h,
      useEffect,
      useMemo,
      constants,
      helpers,
      components,
      stateUtils,
      ghostUtils,
      graphUtils,
      textUtils,
      diffUtils,
      artifactUtils,
      apiActions,
      aiActions,
      configActions,
      workflowActions,
      appGhostActions,
      projectActions,
      nodeActions,
      NODE_WIDTH,
      NODE_HEIGHT,
      SUPPORTED_LOCALES,
      DEFAULT_LOCALE,
      NODE_TYPES,
      GROUP_KINDS,
      GROUP_BINDINGS,
      NODE_STATUSES,
      FALLBACK_TEXT,
      MIN_ZOOM,
      MAX_ZOOM,
      ZOOM_STEP,
      STORYLINE_ALL,
      WEB_STATE_KEY,
      NODE_MIN_WIDTH,
      NODE_MIN_HEIGHT,
      GROUP_MIN_WIDTH,
      GROUP_MIN_HEIGHT,
      GROUP_LAYOUT_PADDING_X,
      GROUP_LAYOUT_PADDING_Y,
      GROUP_LAYOUT_GAP_X,
      GROUP_LAYOUT_GAP_Y,
      apiRequest,
      formatValue,
      shortIso,
      asNumber,
      MetaItem,
      Modal,
      rectAnchor,
      cubicMidpoint,
      splitNodeMetadata,
      asBoolean,
      inferRuntimePreset,
      loadWebStateValue,
      saveWebStateValue,
      loadWebState,
      saveWebState,
      safeArray,
      normalizeChatDiffSegments,
      normalizePersistedChatMessages,
      normalizePersistedMainView,
      normalizePersistedSidebarTab,
      ghostIdWithSeed,
      normalizeGhostSentiment,
      inferGhostSentimentFromText,
      normalizeGhostOutlineSteps,
      pickGhostOutlineSteps,
      normalizePersistedGhostArchive,
      ghostOutlineTextValue,
      sentimentToneColorValue,
      pruneGhostStateMapValue,
      edgeDisplayLabelValue,
      compareEdgesByNarrativeOrderValue,
      clampZoomValue,
      nodeMetadataObjectValue,
      readGroupBindingValue,
      applyGroupBindingValue,
      sceneRenderSizeByMetadataValue,
      groupRenderSizeByMetadataValue,
      findContainingGroupIdValue,
      formatAgentTraceValue,
      buildDiffSegmentsValue,
      renderMarkdownPreviewValue,
      parseWorkflowModeValue,
      isWorkflowBackgroundConfirmedValue,
      isWorkflowOutlineConfirmedValue,
      parseBeatListValue,
      beatTitleValue,
      normalizeDiffKindValue,
      diffPrefixValue,
      resolveActiveChatContextValue,
      nextArtifactDiffNodeIdValue,
      shouldShowArtifactDiffValue,
      buildDefaultWorkflowStateValue,
      createWorkflowActionHandlersValue,
      createGhostActionHandlersValue,
      createProjectActionHandlersValue,
      createNodeActionHandlersValue,
      buildDefaultWorkflowState,
      resolveActiveChatContext,
      nextArtifactDiffNodeId,
      shouldShowArtifactDiff,
      normalizeDiffKind,
      diffPrefix,
      locale,
      setLocale,
      persistedWebStateRef,
      persistedWebState,
      persistedArtifactOpen,
      persistedChatOpen,
      catalog,
      setCatalog,
      projects,
      setProjects,
      projectId,
      setProjectId,
      project,
      setProject,
      nodes,
      setNodes,
      edges,
      setEdges,
      selectedNodeId,
      setSelectedNodeId,
      inspector,
      setInspector,
      newProjectTitle,
      setNewProjectTitle,
      newNodeForm,
      setNewNodeForm,
      projectSettingsForm,
      setProjectSettingsForm,
      outlineGuideForm,
      setOutlineGuideForm,
      outlineGuideBusy,
      setOutlineGuideBusy,
      runtimeSettings,
      setRuntimeSettings,
      runtimeProfiles,
      setRuntimeProfiles,
      activeRuntimeProfile,
      setActiveRuntimeProfile,
      newRuntimeProfile,
      setNewRuntimeProfile,
      renameRuntimeProfile,
      setRenameRuntimeProfile,
      llmPresets,
      setLlmPresets,
      runtimePresetTag,
      setRuntimePresetTag,
      sidebarTab,
      setSidebarTab,
      mainView,
      setMainView,
      storylineFilter,
      setStorylineFilter,
      zoom,
      setZoom,
      aiConfig,
      setAiConfig,
      aiResult,
      setAiResult,
      edgeMode,
      setEdgeMode,
      autoBindOnDrop,
      setAutoBindOnDrop,
      edgeSourceId,
      setEdgeSourceId,
      validationReport,
      setValidationReport,
      activities,
      setActivities,
      toasts,
      setToasts,
      modal,
      setModal,
      chatOpen,
      setChatOpen,
      chatViewScale,
      artifactOpen,
      setArtifactOpen,
      chatContextNodeId,
      setChatContextNodeId,
      artifactContextNodeId,
      setArtifactContextNodeId,
      chatInput,
      setChatInput,
      chatMessages,
      setChatMessages,
      chatBusy,
      setChatBusy,
      chatWorkflow,
      setChatWorkflow,
      artifactDiffSegments,
      setArtifactDiffSegments,
      artifactDiffNodeId,
      setArtifactDiffNodeId,
      collapsedGroupIds,
      setCollapsedGroupIds,
      ghostPlans,
      setGhostPlans,
      ghostArchive,
      setGhostArchive,
      expandedGhostIds,
      setExpandedGhostIds,
      selectedGhostIds,
      setSelectedGhostIds,
      retiringGhostIds,
      setRetiringGhostIds,
      ghostFusionBusy,
      setGhostFusionBusy,
      nodeFlowStates,
      setNodeFlowStates,
      insightData,
      setInsightData,
      insightBusy,
      setInsightBusy,
      insightError,
      setInsightError,
      insightHighlightNodeIds,
      setInsightHighlightNodeIds,
      modalResolverRef,
      nodesRef,
      viewportRef,
      contextMenuSuppressUntilRef,
      ghostClickSuppressUntilRef,
      chatLogRef,
      chatOutlineNodePlanRef
    } = deps;

    const outlineRequired = Boolean(projectId) && nodes.length === 0 && !hasProjectOutline(nodes);
    const workflowWelcomeText = t("web.workflow.welcome");

    function t(key, variables) {
      const text = catalog[key] || FALLBACK_TEXT[key] || key;
      return formatValue(text, variables);
    }

    function enumLabel(prefix, value) {
      const key = prefix + value;
      const text = t(key);
      return text === key ? value : text;
    }

    function nodeTypeLabel(value) {
      return enumLabel("web.option.node_type.", value);
    }

    function groupKindLabel(value) {
      return enumLabel("web.option.group_kind.", value);
    }

    function groupBindingLabel(value) {
      return enumLabel("web.option.group_binding.", value);
    }

    function nodeStatusLabel(value) {
      return enumLabel("web.option.node_status.", value);
    }

    function nodeIsSuggested(node) {
      const metadata = node && node.metadata && typeof node.metadata === "object" ? node.metadata : {};
      return Boolean(metadata.ai_suggested);
    }

    function isGroupCollapsed(groupId) {
      return collapsedGroupIds[groupId] !== false;
    }

    function toggleGroupCollapsed(groupId) {
      setCollapsedGroupIds(function (prev) {
        const current = prev[groupId] !== false;
        return Object.assign({}, prev, { [groupId]: !current });
      });
    }

    function hashString(value) {
      const text = String(value || "");
      let acc = 0;
      for (let index = 0; index < text.length; index += 1) {
        acc = (acc * 31 + text.charCodeAt(index)) % 3600;
      }
      return acc;
    }

    function storylineColor(storylineId) {
      const normalized = String(storylineId || "").trim();
      if (!normalized) {
        return "";
      }
      const hue = Math.floor(hashString(normalized) / 10);
      return "hsl(" + hue + ", 72%, 62%)";
    }

    function nodeContentOf(nodeId) {
      if (!nodeId) {
        return "";
      }
      const target = nodesRef.current.find(function (item) {
        return item.id === nodeId;
      });
      if (!target) {
        return "";
      }
      const metadata = target.metadata && typeof target.metadata === "object" ? target.metadata : {};
      const content = String(metadata.content || "").trim();
      if (content) {
        return content;
      }
      return String(metadata.summary || "").trim();
    }

    function hasProjectOutline(nodeList) {
      if (!Array.isArray(nodeList)) {
        return false;
      }
      return nodeList.some(function (item) {
        const metadata = item && item.metadata && typeof item.metadata === "object" ? item.metadata : {};
        return metadata.project_outline === true || String(metadata.outline_kind || "").trim() === "project_outline";
      });
    }

    function isMockProvider() {
      return String(runtimeSettings.llm_provider || "").trim().toLowerCase() === "mock";
    }

    const formatAgentTrace = function (trace) {
      return formatAgentTraceValue(trace, { t: t });
    };
    const buildDiffSegments = buildDiffSegmentsValue;
    const renderMarkdownPreview = function (text) {
      return renderMarkdownPreviewValue({
        h: h,
        text: text,
        emptyText: t("web.artifact.preview_empty")
      });
    };

    function startNodeFlow(nodeId, phases) {
      if (!nodeId || !Array.isArray(phases) || phases.length === 0) {
        return;
      }
      setNodeFlowStates(function (prev) {
        return Object.assign({}, prev, {
          [nodeId]: {
            phases: phases.slice(),
            index: 0,
            at: Date.now()
          }
        });
      });
    }

    function stopNodeFlow(nodeId) {
      if (!nodeId) {
        return;
      }
      setNodeFlowStates(function (prev) {
        if (!prev[nodeId]) {
          return prev;
        }
        const next = Object.assign({}, prev);
        delete next[nodeId];
        return next;
      });
    }

    const edgeDisplayLabel = edgeDisplayLabelValue;
    const compareEdgesByNarrativeOrder = compareEdgesByNarrativeOrderValue;
    const clampZoom = function (value) {
      return clampZoomValue(value, MIN_ZOOM, MAX_ZOOM);
    };

    function applyZoomDelta(delta) {
      setZoom(function (current) {
        return clampZoom(current + delta);
      });
    }

    function applyRuntimePayload(payload, options) {
      const opts = options || {};
      const config = payload && payload.config ? payload.config : payload;
      if (!config || typeof config !== "object") {
        return;
      }
      const nextSettings = {
        locale: String(config.locale || DEFAULT_LOCALE),
        llm_provider: String(config.llm_provider || "mock"),
        api_url: String(config.api_url || ""),
        api_key: String(config.api_key || ""),
        model_name: String(config.model_name || ""),
        auto_complete: asBoolean(config.auto_complete, true),
        think_switch: asBoolean(config.think_switch, false),
        think_depth: String(config.think_depth || "medium"),
        thinking_budget: Math.max(1, Math.floor(asNumber(config.thinking_budget, 2048))),
        web_search_enabled: asBoolean(config.web_search_enabled, false),
        web_search_context_size: String(config.web_search_context_size || "medium"),
        web_search_max_results: Math.max(1, Math.floor(asNumber(config.web_search_max_results, 5))),
        llm_request_timeout: Math.max(5, Math.floor(asNumber(config.llm_request_timeout, 90))),
        web_request_timeout_ms: Math.max(30000, Math.floor(asNumber(config.web_request_timeout_ms, 240000))),
        default_token_budget: Math.max(1, Math.floor(asNumber(config.default_token_budget, 2200))),
        default_workflow_mode: String(config.default_workflow_mode || "multi_agent"),
        web_host: String(config.web_host || "127.0.0.1"),
        web_port: Math.max(1, Math.floor(asNumber(config.web_port, 8765)))
      };
      setRuntimeSettings(nextSettings);
      if (Array.isArray(payload && payload.profiles)) {
        setRuntimeProfiles(payload.profiles);
      }
      if (payload && typeof payload.active_profile === "string") {
        setActiveRuntimeProfile(payload.active_profile);
      }
      if (opts.syncLocale && SUPPORTED_LOCALES.includes(nextSettings.locale) && locale !== nextSettings.locale) {
        setLocale(nextSettings.locale);
      }
      if (opts.syncAiDefaults) {
        setAiConfig({
          token_budget: String(nextSettings.default_token_budget),
          workflow_mode: nextSettings.default_workflow_mode
        });
      }
    }

    function pushToast(level, message) {
      const id = "toast_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 8);
      const entry = { id: id, level: level, message: message };
      setToasts(function (prev) {
        return prev.concat(entry).slice(-6);
      });
      window.setTimeout(function () {
        setToasts(function (prev) {
          return prev.filter(function (item) {
            return item.id !== id;
          });
        });
      }, 3200);
    }

    function addActivity(kind, message) {
      const item = {
        id: "act_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 8),
        kind: kind,
        message: message,
        at: new Date().toISOString()
      };
      setActivities(function (prev) {
        return [item].concat(prev).slice(0, 48);
      });
    }

    function aiRequestTimeoutMs() {
      const raw = Math.floor(asNumber(runtimeSettings.web_request_timeout_ms, 240000));
      if (!Number.isFinite(raw) || raw < 30000) {
        return 240000;
      }
      return Math.min(1200000, raw);
    }

    async function showModal(config) {
      return await new Promise(function (resolve) {
        modalResolverRef.current = resolve;
        setModal(
          Object.assign({}, config, {
            id: "modal_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 8),
            confirmText: config.confirmText || t("web.modal.confirm"),
            cancelText: config.cancelText || t("web.modal.cancel")
          })
        );
      });
    }

    function resolveModal(result) {
      const resolver = modalResolverRef.current;
      modalResolverRef.current = null;
      setModal(null);
      if (resolver) {
        resolver(result);
      }
    }

    async function showConfirm(title, body) {
      const result = await showModal({ mode: "confirm", title: title, body: body });
      return Boolean(result && result.confirmed);
    }

    async function showInput(title, body, placeholder, defaultValue) {
      const result = await showModal({
        mode: "input",
        title: title,
        body: body,
        placeholder: placeholder || "",
        defaultValue: defaultValue || ""
      });
      if (!result || !result.confirmed) {
        return null;
      }
      return String(result.value || "");
    }

    async function openTutorialModal() {
      await showModal({
        mode: "confirm",
        title: t("web.tutorial.title"),
        body: t("web.tutorial.body"),
        cancelText: t("web.tutorial.close"),
        confirmText: t("web.tutorial.confirm")
      });
    }

    function resolveErrorMessage(error) {
      return error instanceof Error ? error.message : String(error);
    }

    async function runApiDetailed(task, successMessage) {
      try {
        const response = await task();
        if (successMessage) {
          pushToast("ok", successMessage);
        }
        return { ok: true, data: response, error: "" };
      } catch (error) {
        const message = resolveErrorMessage(error);
        pushToast("error", t("web.toast.api_error", { message: message }));
        addActivity("error", message);
        return { ok: false, data: null, error: message };
      }
    }

    async function runApi(task, successMessage) {
      const result = await runApiDetailed(task, successMessage);
      return result.ok ? result.data : null;
    }

    function appendChatMessage(role, text, meta, extra) {
      const contextNodeId =
        extra && typeof extra.contextNodeId === "string" ? String(extra.contextNodeId || "").trim() : "";
      const entry = {
        id: "chat_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 8),
        role: role,
        text: String(text || ""),
        meta: meta || "",
        at: new Date().toISOString(),
        context_node_id: contextNodeId,
        diffSegments:
          extra && Array.isArray(extra.diffSegments)
            ? extra.diffSegments.slice(0, 2000)
            : []
      };
      setChatMessages(function (prev) {
        return prev.concat(entry).slice(-120);
      });
    }

    function openChatForNode(nodeId) {
      if (!nodeId) {
        return;
      }
      setArtifactOpen(true);
      setChatOpen(false);
      setChatContextNodeId(nodeId);
      setArtifactContextNodeId(nodeId);
      setSelectedNodeId(nodeId);
      setArtifactDiffSegments([]);
      pushToast("ok", t("web.artifact.opened", { node_id: nodeId }));
    }

    function applyNodeContentPatchLocal(nodeId, content) {
      if (!nodeId) {
        return;
      }
      const normalized = String(content || "");
      setNodes(function (prev) {
        return prev.map(function (item) {
          if (item.id !== nodeId) {
            return item;
          }
          const metadata = Object.assign(
            {},
            item.metadata && typeof item.metadata === "object" ? item.metadata : {}
          );
          metadata.content = normalized;
          metadata.summary = normalized.slice(0, 200);
          return Object.assign({}, item, {
            status: "generated",
            metadata: metadata
          });
        });
      });
    }

    const CHAT_MESSAGE_MAX_LEN = 3900;

    function compactChatLine(value, maxLen) {
      const source = String(value || "").replace(/\s+/g, " ").trim();
      const limit = Math.max(12, Math.floor(asNumber(maxLen, 160)));
      if (!source) {
        return "";
      }
      return source.length <= limit ? source : source.slice(0, Math.max(0, limit - 1)) + "…";
    }

    function buildOutlineChatMessageWithHistory(rawMessage) {
      const original = String(rawMessage || "").trim();
      if (!outlineRequired) {
        return original.slice(0, CHAT_MESSAGE_MAX_LEN);
      }
      const history = chatMessages.filter(function (item) {
        const contextId = String(item && item.context_node_id ? item.context_node_id : "").trim();
        const role = String(item && item.role ? item.role : "").trim().toLowerCase();
        const meta = String(item && item.meta ? item.meta : "");
        return !contextId && (role === "user" || role === "assistant") && !meta.includes("workflow_init");
      }).slice(-16);
      if (history.length === 0) {
        return original.slice(0, CHAT_MESSAGE_MAX_LEN);
      }
      const lines = history.map(function (item, index) {
        const role = String(item && item.role ? item.role : "user").toLowerCase() === "assistant" ? "assistant" : "user";
        return (
          String(index + 1) +
          ". [" +
          role +
          "] " +
          compactChatLine(item && item.text ? item.text : "", 220)
        );
      });
      const wrapped = [
        "[Conversation History]",
        lines.join("\n"),
        "",
        "[Current User Message]",
        original,
        "",
        "[Instructions]",
        "Continue this conversation and keep continuity with the history.",
        "Only when information is sufficient AND the user explicitly confirms form filling, append exactly one machine block:",
        "[OUTLINE_FORM_PREFILL]{\"ready\":true,\"goal\":\"...\",\"sync_context\":\"...\",\"specify\":\"...\",\"clarify_answers\":\"...\",\"plan_notes\":\"...\",\"constraints\":\"...\",\"tone\":\"...\"}[/OUTLINE_FORM_PREFILL]",
        "If either condition is not met, do not output this block."
      ].join("\n");
      return wrapped.slice(0, CHAT_MESSAGE_MAX_LEN);
    }

    function normalizeOutlinePrefillField(payload, keys) {
      for (let index = 0; index < keys.length; index += 1) {
        const key = keys[index];
        const value = payload && Object.prototype.hasOwnProperty.call(payload, key) ? payload[key] : "";
        if (Array.isArray(value)) {
          const merged = value
            .map(function (item) {
              return compactChatLine(item, 240);
            })
            .filter(Boolean)
            .slice(0, 10)
            .join("\n");
          if (merged) {
            return merged;
          }
          continue;
        }
        const text = String(value == null ? "" : value).trim();
        if (text) {
          return text;
        }
      }
      return "";
    }

    function parseOutlineFormPrefill(rawReply) {
      const text = String(rawReply || "");
      const matched = text.match(/\[OUTLINE_FORM_PREFILL\]\s*([\s\S]*?)\s*\[\/OUTLINE_FORM_PREFILL\]/i);
      if (!matched) {
        return {
          cleanText: text,
          payload: null
        };
      }
      const block = String(matched[1] || "").trim();
      const candidates = [block];
      const braceMatched = block.match(/\{[\s\S]*\}/);
      if (braceMatched) {
        candidates.push(String(braceMatched[0] || "").trim());
      }
      let parsed = null;
      for (let index = 0; index < candidates.length; index += 1) {
        try {
          parsed = JSON.parse(candidates[index]);
          if (parsed && typeof parsed === "object") {
            break;
          }
        } catch (error) {
          parsed = null;
        }
      }
      if (!parsed || typeof parsed !== "object") {
        const stripped = text.replace(matched[0], "").trim();
        return {
          cleanText: stripped || t("web.outline.prefill_detected"),
          payload: null
        };
      }
      const payload = {
        ready: asBoolean(parsed.ready, false),
        goal: normalizeOutlinePrefillField(parsed, ["goal", "story_goal", "target"]),
        sync_context: normalizeOutlinePrefillField(parsed, ["sync_context", "background", "facts"]),
        specify: normalizeOutlinePrefillField(parsed, ["specify", "scope", "requirements"]),
        clarify_answers: normalizeOutlinePrefillField(parsed, ["clarify_answers", "qa", "answers"]),
        plan_notes: normalizeOutlinePrefillField(parsed, ["plan_notes", "plan", "notes"]),
        constraints: normalizeOutlinePrefillField(parsed, ["constraints", "hard_constraints", "must_keep"]),
        tone: normalizeOutlinePrefillField(parsed, ["tone", "style", "voice"])
      };
      const hasContent = Boolean(
        payload.goal ||
          payload.sync_context ||
          payload.specify ||
          payload.clarify_answers ||
          payload.plan_notes ||
          payload.constraints ||
          payload.tone
      );
      const stripped = text.replace(matched[0], "").trim();
      return {
        cleanText: stripped || t("web.outline.prefill_detected"),
        payload: hasContent ? payload : null
      };
    }

    function isJsonPayload(text) {
      const source = String(text || "").trim();
      if (!source) {
        return false;
      }
      const first = source[0];
      const last = source[source.length - 1];
      if (!((first === "{" && last === "}") || (first === "[" && last === "]"))) {
        return false;
      }
      try {
        const parsed = JSON.parse(source);
        return Boolean(parsed && typeof parsed === "object");
      } catch (error) {
        return false;
      }
    }

    function filterStructuredAssistantText(rawText) {
      let text = String(rawText || "");
      if (!text.trim()) {
        return text;
      }
      text = text.replace(
        /\[[A-Z][A-Z0-9_:-]{2,}\][\s\S]*?\[\/[A-Z][A-Z0-9_:-]{2,}\]/g,
        "\n"
      );
      text = text.replace(/```([^\n`]*)\n?([\s\S]*?)```/g, function (match, lang, body) {
        const language = String(lang || "").trim().toLowerCase();
        const payload = String(body || "").trim();
        const structuredLang = language === "json" || language === "yaml" || language === "yml" || language === "xml";
        const structuredBody = isJsonPayload(payload) || /^<\?xml\b|^<\w+[\s>]/i.test(payload);
        return structuredLang || structuredBody ? "\n" : match;
      });
      if (isJsonPayload(text)) {
        return t("web.chat.structured_hidden");
      }
      const lines = text.split(/\r?\n/);
      const filteredLines = lines.filter(function (line) {
        const trimmed = String(line || "").trim();
        if (!trimmed) {
          return true;
        }
        if (/^[{}\[\],]+$/.test(trimmed)) {
          return false;
        }
        if (/^"[^"]+"\s*:\s*/.test(trimmed) || /^'[^']+'\s*:\s*/.test(trimmed)) {
          return false;
        }
        if (/^<\/?[A-Za-z][^>]*>$/.test(trimmed)) {
          return false;
        }
        if (/^(?:decision|goal|assistant_reply|options|outline_steps|metadata|content|summary)\s*:/i.test(trimmed)) {
          return false;
        }
        return true;
      });
      const cleaned = filteredLines.join("\n").replace(/\n{3,}/g, "\n\n").trim();
      return cleaned || t("web.chat.structured_hidden");
    }

    function hasOutlineFormFillConsent(rawMessage) {
      const source = String(rawMessage || "");
      const lowered = source.toLowerCase();
      const englishMarkers = [
        "confirm",
        "go ahead",
        "apply",
        "fill the form",
        "use this to fill",
        "write to form"
      ];
      const cjkMarkers = ["确认", "同意", "可以填", "填入表单", "写入表单", "确认填充", "埋めて", "確認して入力"];
      if (englishMarkers.some(function (item) { return lowered.includes(item); })) {
        return true;
      }
      return cjkMarkers.some(function (item) { return source.includes(item); });
    }

    function applyOutlineFormPrefill(payload) {
      const normalized = payload && typeof payload === "object" ? payload : {};
      setOutlineGuideForm(function (prev) {
        const next = Object.assign({}, prev);
        let changed = false;
        function assignIfPresent(key) {
          const value = compactChatLine(normalized[key], 2000);
          if (!value) {
            return;
          }
          if (String(next[key] || "").trim() === value) {
            return;
          }
          next[key] = value;
          changed = true;
        }
        assignIfPresent("goal");
        assignIfPresent("sync_context");
        assignIfPresent("specify");
        assignIfPresent("clarify_answers");
        assignIfPresent("plan_notes");
        assignIfPresent("constraints");
        assignIfPresent("tone");
        return changed ? next : prev;
      });
    }

    function outlinePrefillSummary(payload) {
      const picked = payload && typeof payload === "object" ? payload : {};
      const rows = [];
      if (picked.goal) {
        rows.push(t("web.outline.goal") + ": " + compactChatLine(picked.goal, 90));
      }
      if (picked.sync_context) {
        rows.push(t("web.outline.sync_context") + ": " + compactChatLine(picked.sync_context, 90));
      }
      if (picked.specify) {
        rows.push(t("web.outline.specify") + ": " + compactChatLine(picked.specify, 90));
      }
      if (picked.constraints) {
        rows.push(t("web.outline.constraints") + ": " + compactChatLine(picked.constraints, 90));
      }
      if (picked.tone) {
        rows.push(t("web.outline.tone") + ": " + compactChatLine(picked.tone, 90));
      }
      return rows.join("\n") || "-";
    }

    const OUTLINE_NODE_PLAN_MARKER = "workflow_outline_seed_v1";

    function parseLooseJsonObject(rawReply) {
      const raw = String(rawReply || "").trim();
      if (!raw) {
        return null;
      }
      const candidates = [];
      const fenced = raw.match(/```(?:json)?\s*[\s\S]*?```/gi) || [];
      fenced.forEach(function (block) {
        const cleaned = String(block)
          .replace(/^```(?:json)?\s*/i, "")
          .replace(/```$/i, "")
          .trim();
        if (cleaned) {
          candidates.push(cleaned);
        }
      });
      candidates.push(raw);
      const braceMatched = raw.match(/\{[\s\S]*\}/);
      if (braceMatched && String(braceMatched[0] || "").trim()) {
        candidates.push(String(braceMatched[0]).trim());
      }
      for (let index = 0; index < candidates.length; index += 1) {
        try {
          const parsed = JSON.parse(candidates[index]);
          if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
            return parsed;
          }
        } catch (error) {
          continue;
        }
      }
      return null;
    }

    function normalizeOutlineNodePlanIntent(rawReply) {
      const parsed = parseLooseJsonObject(rawReply);
      if (!parsed) {
        return {
          decision: "normal",
          assistantReply: ""
        };
      }
      const decisionRaw = String(parsed.decision || parsed.intent || parsed.action || "").trim().toLowerCase();
      const decision = decisionRaw === "need_confirm" || decisionRaw === "confirm_required" || decisionRaw === "create_outline_nodes"
        ? "need_confirm"
        : "normal";
      return {
        decision: decision,
        assistantReply: String(parsed.assistant_reply || parsed.reply || parsed.message || "").trim()
      };
    }

    function normalizeOutlineNodePlanConfirm(rawReply) {
      const parsed = parseLooseJsonObject(rawReply);
      if (!parsed) {
        return {
          confirmed: false,
          assistantReply: ""
        };
      }
      const rawConfirmed = parsed.confirmed;
      const confirmed =
        rawConfirmed === true ||
        String(rawConfirmed || "").trim().toLowerCase() === "true" ||
        String(rawConfirmed || "").trim().toLowerCase() === "yes" ||
        String(rawConfirmed || "").trim().toLowerCase() === "confirm";
      return {
        confirmed: confirmed,
        assistantReply: String(parsed.assistant_reply || parsed.reply || parsed.message || "").trim()
      };
    }

    function resolveOutlineSeedNode(contextNodeId) {
      const nodeList = Array.isArray(nodesRef.current) ? nodesRef.current : [];
      const ordered = [];
      const seen = {};

      function addById(nodeId) {
        const id = String(nodeId || "").trim();
        if (!id || seen[id]) {
          return;
        }
        const hit = nodeList.find(function (item) {
          return item.id === id;
        });
        if (!hit) {
          return;
        }
        seen[id] = true;
        ordered.push(hit);
      }

      addById(contextNodeId);
      addById(selectedNodeId);
      nodeList.forEach(function (item) {
        const metadata = item && item.metadata && typeof item.metadata === "object" ? item.metadata : {};
        if (metadata.ai_outline_seed || metadata.project_outline || String(metadata.outline_kind || "") === "project_outline") {
          addById(item.id);
        }
      });
      for (let index = 0; index < ordered.length; index += 1) {
        const item = ordered[index];
        const metadata = item && item.metadata && typeof item.metadata === "object" ? item.metadata : {};
        const outlineText = String(metadata.outline_markdown || "").trim();
        if (outlineText) {
          return item;
        }
      }
      return null;
    }

    function buildOutlineNodePlanIntentPrompt(userText, seedNode, contextNodeId) {
      const seedMeta = seedNode && seedNode.metadata && typeof seedNode.metadata === "object" ? seedNode.metadata : {};
      const outlineText = String(seedMeta.outline_markdown || "").trim();
      const scopedHistory = chatMessages
        .filter(function (item) {
          return String(item && item.context_node_id ? item.context_node_id : "").trim() === String(contextNodeId || "").trim();
        })
        .slice(-12)
        .map(function (item, index) {
          const role = String(item && item.role ? item.role : "").toLowerCase() === "assistant" ? "assistant" : "user";
          return String(index + 1) + ". [" + role + "] " + compactChatLine(item && item.text ? item.text : "", 220);
        });
      const wrapped = [
        "You are an intent judge for creating detailed-outline nodes in a novel graph.",
        "Decide whether the user's latest message should enter the detailed-outline node creation flow.",
        "Return strict JSON only:",
        "{\"decision\":\"need_confirm|normal\",\"assistant_reply\":\"...\"}",
        "Rules:",
        "1) need_confirm only when user intent is to continue from outline and create a sequence of next-outline nodes.",
        "2) If uncertain, choose normal.",
        "3) assistant_reply should be natural language. If need_confirm, ask for explicit confirmation first.",
        "",
        "[Seed Node]",
        "id=" + String(seedNode && seedNode.id ? seedNode.id : "-") + ", title=" + String(seedNode && seedNode.title ? seedNode.title : "-"),
        "",
        "[Seed Outline]",
        outlineText || "-",
        "",
        "[Context Chat History]",
        scopedHistory.join("\n") || "-",
        "",
        "[Current User Message]",
        String(userText || "")
      ].join("\n");
      return wrapped.slice(0, CHAT_MESSAGE_MAX_LEN);
    }

    function buildOutlineNodePlanConfirmPrompt(userText, pendingPayload, seedNode) {
      const seedMeta = seedNode && seedNode.metadata && typeof seedNode.metadata === "object" ? seedNode.metadata : {};
      const outlineText = String(seedMeta.outline_markdown || "").trim();
      const wrapped = [
        "You are a confirmation judge for detailed-outline node creation.",
        "Return strict JSON only:",
        "{\"confirmed\":true|false,\"assistant_reply\":\"...\"}",
        "Rules:",
        "1) confirmed=true only when current message clearly indicates user confirmation to proceed.",
        "2) If ambiguous, confirmed=false and ask for clear confirmation.",
        "",
        "[Pending Request]",
        String(pendingPayload && pendingPayload.request ? pendingPayload.request : "-"),
        "",
        "[Seed Node]",
        "id=" + String(seedNode && seedNode.id ? seedNode.id : "-") + ", title=" + String(seedNode && seedNode.title ? seedNode.title : "-"),
        "",
        "[Seed Outline]",
        outlineText || "-",
        "",
        "[Current User Message]",
        String(userText || "")
      ].join("\n");
      return wrapped.slice(0, CHAT_MESSAGE_MAX_LEN);
    }

    async function runOutlineNodePlanJudge(promptText) {
      const outcome = await runApiDetailed(
        function () {
          return apiRequest("/api/ai/chat", {
            method: "POST",
            timeout_ms: aiRequestTimeoutMs(),
            body: {
              project_id: projectId,
              node_id: null,
              message: String(promptText || ""),
              token_budget: Math.max(700, Math.floor(asNumber(aiConfig.token_budget, 2200) / 3))
            }
          });
        },
        null
      );
      if (!outcome.ok || !outcome.data) {
        return {
          ok: false,
          reply: ""
        };
      }
      return {
        ok: true,
        reply: String(outcome.data.reply || "")
      };
    }

    async function createOutlineDetailNodesFromSeed(seedNode, userRequest) {
      if (!seedNode || !projectId) {
        return {
          ok: false,
          count: 0
        };
      }
      const metadata = seedNode.metadata && typeof seedNode.metadata === "object" ? seedNode.metadata : {};
      const outlineText = String(metadata.outline_markdown || "").trim();
      const chapterBeats = Array.isArray(metadata.outline_chapter_beats)
        ? metadata.outline_chapter_beats.map(String).slice(0, 20)
        : [];
      if (!outlineText) {
        return {
          ok: false,
          count: 0
        };
      }
      const detailOutcome = await runApiDetailed(
        function () {
          return apiRequest("/api/ai/outline/detail_nodes", {
            method: "POST",
            timeout_ms: aiRequestTimeoutMs(),
            body: {
              project_id: projectId,
              outline_markdown: outlineText,
              chapter_beats: chapterBeats,
              user_request: String(userRequest || ""),
              mode: String(metadata.outline_mode || ""),
              token_budget: Math.max(1200, Math.floor(asNumber(aiConfig.token_budget, 2200))),
              max_nodes: 8
            }
          });
        },
        null
      );
      if (!detailOutcome.ok || !detailOutcome.data) {
        return {
          ok: false,
          count: 0
        };
      }
      const detailNodes = Array.isArray(detailOutcome.data.nodes)
        ? detailOutcome.data.nodes
            .map(function (item) {
              const raw = item && typeof item === "object" ? item : {};
              const title = String(raw.title || "").trim();
              const outline = String(raw.outline_markdown || "").trim();
              const summary = String(raw.summary || "").trim();
              if (!outline) {
                return null;
              }
              return {
                title: title,
                outline_markdown: outline,
                summary: summary || outline.replace(/\s+/g, " ").slice(0, 180)
              };
            })
            .filter(function (item) {
              return Boolean(item && item.outline_markdown);
            })
            .slice(0, 8)
        : [];
      if (detailNodes.length === 0) {
        return {
          ok: false,
          count: 0
        };
      }
      const created = [];
      const sourceX = asNumber(seedNode.pos_x, 120);
      const sourceY = asNumber(seedNode.pos_y, 120);
      for (let index = 0; index < detailNodes.length; index += 1) {
        const detail = detailNodes[index];
        const createdNode = await runApi(
          function () {
            return apiRequest("/api/projects/" + projectId + "/nodes", {
              method: "POST",
              body: {
                title: detail.title || t("web.outline.default_scene_prefix") + " " + String(index + 1),
                type: "chapter",
                status: "draft",
                storyline_id: seedNode.storyline_id || null,
                pos_x: sourceX + 260 + index * 230,
                pos_y: sourceY + 96,
                metadata: {
                  outline_markdown: String(detail.outline_markdown || ""),
                  summary: String(detail.summary || "").slice(0, 180),
                  ai_from_outline_seed: true,
                  ai_outline_seed_source: seedNode.id,
                  ai_outline_seed_marker: OUTLINE_NODE_PLAN_MARKER,
                  narrative_index: index + 1
                }
              }
            });
          },
          null
        );
        if (!createdNode) {
          return {
            ok: false,
            count: created.length
          };
        }
        created.push(createdNode);
      }
      if (created.length > 0) {
        await runApi(
          function () {
            return apiRequest("/api/projects/" + projectId + "/edges", {
              method: "POST",
              body: {
                source_id: seedNode.id,
                target_id: created[0].id,
                label: "next"
              }
            });
          },
          null
        );
      }
      for (let index = 1; index < created.length; index += 1) {
        await runApi(
          function () {
            return apiRequest("/api/projects/" + projectId + "/edges", {
              method: "POST",
              body: {
                source_id: created[index - 1].id,
                target_id: created[index].id,
                label: "next"
              }
            });
          },
          null
        );
      }
      await refreshProjectData(projectId, true);
      await validateGraph();
      if (created.length > 0) {
        setSelectedNodeId(created[0].id);
        setSidebarTab("node");
        setChatContextNodeId(created[0].id);
        setChatOpen(true);
        setArtifactOpen(false);
      }
      return {
        ok: true,
        count: created.length
      };
    }

    async function handleOutlineNodePlanChat(userText, contextNodeId) {
      if (!projectId || outlineRequired) {
        return false;
      }
      const ref = chatOutlineNodePlanRef && typeof chatOutlineNodePlanRef === "object" ? chatOutlineNodePlanRef : null;
      const pending = ref && ref.current && typeof ref.current === "object" ? ref.current : null;
      if (pending && String(pending.project_id || "") === String(projectId || "")) {
        const seedNode = resolveOutlineSeedNode(pending.source_node_id || contextNodeId);
        if (!seedNode) {
          ref.current = null;
          return false;
        }
        const confirmJudge = await runOutlineNodePlanJudge(
          buildOutlineNodePlanConfirmPrompt(userText, pending, seedNode)
        );
        const confirmResult = normalizeOutlineNodePlanConfirm(confirmJudge.reply);
        if (!confirmResult.confirmed) {
          appendChatMessage(
            "assistant",
            confirmResult.assistantReply || t("web.chat.outline_plan_waiting_confirm"),
            t("web.chat.route_label", { route: "outline_plan" }),
            { contextNodeId: contextNodeId }
          );
          return true;
        }
        const modalApproved = await showConfirm(
          t("web.chat.outline_plan_modal_title"),
          t("web.chat.outline_plan_modal_body", {
            node_title: String(seedNode.title || seedNode.id || "-"),
            request: String(pending.request || userText || "-")
          })
        );
        if (!modalApproved) {
          ref.current = null;
          appendChatMessage(
            "assistant",
            t("web.chat.outline_plan_cancelled"),
            t("web.chat.route_label", { route: "outline_plan" }),
            { contextNodeId: contextNodeId }
          );
          return true;
        }
        const creation = await createOutlineDetailNodesFromSeed(seedNode, String(pending.request || userText || ""));
        ref.current = null;
        if (!creation.ok || creation.count <= 0) {
          appendChatMessage(
            "assistant",
            t("web.chat.outline_plan_failed"),
            t("web.chat.route_label", { route: "outline_plan" }),
            { contextNodeId: contextNodeId }
          );
          pushToast("warn", t("web.chat.outline_plan_failed"));
          return true;
        }
        appendChatMessage(
          "assistant",
          t("web.chat.outline_plan_created", { count: String(creation.count) }),
          t("web.chat.route_label", { route: "outline_plan" }),
          { contextNodeId: contextNodeId }
        );
        pushToast("ok", t("web.chat.outline_plan_created", { count: String(creation.count) }));
        addActivity("success", "outline detail nodes created from chat request");
        return true;
      }

      const seedNode = resolveOutlineSeedNode(contextNodeId);
      if (!seedNode) {
        return false;
      }
      const intentJudge = await runOutlineNodePlanJudge(
        buildOutlineNodePlanIntentPrompt(userText, seedNode, contextNodeId)
      );
      if (!intentJudge.ok) {
        return false;
      }
      const intent = normalizeOutlineNodePlanIntent(intentJudge.reply);
      if (intent.decision !== "need_confirm") {
        return false;
      }
      if (ref) {
        ref.current = {
          project_id: projectId,
          source_node_id: seedNode.id,
          request: String(userText || ""),
          marker: OUTLINE_NODE_PLAN_MARKER
        };
      }
      appendChatMessage(
        "assistant",
        intent.assistantReply || t("web.chat.outline_plan_need_confirm"),
        t("web.chat.route_label", { route: "outline_plan" }),
        { contextNodeId: contextNodeId }
      );
      return true;
    }

    async function sendChatMessage() {
      if (!projectId) {
        pushToast("warn", t("web.toast.project_required"));
        return;
      }
      const text = chatInput.trim();
      if (!text || chatBusy) {
        return;
      }
      const contextNodeId = resolveActiveChatContext(chatContextNodeId, artifactContextNodeId);
      const plannerRequested = /(^|\s)@(?:plan|planner)\b/i.test(text);
      let messageForRequest = text;
      if (plannerRequested && contextNodeId) {
        messageForRequest = buildPlannerFeedbackMessage(contextNodeId, text);
      } else if (!contextNodeId && outlineRequired) {
        messageForRequest = buildOutlineChatMessageWithHistory(text);
      }
      appendChatMessage(
        "user",
        text,
        contextNodeId ? t("web.chat.context_node", { node_id: contextNodeId }) : t("web.chat.context_global"),
        { contextNodeId: contextNodeId }
      );
      setChatInput("");
      setChatBusy(true);
      const consumedByWorkflow = await handleWorkflowChat(text);
      if (consumedByWorkflow) {
        setChatBusy(false);
        return;
      }
      const consumedByOutlinePlan = await handleOutlineNodePlanChat(text, contextNodeId);
      if (consumedByOutlinePlan) {
        setChatBusy(false);
        return;
      }
      if (isMockProvider()) {
        const blocked = t("web.ai.mock_blocked");
        appendChatMessage("assistant", blocked, t("web.chat.route_label", { route: "blocked" }), {
          contextNodeId: contextNodeId
        });
        pushToast("warn", blocked);
        setChatBusy(false);
        return;
      }
      const beforeContent = nodeContentOf(contextNodeId);
      if (contextNodeId) {
        startNodeFlow(contextNodeId, ["running"]);
      }
      const chatOutcome = await runApiDetailed(
        function () {
          return apiRequest("/api/ai/chat", {
            method: "POST",
            timeout_ms: aiRequestTimeoutMs(),
            body: {
              project_id: projectId,
              node_id: contextNodeId || null,
              message: messageForRequest,
              token_budget: Math.max(1, Math.floor(asNumber(aiConfig.token_budget, 2200)))
            }
          });
        },
        null
      );
      setChatBusy(false);
      if (!chatOutcome.ok) {
        appendChatMessage(
          "assistant",
          t("web.chat.error_reply", { message: chatOutcome.error }),
          t("web.chat.route_label", { route: "error" }),
          { contextNodeId: contextNodeId }
        );
        if (contextNodeId) {
          stopNodeFlow(contextNodeId);
        }
        return;
      }
      const payload = chatOutcome.data;
      if (!payload) {
        if (contextNodeId) {
          stopNodeFlow(contextNodeId);
        }
        return;
      }
      const route = String(payload.route || "auto");
      const bypassed = Boolean(payload.review_bypassed);
      let meta = t("web.chat.route_label", { route: route });
      if (bypassed) {
        meta += " · " + t("web.chat.review_bypassed");
      }
      const replyTextRaw = String(payload.reply || "");
      const prefillParsed = !contextNodeId && outlineRequired
        ? parseOutlineFormPrefill(replyTextRaw)
        : { cleanText: replyTextRaw, payload: null };
      const replyText = String(prefillParsed.cleanText || "");
      const displayReplyText = filterStructuredAssistantText(replyText);
      let diffSegments = [];
      if (route === "writer" && contextNodeId) {
        diffSegments = buildDiffSegments(beforeContent, replyText);
        applyNodeContentPatchLocal(contextNodeId, replyText);
      }
      setArtifactDiffNodeId(nextArtifactDiffNodeId(route, contextNodeId));
      setArtifactDiffSegments(diffSegments);
      appendChatMessage("assistant", displayReplyText, meta, {
        diffSegments: diffSegments,
        contextNodeId: contextNodeId
      });
      const options = Array.isArray(payload.suggested_options) ? payload.suggested_options : [];
      if (route === "planner" && contextNodeId && options.length > 0) {
        const result = refreshGhostPlansForSource(contextNodeId, options, {
          feedbackLoop: plannerRequested
        });
        if (result.totalRoutes > 0) {
          pushToast(
            "ok",
            t("web.chat.suggested_updated", {
              count: result.totalRoutes,
              locked: result.preservedLockedRoutes
            })
          );
        }
      }
      if (!contextNodeId && outlineRequired && prefillParsed.payload) {
        const payloadReady = Boolean(prefillParsed.payload.ready);
        const consented = payloadReady || hasOutlineFormFillConsent(text);
        if (consented) {
          const approved = await showConfirm(
            t("web.outline.prefill_apply_title"),
            t("web.outline.prefill_apply_body", {
              summary: outlinePrefillSummary(prefillParsed.payload)
            })
          );
          if (approved) {
            applyOutlineFormPrefill(prefillParsed.payload);
            pushToast("ok", t("web.outline.prefill_applied"));
            addActivity("success", "outline guide form prefilled from confirmed chat");
          }
        }
      }
      addActivity("info", "ai chat route=" + route + ", node=" + (contextNodeId || "global"));
      await refreshProjectData(projectId, true);
      await validateGraph();
      if (contextNodeId) {
        stopNodeFlow(contextNodeId);
      }
    }

    const projectActionHandlers = createProjectActionHandlersValue({
      SUPPORTED_LOCALES: SUPPORTED_LOCALES,
      DEFAULT_LOCALE: DEFAULT_LOCALE,
      runApi: runApi,
      runApiDetailed: runApiDetailed,
      apiRequest: apiRequest,
      configActions: configActions,
      apiActions: apiActions,
      applyRuntimePayload: applyRuntimePayload,
      addActivity: addActivity,
      setCatalog: setCatalog,
      setLlmPresets: setLlmPresets,
      setRuntimePresetTag: setRuntimePresetTag,
      llmPresets: llmPresets,
      setRuntimeSettings: setRuntimeSettings,
      asBoolean: asBoolean,
      pushToast: pushToast,
      t: t,
      projectId: projectId,
      setProjects: setProjects,
      setProjectId: setProjectId,
      setProject: setProject,
      setNodes: setNodes,
      setEdges: setEdges,
      setSelectedNodeId: setSelectedNodeId,
      setValidationReport: setValidationReport,
      setGhostPlans: setGhostPlans,
      setExpandedGhostIds: setExpandedGhostIds,
      setSelectedGhostIds: setSelectedGhostIds,
      setRetiringGhostIds: setRetiringGhostIds,
      setNodeFlowStates: setNodeFlowStates,
      selectedNodeId: selectedNodeId,
      setInsightData: setInsightData,
      setInsightError: setInsightError,
      setInsightBusy: setInsightBusy,
      viewportRef: viewportRef,
      nodesRef: nodesRef,
      nodeRenderSize: nodeRenderSize,
      zoom: zoom,
      asNumber: asNumber,
      setInsightHighlightNodeIds: setInsightHighlightNodeIds,
      setMainView: setMainView,
      setSidebarTab: setSidebarTab,
      showInput: showInput,
      project: project,
      newProjectTitle: newProjectTitle,
      setNewProjectTitle: setNewProjectTitle,
      isMockProvider: isMockProvider,
      outlineGuideForm: outlineGuideForm,
      setOutlineGuideBusy: setOutlineGuideBusy,
      aiRequestTimeoutMs: aiRequestTimeoutMs,
      aiConfig: aiConfig,
      setOutlineGuideForm: setOutlineGuideForm,
      setChatContextNodeId: setChatContextNodeId,
      setChatOpen: setChatOpen,
      setArtifactOpen: setArtifactOpen,
      showConfirm: showConfirm,
      projectSettingsForm: projectSettingsForm,
      setProjectSettingsForm: setProjectSettingsForm
    });
    const loadLocaleCatalog = projectActionHandlers.loadLocaleCatalog;
    const loadRuntimeSettings = projectActionHandlers.loadRuntimeSettings;
    const loadLlmPresets = projectActionHandlers.loadLlmPresets;
    const applyRuntimePreset = projectActionHandlers.applyRuntimePreset;
    const refreshProjects = projectActionHandlers.refreshProjects;
    const refreshProjectData = projectActionHandlers.refreshProjectData;
    const loadInsights = projectActionHandlers.loadInsights;
    const focusNodeOnViewport = projectActionHandlers.focusNodeOnViewport;
    const openNodeFromInsight = projectActionHandlers.openNodeFromInsight;
    const validateGraph = projectActionHandlers.validateGraph;
    const exportGraph = projectActionHandlers.exportGraph;
    const createSnapshot = projectActionHandlers.createSnapshot;
    const rollbackProject = projectActionHandlers.rollbackProject;
    const createProject = projectActionHandlers.createProject;
    const runOutlineGuide = projectActionHandlers.runOutlineGuide;
    const saveOutlineNodeFromGuide = projectActionHandlers.saveOutlineNodeFromGuide;
    const deleteProject = projectActionHandlers.deleteProject;
    const toggleAllowCycles = projectActionHandlers.toggleAllowCycles;
    const saveProjectSettings = projectActionHandlers.saveProjectSettings;

    const workflowActionHandlers = createWorkflowActionHandlersValue({
      projectId: projectId,
      runApi: runApi,
      runApiDetailed: runApiDetailed,
      apiRequest: apiRequest,
      t: t,
      parseWorkflowModeValue: parseWorkflowModeValue,
      isWorkflowBackgroundConfirmedValue: isWorkflowBackgroundConfirmedValue,
      isWorkflowOutlineConfirmedValue: isWorkflowOutlineConfirmedValue,
      parseBeatListValue: parseBeatListValue,
      beatTitleValue: beatTitleValue,
      pushToast: pushToast,
      refreshProjectData: refreshProjectData,
      validateGraph: validateGraph,
      setSelectedNodeId: setSelectedNodeId,
      setSidebarTab: setSidebarTab,
      setChatContextNodeId: setChatContextNodeId,
      setChatOpen: setChatOpen,
      setArtifactOpen: setArtifactOpen,
      setChatWorkflow: setChatWorkflow,
      setOutlineGuideField: setOutlineGuideField,
      setOutlineGuideForm: setOutlineGuideForm,
      outlineGuideForm: outlineGuideForm,
      aiConfig: aiConfig,
      asNumber: asNumber,
      aiRequestTimeoutMs: aiRequestTimeoutMs,
      appendChatMessage: appendChatMessage,
      outlineRequired: outlineRequired,
      chatContextNodeId: chatContextNodeId,
      chatWorkflow: chatWorkflow,
      chatMessages: chatMessages
    });
    const materializeWorkflowGraphPlan = workflowActionHandlers.materializeWorkflowGraphPlan;
    const saveWorkflowOutlineNode = workflowActionHandlers.saveWorkflowOutlineNode;
    const handleWorkflowChat = workflowActionHandlers.handleWorkflowChat;

    const ghostActionHandlers = createGhostActionHandlersValue({
      nodesRef: nodesRef,
      nodeRenderSize: nodeRenderSize,
      asNumber: asNumber,
      t: t,
      pickGhostOutlineSteps: pickGhostOutlineSteps,
      normalizeGhostSentiment: normalizeGhostSentiment,
      inferGhostSentimentFromText: inferGhostSentimentFromText,
      ghostIdWithSeed: ghostIdWithSeed,
      ghostOutlineTextValue: ghostOutlineTextValue,
      sentimentToneColorValue: sentimentToneColorValue,
      normalizeGhostOutlineSteps: normalizeGhostOutlineSteps,
      safeArray: safeArray,
      setGhostArchive: setGhostArchive,
      ghostArchive: ghostArchive,
      setGhostPlans: setGhostPlans,
      setExpandedGhostIds: setExpandedGhostIds,
      pushToast: pushToast,
      setSelectedGhostIds: setSelectedGhostIds,
      projectId: projectId,
      ghostFusionBusy: ghostFusionBusy,
      selectedGhostIds: selectedGhostIds,
      ghostPlans: ghostPlans,
      aiConfig: aiConfig,
      runApiDetailed: runApiDetailed,
      apiRequest: apiRequest,
      aiRequestTimeoutMs: aiRequestTimeoutMs,
      setGhostFusionBusy: setGhostFusionBusy,
      addActivity: addActivity,
      runApi: runApi,
      validateGraph: validateGraph,
      refreshProjectData: refreshProjectData,
      setRetiringGhostIds: setRetiringGhostIds,
      nodeIsSuggested: nodeIsSuggested,
      nodeMetadataObject: nodeMetadataObjectValue,
      apiActions: apiActions,
      pruneGhostStateMapValue: pruneGhostStateMapValue
    });
    const createGhostPlansFromOptions = ghostActionHandlers.createGhostPlansFromOptions;
    const ghostOutlineText = ghostActionHandlers.ghostOutlineText;
    const sentimentToneColor = ghostActionHandlers.sentimentToneColor;
    const pruneGhostStateMap = ghostActionHandlers.pruneGhostStateMap;
    const restoreGhostFromArchive = ghostActionHandlers.restoreGhostFromArchive;
    const removeGhostArchiveItem = ghostActionHandlers.removeGhostArchiveItem;
    const clearGhostArchiveForProject = ghostActionHandlers.clearGhostArchiveForProject;
    const toggleGhostPreview = ghostActionHandlers.toggleGhostPreview;
    const toggleGhostSelection = ghostActionHandlers.toggleGhostSelection;
    const toggleGhostLock = ghostActionHandlers.toggleGhostLock;
    const buildPlannerFeedbackMessage = ghostActionHandlers.buildPlannerFeedbackMessage;
    const refreshGhostPlansForSource = ghostActionHandlers.refreshGhostPlansForSource;
    const fuseSelectedGhostPlans = ghostActionHandlers.fuseSelectedGhostPlans;
    const adoptGhostPlan = ghostActionHandlers.adoptGhostPlan;
    const previewGhostPlan = ghostActionHandlers.previewGhostPlan;
    const deleteGhostRoute = ghostActionHandlers.deleteGhostRoute;
    const acceptSuggestedNode = ghostActionHandlers.acceptSuggestedNode;
    const clearSuggestedNodes = ghostActionHandlers.clearSuggestedNodes;

    const nodeActionHandlers = createNodeActionHandlersValue({
      projectId: projectId,
      outlineRequired: outlineRequired,
      pushToast: pushToast,
      t: t,
      setSidebarTab: setSidebarTab,
      newNodeForm: newNodeForm,
      NODE_WIDTH: NODE_WIDTH,
      NODE_HEIGHT: NODE_HEIGHT,
      asNumber: asNumber,
      runApi: runApi,
      runApiDetailed: runApiDetailed,
      apiRequest: apiRequest,
      apiActions: apiActions,
      setNewNodeForm: setNewNodeForm,
      setSelectedNodeId: setSelectedNodeId,
      addActivity: addActivity,
      refreshProjectData: refreshProjectData,
      selectedNodeId: selectedNodeId,
      inspector: inspector,
      applyGroupBinding: applyGroupBindingValue,
      arrangeGroupChildren: arrangeGroupChildren,
      clearSuggestedNodes: clearSuggestedNodes,
      showConfirm: showConfirm,
      nodes: nodes,
      edges: edges,
      showInput: showInput,
      acceptSuggestedNode: acceptSuggestedNode,
      getNodeById: function () {
        return nodeById;
      },
      compareEdgesByNarrativeOrder: compareEdgesByNarrativeOrder,
      validateGraph: validateGraph,
      aiRequestTimeoutMs: aiRequestTimeoutMs,
      isMockProvider: isMockProvider,
      setAiResult: setAiResult,
      aiConfig: aiConfig,
      startNodeFlow: startNodeFlow,
      stopNodeFlow: stopNodeFlow,
      formatAgentTrace: formatAgentTrace
    });
    const createNode = nodeActionHandlers.createNode;
    const saveInspector = nodeActionHandlers.saveInspector;
    const deleteNode = nodeActionHandlers.deleteNode;
    const deleteEdge = nodeActionHandlers.deleteEdge;
    const createEdge = nodeActionHandlers.createEdge;
    const reorderEdge = nodeActionHandlers.reorderEdge;
    const runAi = nodeActionHandlers.runAi;

    function onNodeClick(nodeId) {
      if (!edgeMode) {
        setSelectedNodeId(nodeId);
        return;
      }

      if (!edgeSourceId) {
        setEdgeSourceId(nodeId);
        pushToast("ok", t("web.toast.edge_source_set", { node_id: nodeId }));
        return;
      }

      if (edgeSourceId === nodeId) {
        setEdgeSourceId("");
        pushToast("warn", t("web.toast.edge_source_reset"));
        return;
      }

      const sourceId = edgeSourceId;
      setEdgeSourceId("");
      pushToast("ok", t("web.canvas.edge_pick_target", { node_id: nodeId }));
      void createEdge(sourceId, nodeId);
    }

    const nodeMetadataObject = nodeMetadataObjectValue;
    const readGroupBinding = readGroupBindingValue;
    const applyGroupBinding = applyGroupBindingValue;
    const sceneRenderSizeByMetadata = function (metadata) {
      return sceneRenderSizeByMetadataValue(metadata, {
        asNumber: asNumber,
        nodeMinWidth: NODE_MIN_WIDTH,
        nodeMinHeight: NODE_MIN_HEIGHT,
        nodeWidth: NODE_WIDTH,
        nodeHeight: NODE_HEIGHT
      });
    };
    const groupRenderSizeByMetadata = function (metadata) {
      return groupRenderSizeByMetadataValue(metadata, {
        asNumber: asNumber,
        groupMinWidth: GROUP_MIN_WIDTH,
        groupMinHeight: GROUP_MIN_HEIGHT
      });
    };
    const findContainingGroupId = function (node, allNodes) {
      return findContainingGroupIdValue(node, allNodes, {
        asNumber: asNumber,
        nodeMetadataObject: nodeMetadataObject,
        groupRenderSizeByMetadata: groupRenderSizeByMetadata,
        nodeRenderSize: nodeRenderSize
      });
    };

    async function arrangeGroupChildren(groupId) {
      if (!projectId || !groupId) {
        return;
      }
      const snapshot = nodesRef.current.slice();
      const groupNode = snapshot.find(function (item) {
        return item.id === groupId && item.type === "group";
      });
      if (!groupNode) {
        return;
      }
      const groupMeta = nodeMetadataObject(groupNode);
      const currentSize = groupRenderSizeByMetadata(groupMeta);
      const boundChildren = snapshot.filter(function (item) {
        if (item.type === "group") {
          return false;
        }
        const binding = readGroupBinding(nodeMetadataObject(item));
        return binding.binding === "bound" && binding.parentId === groupId;
      });
      if (boundChildren.length === 0) {
        return;
      }
      const orderedChildren = boundChildren.slice().sort(function (left, right) {
        const ly = asNumber(left.pos_y, 0);
        const ry = asNumber(right.pos_y, 0);
        if (ly !== ry) {
          return ly - ry;
        }
        const lx = asNumber(left.pos_x, 0);
        const rx = asNumber(right.pos_x, 0);
        if (lx !== rx) {
          return lx - rx;
        }
        return String(left.id).localeCompare(String(right.id));
      });
      const childrenLayout = orderedChildren.map(function (child) {
        return {
          child: child,
          size: nodeRenderSize(child)
        };
      });

      function buildRows(groupWidth) {
        const innerWidth = Math.max(1, groupWidth - GROUP_LAYOUT_PADDING_X * 2);
        const rows = [];
        let currentItems = [];
        let currentWidth = 0;
        let currentHeight = 0;
        childrenLayout.forEach(function (entry) {
          const itemWidth = Math.round(entry.size.width);
          const itemHeight = Math.round(entry.size.height);
          const nextWidth = currentItems.length === 0 ? itemWidth : currentWidth + GROUP_LAYOUT_GAP_X + itemWidth;
          if (currentItems.length > 0 && nextWidth > innerWidth) {
            rows.push({
              items: currentItems,
              width: currentWidth,
              height: currentHeight
            });
            currentItems = [entry];
            currentWidth = itemWidth;
            currentHeight = itemHeight;
            return;
          }
          currentItems.push(entry);
          currentWidth = nextWidth;
          currentHeight = Math.max(currentHeight, itemHeight);
        });
        if (currentItems.length > 0) {
          rows.push({
            items: currentItems,
            width: currentWidth,
            height: currentHeight
          });
        }
        return rows;
      }

      function rowsHeight(rows) {
        if (rows.length === 0) {
          return 0;
        }
        return (
          rows.reduce(function (sum, row) {
            return sum + row.height;
          }, 0) +
          Math.max(0, rows.length - 1) * GROUP_LAYOUT_GAP_Y
        );
      }

      let nextGroupWidth = currentSize.width;
      let rows = buildRows(nextGroupWidth);
      const firstPassMaxWidth = rows.reduce(function (maxWidth, row) {
        return Math.max(maxWidth, row.width);
      }, 0);
      const requiredWidth = Math.max(GROUP_MIN_WIDTH, firstPassMaxWidth + GROUP_LAYOUT_PADDING_X * 2);
      if (requiredWidth > nextGroupWidth) {
        nextGroupWidth = requiredWidth;
        rows = buildRows(nextGroupWidth);
      }
      const contentHeight = rowsHeight(rows);
      const requiredHeight = Math.max(GROUP_MIN_HEIGHT, contentHeight + GROUP_LAYOUT_PADDING_Y * 2);
      const nextGroupHeight = Math.max(currentSize.height, requiredHeight);
      const groupPatchMetadata = Object.assign({}, groupMeta);
      groupPatchMetadata.group_width = Math.round(nextGroupWidth);
      groupPatchMetadata.group_height = Math.round(nextGroupHeight);

      const updates = [];
      if (
        Math.round(asNumber(groupMeta.group_width, currentSize.width)) !== Math.round(nextGroupWidth) ||
        Math.round(asNumber(groupMeta.group_height, currentSize.height)) !== Math.round(nextGroupHeight)
      ) {
        updates.push(
          apiRequest("/api/projects/" + projectId + "/nodes/" + groupId, {
            method: "PUT",
            body: { metadata: groupPatchMetadata }
          })
        );
      }
      const groupLeft = asNumber(groupNode.pos_x, 0);
      const groupTop = asNumber(groupNode.pos_y, 0);
      const startY = Math.round(groupTop + Math.max(GROUP_LAYOUT_PADDING_Y, (nextGroupHeight - contentHeight) / 2));
      let cursorY = startY;
      rows.forEach(function (row) {
        const startX = Math.round(groupLeft + Math.max(GROUP_LAYOUT_PADDING_X, (nextGroupWidth - row.width) / 2));
        let cursorX = startX;
        row.items.forEach(function (entry) {
          const child = entry.child;
          const childSize = entry.size;
          const targetX = Math.round(cursorX);
          const targetY = Math.round(cursorY + Math.max(0, (row.height - childSize.height) / 2));
          if (
            Math.round(asNumber(child.pos_x, 0)) !== targetX ||
            Math.round(asNumber(child.pos_y, 0)) !== targetY
          ) {
            updates.push(
              apiRequest("/api/projects/" + projectId + "/nodes/" + child.id, {
                method: "PUT",
                body: {
                  pos_x: targetX,
                  pos_y: targetY
                }
              })
            );
          }
          cursorX += childSize.width + GROUP_LAYOUT_GAP_X;
        });
        cursorY += row.height + GROUP_LAYOUT_GAP_Y;
      });
      if (updates.length === 0) {
        return;
      }
      const result = await runApi(function () {
        return Promise.all(updates);
      }, null);
      if (!result) {
        await refreshProjectData(projectId, true);
        return;
      }
      await refreshProjectData(projectId, true);
      addActivity("info", "group arranged: " + groupId + " (" + orderedChildren.length + " children, " + rows.length + " rows)");
    }

    function beginDrag(event, node) {
      if (event.button !== 0) {
        return;
      }
      if (edgeMode) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();

      const dragState = {
        nodeId: node.id,
        startClientX: event.clientX,
        startClientY: event.clientY,
        startX: asNumber(node.pos_x, 0),
        startY: asNumber(node.pos_y, 0),
        scale: Math.max(0.01, zoom),
        moved: false
      };

      function onMove(moveEvent) {
        const dx = (moveEvent.clientX - dragState.startClientX) / dragState.scale;
        const dy = (moveEvent.clientY - dragState.startClientY) / dragState.scale;
        const nextX = Math.round(dragState.startX + dx);
        const nextY = Math.round(dragState.startY + dy);
        dragState.moved = dragState.moved || Math.abs(dx) > 5 || Math.abs(dy) > 5;

        setNodes(function (prev) {
          return prev.map(function (item) {
            if (item.id !== dragState.nodeId) {
              return item;
            }
            return Object.assign({}, item, { pos_x: nextX, pos_y: nextY });
          });
        });
      }

      async function onUp() {
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);

        if (!dragState.moved || !projectId) {
          return;
        }

        const movedNode = nodesRef.current.find(function (item) {
          return item.id === dragState.nodeId;
        });
        if (!movedNode) {
          return;
        }
        const movedMetadata = nodeMetadataObject(movedNode);
        const bindingInfo = readGroupBinding(movedMetadata);
        const arrangeGroupIds = new Set();
        const patch = {
          pos_x: movedNode.pos_x,
          pos_y: movedNode.pos_y
        };
        if (movedNode.type !== "group") {
          if (autoBindOnDrop) {
            const startSnapshot = Object.assign({}, movedNode, {
              pos_x: dragState.startX,
              pos_y: dragState.startY
            });
            const startGroupId = findContainingGroupId(startSnapshot, nodesRef.current);
            const matchedGroupId = findContainingGroupId(movedNode, nodesRef.current);
            let nextBinding = bindingInfo.binding;
            let nextParentId = bindingInfo.parentId;
            if (bindingInfo.binding === "bound") {
              if (matchedGroupId) {
                nextBinding = "bound";
                nextParentId = matchedGroupId;
              } else {
                nextBinding = "independent";
                nextParentId = "";
              }
            } else {
              const movedIntoNewGroup = Boolean(matchedGroupId) && matchedGroupId !== startGroupId;
              const movedOutsideToGroup = !startGroupId && Boolean(matchedGroupId);
              if (movedIntoNewGroup || movedOutsideToGroup) {
                const targetGroup = nodesRef.current.find(function (item) {
                  return item.id === matchedGroupId && item.type === "group";
                });
                const nodeTitle = String(movedNode.title || movedNode.id || "").trim() || movedNode.id;
                const groupTitle = targetGroup
                  ? String(targetGroup.title || targetGroup.id || "").trim() || targetGroup.id
                  : String(matchedGroupId || "");
                const confirmed = await showConfirm(
                  t("web.bind_node_modal.title"),
                  t("web.bind_node_modal.body", {
                    node_title: nodeTitle,
                    group_title: groupTitle
                  })
                );
                if (confirmed) {
                  nextBinding = "bound";
                  nextParentId = matchedGroupId;
                } else {
                  nextBinding = "independent";
                  nextParentId = "";
                }
              } else {
                nextBinding = "independent";
                nextParentId = "";
              }
            }
            if (bindingInfo.binding === "bound" && bindingInfo.parentId) {
              arrangeGroupIds.add(bindingInfo.parentId);
            }
            if (nextBinding === "bound" && nextParentId) {
              arrangeGroupIds.add(nextParentId);
            }
            if (nextBinding !== bindingInfo.binding || nextParentId !== bindingInfo.parentId) {
              patch.metadata = applyGroupBinding(movedMetadata, nextBinding, nextParentId);
            }
          }
        }

        const result = await runApi(
          function () {
            return apiRequest("/api/projects/" + projectId + "/nodes/" + dragState.nodeId, {
              method: "PUT",
              body: patch
            });
          },
          null
        );

        if (!result) {
          await refreshProjectData(projectId, true);
          return;
        }
        addActivity(
          "info",
          "node moved: " + dragState.nodeId + " => (" + movedNode.pos_x + ", " + movedNode.pos_y + ")"
        );
        if (movedNode.type === "group") {
          await arrangeGroupChildren(movedNode.id);
        } else if (arrangeGroupIds.size > 0) {
          const orderedGroupIds = Array.from(arrangeGroupIds);
          for (let index = 0; index < orderedGroupIds.length; index += 1) {
            await arrangeGroupChildren(orderedGroupIds[index]);
          }
        }
      }

      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    }

    function beginGhostDrag(event, ghostPlan) {
      if (event.button !== 0) {
        return;
      }
      if (!ghostPlan || !ghostPlan.id) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();

      const dragState = {
        ghostId: ghostPlan.id,
        startClientX: event.clientX,
        startClientY: event.clientY,
        startX: asNumber(ghostPlan.pos_x, 0),
        startY: asNumber(ghostPlan.pos_y, 0),
        scale: Math.max(0.01, zoom),
        moved: false
      };

      function onMove(moveEvent) {
        const dx = (moveEvent.clientX - dragState.startClientX) / dragState.scale;
        const dy = (moveEvent.clientY - dragState.startClientY) / dragState.scale;
        const nextX = Math.round(dragState.startX + dx);
        const nextY = Math.round(dragState.startY + dy);
        dragState.moved = dragState.moved || Math.abs(dx) > 2 || Math.abs(dy) > 2;

        setGhostPlans(function (prev) {
          return prev.map(function (item) {
            if (item.id !== dragState.ghostId) {
              return item;
            }
            return Object.assign({}, item, { pos_x: nextX, pos_y: nextY });
          });
        });
      }

      function onUp() {
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
        if (dragState.moved) {
          ghostClickSuppressUntilRef.current = Date.now() + 220;
        }
      }

      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    }

    function beginNodeResize(event, node) {
      if (event.button !== 0) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      const isGroup = node.type === "group";
      const metadata = nodeMetadataObject(node);
      const startSize = isGroup ? groupRenderSizeByMetadata(metadata) : sceneRenderSizeByMetadata(metadata);
      const resizeState = {
        nodeId: node.id,
        isGroup: isGroup,
        startClientX: event.clientX,
        startClientY: event.clientY,
        startWidth: startSize.width,
        startHeight: startSize.height,
        scale: Math.max(0.01, zoom),
        moved: false
      };

      function onMove(moveEvent) {
        const dx = (moveEvent.clientX - resizeState.startClientX) / resizeState.scale;
        const dy = (moveEvent.clientY - resizeState.startClientY) / resizeState.scale;
        const nextWidth = Math.max(
          resizeState.isGroup ? GROUP_MIN_WIDTH : NODE_MIN_WIDTH,
          Math.round(resizeState.startWidth + dx)
        );
        const nextHeight = Math.max(
          resizeState.isGroup ? GROUP_MIN_HEIGHT : NODE_MIN_HEIGHT,
          Math.round(resizeState.startHeight + dy)
        );
        resizeState.moved = resizeState.moved || Math.abs(dx) > 2 || Math.abs(dy) > 2;
        setNodes(function (prev) {
          return prev.map(function (item) {
            if (item.id !== resizeState.nodeId) {
              return item;
            }
            const nextMeta = nodeMetadataObject(item);
            if (resizeState.isGroup) {
              nextMeta.group_width = nextWidth;
              nextMeta.group_height = nextHeight;
            } else {
              nextMeta.node_width = nextWidth;
              nextMeta.node_height = nextHeight;
            }
            return Object.assign({}, item, { metadata: nextMeta });
          });
        });
      }

      async function onUp() {
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
        if (!resizeState.moved || !projectId) {
          return;
        }
        const resizedNode = nodesRef.current.find(function (item) {
          return item.id === resizeState.nodeId;
        });
        if (!resizedNode) {
          return;
        }
        const nextMeta = nodeMetadataObject(resizedNode);
        if (resizeState.isGroup) {
          nextMeta.group_width = Math.max(
            GROUP_MIN_WIDTH,
            Math.round(asNumber(nextMeta.group_width, resizeState.startWidth))
          );
          nextMeta.group_height = Math.max(
            GROUP_MIN_HEIGHT,
            Math.round(asNumber(nextMeta.group_height, resizeState.startHeight))
          );
        } else {
          nextMeta.node_width = Math.max(
            NODE_MIN_WIDTH,
            Math.round(asNumber(nextMeta.node_width, resizeState.startWidth))
          );
          nextMeta.node_height = Math.max(
            NODE_MIN_HEIGHT,
            Math.round(asNumber(nextMeta.node_height, resizeState.startHeight))
          );
        }
        const result = await runApi(
          function () {
            return apiRequest("/api/projects/" + projectId + "/nodes/" + resizeState.nodeId, {
              method: "PUT",
              body: { metadata: nextMeta }
            });
          },
          null
        );
        if (!result) {
          await refreshProjectData(projectId, true);
          return;
        }
        if (resizeState.isGroup) {
          addActivity(
            "info",
            "group resized: " + resizeState.nodeId + " => (" + nextMeta.group_width + ", " + nextMeta.group_height + ")"
          );
          await arrangeGroupChildren(resizeState.nodeId);
        } else {
          addActivity(
            "info",
            "node resized: " + resizeState.nodeId + " => (" + nextMeta.node_width + ", " + nextMeta.node_height + ")"
          );
          const resizedBinding = readGroupBinding(nextMeta);
          if (resizedBinding.binding === "bound" && resizedBinding.parentId) {
            await arrangeGroupChildren(resizedBinding.parentId);
          }
        }
      }

      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    }

    function beginViewportPan(event) {
      if (event.button !== 2) {
        return;
      }
      const viewport = viewportRef.current;
      if (!viewport) {
        return;
      }
      const panState = {
        startClientX: event.clientX,
        startClientY: event.clientY,
        startLeft: viewport.scrollLeft,
        startTop: viewport.scrollTop,
        dragging: false
      };
      function onMove(moveEvent) {
        const dx = moveEvent.clientX - panState.startClientX;
        const dy = moveEvent.clientY - panState.startClientY;
        if (!panState.dragging) {
          if (Math.hypot(dx, dy) < 4) {
            return;
          }
          panState.dragging = true;
        }
        moveEvent.preventDefault();
        viewport.scrollLeft = panState.startLeft - dx;
        viewport.scrollTop = panState.startTop - dy;
      }
      function onContextMenu(contextEvent) {
        if (!panState.dragging) {
          return;
        }
        contextEvent.preventDefault();
      }
      function onUp(upEvent) {
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
        window.removeEventListener("contextmenu", onContextMenu, true);
        if (panState.dragging) {
          contextMenuSuppressUntilRef.current = Date.now() + 220;
          upEvent.preventDefault();
        }
      }
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
      window.addEventListener("contextmenu", onContextMenu, true);
    }

    const storylineOptions = useMemo(
      function () {
        const values = new Set();
        nodes.forEach(function (node) {
          const value = String(node.storyline_id || "").trim();
          if (value) {
            values.add(value);
          }
        });
        return Array.from(values).sort(function (left, right) {
          return left.localeCompare(right);
        });
      },
      [nodes]
    );

    const visibleGraph = useMemo(
      function () {
        const allSelected = storylineFilter === STORYLINE_ALL;
        const includedNodeIds = new Set();
        nodes.forEach(function (node) {
          const storylineId = String(node.storyline_id || "").trim();
          if (allSelected || storylineId === storylineFilter) {
            includedNodeIds.add(node.id);
          }
        });
        nodes.forEach(function (node) {
          if (node.type === "group") {
            return;
          }
          if (!includedNodeIds.has(node.id)) {
            return;
          }
          const binding = readGroupBinding(nodeMetadataObject(node));
          if (binding.binding === "bound" && binding.parentId) {
            includedNodeIds.add(binding.parentId);
          }
        });

        const hiddenByCollapse = new Set();
        nodes.forEach(function (node) {
          if (node.type === "group") {
            return;
          }
          const binding = readGroupBinding(nodeMetadataObject(node));
          if (binding.binding === "bound" && binding.parentId && isGroupCollapsed(binding.parentId)) {
            hiddenByCollapse.add(node.id);
          }
        });

        const visibleNodes = nodes.filter(function (node) {
          return includedNodeIds.has(node.id) && !hiddenByCollapse.has(node.id);
        });
        const visibleNodeIds = new Set(
          visibleNodes.map(function (node) {
            return node.id;
          })
        );
        const visibleEdges = edges.filter(function (edge) {
          return visibleNodeIds.has(edge.source_id) && visibleNodeIds.has(edge.target_id);
        });
        return {
          nodes: visibleNodes,
          edges: visibleEdges,
          nodeIds: visibleNodeIds
        };
      },
      [nodes, edges, storylineFilter, collapsedGroupIds]
    );

    const visibleNodes = visibleGraph.nodes;
    const visibleEdges = visibleGraph.edges;
    const visibleNodeIds = visibleGraph.nodeIds;
    const visibleGhostPlans = useMemo(
      function () {
        const allSelected = storylineFilter === STORYLINE_ALL;
        return ghostPlans.filter(function (plan) {
          if (!plan || !plan.id || !plan.source_id) {
            return false;
          }
          if (!visibleNodeIds.has(plan.source_id)) {
            return false;
          }
          const storylineId = String(plan.storyline_id || "").trim();
          return allSelected || storylineId === storylineFilter;
        });
      },
      [ghostPlans, visibleNodeIds, storylineFilter]
    );
    const visibleGhostArchive = useMemo(
      function () {
        const activeProjectId = String(projectId || "");
        return ghostArchive.filter(function (item) {
          return String(item.project_id || "") === activeProjectId;
        });
      },
      [ghostArchive, projectId]
    );
    const selectedGhostCount = useMemo(
      function () {
        let count = 0;
        Object.keys(selectedGhostIds).forEach(function (ghostId) {
          if (selectedGhostIds[ghostId]) {
            count += 1;
          }
        });
        return count;
      },
      [selectedGhostIds]
    );
    const visibleGhostById = useMemo(
      function () {
        const map = {};
        visibleGhostPlans.forEach(function (plan) {
          map[plan.id] = plan;
        });
        return map;
      },
      [visibleGhostPlans]
    );
    const insightHighlightSet = useMemo(
      function () {
        return new Set(
          insightHighlightNodeIds.map(function (item) {
            return String(item || "");
          })
        );
      },
      [insightHighlightNodeIds]
    );

    const nodeById = useMemo(
      function () {
        const map = {};
        nodes.forEach(function (node) {
          map[node.id] = node;
        });
        return map;
      },
      [nodes]
    );

    function nodeRenderSize(node) {
      const isGroup = node && node.type === "group";
      const metadata = node && node.metadata && typeof node.metadata === "object" ? node.metadata : {};
      if (!isGroup) {
        return sceneRenderSizeByMetadata(metadata);
      }
      const width = Math.max(GROUP_MIN_WIDTH, asNumber(metadata.group_width, 820));
      const height = Math.max(GROUP_MIN_HEIGHT, asNumber(metadata.group_height, 460));
      if (isGroupCollapsed(node.id)) {
        return {
          width: Math.max(260, Math.min(560, Math.round(width * 0.62))),
          height: 88
        };
      }
      return { width: width, height: height };
    }

    const boardSize = useMemo(
      function () {
        let width = 1280;
        let height = 960;
        visibleNodes.forEach(function (node) {
          const size = nodeRenderSize(node);
          width = Math.max(width, asNumber(node.pos_x, 0) + size.width + 240);
          height = Math.max(height, asNumber(node.pos_y, 0) + size.height + 220);
        });
        visibleGhostPlans.forEach(function (plan) {
          width = Math.max(width, asNumber(plan.pos_x, 0) + NODE_WIDTH + 220);
          height = Math.max(height, asNumber(plan.pos_y, 0) + NODE_HEIGHT + 200);
        });
        return { width: width, height: height };
      },
      [visibleNodes, visibleGhostPlans, collapsedGroupIds]
    );

    const edgeShapes = useMemo(
      function () {
        const outgoingSlotByEdgeId = {};
        const outgoingBySourceId = {};
        visibleEdges.forEach(function (edge) {
          if (!outgoingBySourceId[edge.source_id]) {
            outgoingBySourceId[edge.source_id] = [];
          }
          outgoingBySourceId[edge.source_id].push(edge);
        });
        Object.keys(outgoingBySourceId).forEach(function (sourceId) {
          outgoingBySourceId[sourceId]
            .slice()
            .sort(compareEdgesByNarrativeOrder)
            .forEach(function (edge, index) {
              outgoingSlotByEdgeId[edge.id] = index;
            });
        });

        return visibleEdges
          .map(function (edge) {
            const source = nodeById[edge.source_id];
            const target = nodeById[edge.target_id];
            if (!source || !target) {
              return null;
            }
            const sourceSize = nodeRenderSize(source);
            const targetSize = nodeRenderSize(target);
            const sourcePosX = asNumber(source.pos_x, 0);
            const sourcePosY = asNumber(source.pos_y, 0);
            const targetPosX = asNumber(target.pos_x, 0);
            const targetPosY = asNumber(target.pos_y, 0);
            const sourceCenterX = sourcePosX + sourceSize.width / 2;
            const sourceCenterY = sourcePosY + sourceSize.height / 2;
            const targetCenterX = targetPosX + targetSize.width / 2;
            const targetCenterY = targetPosY + targetSize.height / 2;
            const sourceAnchor = rectAnchor(
              sourceCenterX,
              sourceCenterY,
              targetCenterX,
              targetCenterY,
              sourceSize.width / 2,
              sourceSize.height / 2
            );
            const targetAnchor = rectAnchor(
              targetCenterX,
              targetCenterY,
              sourceCenterX,
              sourceCenterY,
              targetSize.width / 2,
              targetSize.height / 2
            );
            const siblingSlot = outgoingSlotByEdgeId[edge.id] || 0;
            const isSelfLoop = edge.source_id === edge.target_id;
            const isSuggestedEdge = nodeIsSuggested(source) || nodeIsSuggested(target);
            const sourceStoryline = String(source.storyline_id || "").trim();
            const edgeTone = storylineColor(sourceStoryline);
            let sx = sourceAnchor.x;
            let sy = sourceAnchor.y;
            let tx = targetAnchor.x;
            let ty = targetAnchor.y;
            let control1;
            let control2;
            let labelYOffset = -9;
            let renderRank = 1;

            const isBackwardByX = tx < sx - 8;
            const isBackwardByY = Math.abs(tx - sx) <= 8 && ty < sy - 8;
            const isLoopLike = isSelfLoop || isBackwardByX || isBackwardByY;
            const isHighlightEdge = insightHighlightSet.has(edge.source_id) || insightHighlightSet.has(edge.target_id);

            if (isSelfLoop) {
              const centerX = sourcePosX + sourceSize.width / 2;
              const bottomY = sourcePosY + sourceSize.height + 2;
              const loopWidth = Math.max(24, Math.min(64, sourceSize.width * 0.22));
              sx = centerX - loopWidth;
              tx = centerX + loopWidth;
              sy = bottomY;
              ty = bottomY;
              const depth = Math.max(96, Math.min(248, sourceSize.height * 1.16 + siblingSlot * 24));
              control1 = { x: sx - 52, y: sy + depth };
              control2 = { x: tx + 52, y: ty + depth };
              labelYOffset = 18;
              renderRank = 0;
            } else if (isLoopLike) {
              const sourceBottomX = sourcePosX + sourceSize.width / 2;
              const sourceBottomY = sourcePosY + sourceSize.height + 2;
              const targetBottomX = targetPosX + targetSize.width / 2;
              const targetBottomY = targetPosY + targetSize.height + 2;
              sx = sourceBottomX;
              sy = sourceBottomY;
              tx = targetBottomX;
              ty = targetBottomY;
              const depthBase = Math.max(84, Math.min(248, Math.abs(tx - sx) * 0.24 + Math.abs(ty - sy) * 0.32));
              const depth = depthBase + siblingSlot * 20;
              const spread = Math.max(42, Math.min(176, Math.abs(tx - sx) * 0.24 + 46));
              const direction = tx >= sx ? 1 : -1;
              control1 = { x: sx + direction * spread, y: sy + depth };
              control2 = { x: tx - direction * spread, y: ty + depth };
              labelYOffset = 14;
              renderRank = 0;
            } else {
              const edgeLength = Math.hypot(tx - sx, ty - sy);
              const bend = Math.max(40, Math.min(140, edgeLength * 0.28));
              const horizontalDir = tx >= sx ? 1 : -1;
              const verticalSpread = Math.min(34, siblingSlot * 7);
              control1 = { x: sx + horizontalDir * bend, y: sy + verticalSpread };
              control2 = { x: tx - horizontalDir * bend, y: ty + verticalSpread };
            }

            const path =
              "M " +
              sx +
              " " +
              sy +
              " C " +
              control1.x +
              " " +
              control1.y +
              ", " +
              control2.x +
              " " +
              control2.y +
              ", " +
              tx +
              " " +
              ty;
            const midpoint = cubicMidpoint(
              { x: sx, y: sy },
              control1,
              control2,
              { x: tx, y: ty }
            );
            const labelX = midpoint.x;
            const labelY = midpoint.y + labelYOffset;
            return {
              edge: edge,
              path: path,
              labelX: labelX,
              labelY: labelY,
              sourceTitle: source.title,
              targetTitle: target.title,
              suggested: isSuggestedEdge,
              highlight: isHighlightEdge,
              tone: edgeTone,
              renderRank: renderRank
            };
          })
          .filter(Boolean);
      },
      [visibleEdges, nodeById, collapsedGroupIds, insightHighlightSet]
    );

    const edgeRenderShapes = useMemo(
      function () {
        return edgeShapes
          .slice()
          .sort(function (left, right) {
            if (left.renderRank !== right.renderRank) {
              return left.renderRank - right.renderRank;
            }
            return compareEdgesByNarrativeOrder(left.edge, right.edge);
          });
      },
      [edgeShapes]
    );

    const ghostEdgeShapes = useMemo(
      function () {
        return visibleGhostPlans
          .map(function (plan) {
            const sourceGhostId = String(plan.source_ghost_id || "").trim();
            const sourceGhost = sourceGhostId ? visibleGhostById[sourceGhostId] : null;
            const sourceNode = sourceGhost ? null : nodeById[plan.source_id];
            if (!sourceGhost && !sourceNode) {
              return null;
            }
            const sourceSize = sourceGhost ? { width: NODE_WIDTH, height: NODE_HEIGHT } : nodeRenderSize(sourceNode);
            const sourcePosX = asNumber(sourceGhost ? sourceGhost.pos_x : sourceNode.pos_x, 0);
            const sourcePosY = asNumber(sourceGhost ? sourceGhost.pos_y : sourceNode.pos_y, 0);
            const targetPosX = asNumber(plan.pos_x, 0);
            const targetPosY = asNumber(plan.pos_y, 0);
            const targetWidth = NODE_WIDTH;
            const targetHeight = NODE_HEIGHT;
            const sourceCenterX = sourcePosX + sourceSize.width / 2;
            const sourceCenterY = sourcePosY + sourceSize.height / 2;
            const targetCenterX = targetPosX + targetWidth / 2;
            const targetCenterY = targetPosY + targetHeight / 2;
            const sourceAnchor = rectAnchor(
              sourceCenterX,
              sourceCenterY,
              targetCenterX,
              targetCenterY,
              sourceSize.width / 2,
              sourceSize.height / 2
            );
            const targetAnchor = rectAnchor(
              targetCenterX,
              targetCenterY,
              sourceCenterX,
              sourceCenterY,
              targetWidth / 2,
              targetHeight / 2
            );
            const dx = Math.abs(targetAnchor.x - sourceAnchor.x);
            const bend = Math.max(52, Math.min(150, dx * 0.26));
            const dir = targetAnchor.x >= sourceAnchor.x ? 1 : -1;
            const control1 = { x: sourceAnchor.x + dir * bend, y: sourceAnchor.y };
            const control2 = { x: targetAnchor.x - dir * bend, y: targetAnchor.y };
            const path =
              "M " +
              sourceAnchor.x +
              " " +
              sourceAnchor.y +
              " C " +
              control1.x +
              " " +
              control1.y +
              ", " +
              control2.x +
              " " +
              control2.y +
              ", " +
              targetAnchor.x +
              " " +
              targetAnchor.y;
            const midpoint = cubicMidpoint(sourceAnchor, control1, control2, targetAnchor);
            return {
              id: "ghost_edge_" + plan.id,
              path: path,
              labelX: midpoint.x,
              labelY: midpoint.y - 8,
              tone:
                storylineColor(plan.storyline_id || (sourceNode ? sourceNode.storyline_id : "")) ||
                sentimentToneColor(plan.sentiment)
            };
          })
          .filter(Boolean);
      },
      [visibleGhostPlans, visibleGhostById, nodeById]
    );

    useEffect(
      function () {
        void loadLocaleCatalog(locale);
      },
      [locale]
    );

    useEffect(
      function () {
        const validGhostIds = new Set(
          ghostPlans.map(function (item) {
            return item.id;
          })
        );
        setExpandedGhostIds(function (prev) {
          return pruneGhostStateMap(prev, validGhostIds);
        });
        setSelectedGhostIds(function (prev) {
          return pruneGhostStateMap(prev, validGhostIds);
        });
        setRetiringGhostIds(function (prev) {
          return pruneGhostStateMap(prev, validGhostIds);
        });
      },
      [ghostPlans]
    );

    useEffect(
      function () {
        const outlineDraft = {
          goal: String(outlineGuideForm.goal || ""),
          sync_context: String(outlineGuideForm.sync_context || ""),
          specify: String(outlineGuideForm.specify || ""),
          clarify_answers: String(outlineGuideForm.clarify_answers || ""),
          plan_notes: String(outlineGuideForm.plan_notes || ""),
          constraints: String(outlineGuideForm.constraints || ""),
          tone: String(outlineGuideForm.tone || ""),
          outline_markdown: String(outlineGuideForm.outline_markdown || ""),
          questions: safeArray(outlineGuideForm.questions).map(String).slice(0, 16),
          chapter_beats: safeArray(outlineGuideForm.chapter_beats).map(String).slice(0, 32),
          next_steps: safeArray(outlineGuideForm.next_steps).map(String).slice(0, 16)
        };
        const sessionPayload = {
          project_id: String(projectId || ""),
          selected_node_id: String(selectedNodeId || ""),
          sidebar_tab: normalizePersistedSidebarTab(sidebarTab),
          main_view: normalizePersistedMainView(mainView),
          storyline_filter: String(storylineFilter || STORYLINE_ALL),
          zoom: Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, asNumber(zoom, 1))),
          edge_mode: Boolean(edgeMode),
          auto_bind_on_drop: Boolean(autoBindOnDrop),
          chat_open: Boolean(chatOpen),
          chat_view_scale: Math.max(0.8, Math.min(2.2, asNumber(chatViewScale, 1))),
          artifact_open: Boolean(artifactOpen),
          chat_context_node_id: String(chatContextNodeId || ""),
          artifact_context_node_id: String(artifactContextNodeId || ""),
          chat_input: String(chatInput || ""),
          chat_messages: normalizePersistedChatMessages(chatMessages),
          ai_config: {
            token_budget: String(aiConfig.token_budget || "2200"),
            workflow_mode: aiConfig.workflow_mode === "single" ? "single" : "multi_agent"
          },
          new_project_title: String(newProjectTitle || ""),
          new_node_form: Object.assign({}, newNodeForm || {}),
          outline_guide_form: outlineDraft,
          collapsed_group_ids: Object.assign({}, collapsedGroupIds || {}),
          ghost_archive: normalizePersistedGhostArchive(ghostArchive)
        };
        saveWebState(sessionPayload);
      },
      [
        projectId,
        selectedNodeId,
        sidebarTab,
        mainView,
        storylineFilter,
        zoom,
        edgeMode,
        autoBindOnDrop,
        chatOpen,
        chatViewScale,
        artifactOpen,
        chatContextNodeId,
        artifactContextNodeId,
        chatInput,
        chatMessages,
        aiConfig,
        newProjectTitle,
        newNodeForm,
        outlineGuideForm,
        collapsedGroupIds,
        ghostArchive
      ]
    );

    useEffect(function () {
      void refreshProjects("");
      void loadRuntimeSettings();
      void loadLlmPresets();
    }, []);

    useEffect(
      function () {
        if (!projectId) {
          return;
        }
        void refreshProjectData(projectId, true);
      },
      [projectId]
    );

    useEffect(
      function () {
        if (!projectId) {
          setInsightData(null);
          setInsightError("");
          setInsightHighlightNodeIds([]);
          setStorylineFilter(STORYLINE_ALL);
          return;
        }
        setStorylineFilter(STORYLINE_ALL);
        void loadInsights(false);
      },
      [projectId]
    );

    useEffect(
      function () {
        if (mainView !== "insight" || !projectId) {
          return;
        }
        const insightRevision =
          insightData && Number.isFinite(Number(insightData.revision))
            ? Number(insightData.revision)
            : -1;
        const projectRevision =
          project && Number.isFinite(Number(project.active_revision))
            ? Number(project.active_revision)
            : -1;
        if (!insightData || (projectRevision >= 0 && insightRevision !== projectRevision)) {
          void loadInsights(false);
        }
      },
      [
        mainView,
        projectId,
        project ? project.active_revision : "",
        insightData ? insightData.revision : ""
      ]
    );

    useEffect(
      function () {
        const selected = nodes.find(function (item) {
          return item.id === selectedNodeId;
        });
        if (!selected) {
          setInspector(null);
          return;
        }
        const extracted = splitNodeMetadata(selected.metadata || {});
        setInspector({
          title: selected.title,
          type: selected.type,
          status: selected.status,
          storyline_id: selected.storyline_id || "",
          agent_preset: extracted.agentPreset,
          group_parent_id: extracted.groupParentId,
          group_binding: extracted.groupBinding,
          group_kind: extracted.groupKind,
          group_width: String(asNumber(extracted.plainMetadata.group_width, 820)),
          group_height: String(asNumber(extracted.plainMetadata.group_height, 460)),
          metadata_json: JSON.stringify(extracted.plainMetadata, null, 2)
        });
      },
      [selectedNodeId, nodes]
    );

    useEffect(
      function () {
        setRuntimePresetTag(inferRuntimePreset(runtimeSettings, llmPresets));
      },
      [runtimeSettings, llmPresets]
    );

    useEffect(
      function () {
        if (!projectId) {
          setOutlineGuideForm({
            goal: "",
            sync_context: "",
            specify: "",
            clarify_answers: "",
            plan_notes: "",
            constraints: "",
            tone: "",
            outline_markdown: "",
            questions: [],
            chapter_beats: [],
            next_steps: []
          });
          return;
        }
        if (!outlineRequired) {
          return;
        }
        setOutlineGuideForm(function (prev) {
          if (String(prev.goal || "").trim()) {
            return prev;
          }
          return Object.assign({}, prev, {
            goal: project ? String(project.title || "").trim() : ""
          });
        });
      },
      [projectId, outlineRequired, project ? project.title : ""]
    );

    useEffect(
      function () {
        if (!projectId) {
          setChatWorkflow(buildDefaultWorkflowState());
          return;
        }
        if (!outlineRequired) {
          setChatWorkflow(function (prev) {
            if (!prev.enabled) {
              return prev;
            }
            return buildDefaultWorkflowState();
          });
          return;
        }
        setChatWorkflow(function (prev) {
          if (prev.enabled) {
            return prev;
          }
          return Object.assign(buildDefaultWorkflowState(), {
            enabled: true,
            step: "start"
          });
        });
        if (!chatOpen) {
          setChatOpen(true);
          setArtifactOpen(false);
        }
        if (chatContextNodeId) {
          setChatContextNodeId("");
        }
        setChatMessages(function (prev) {
          if (
            prev.some(function (item) {
              return String(item.meta || "").includes("workflow_init");
            })
          ) {
            return prev;
          }
          const hello = {
            id: "chat_" + Date.now().toString(36) + "_workflow_init",
            role: "assistant",
            text: workflowWelcomeText,
            meta: "workflow_init",
            at: new Date().toISOString(),
            diffSegments: []
          };
          return prev.concat(hello).slice(-120);
        });
      },
      [projectId, outlineRequired, chatOpen, chatContextNodeId]
    );

    useEffect(
      function () {
        setChatMessages(function (prev) {
          let changed = false;
          const next = prev.map(function (item) {
            if (!String(item && item.meta ? item.meta : "").includes("workflow_init")) {
              return item;
            }
            if (String(item && item.text ? item.text : "") === workflowWelcomeText) {
              return item;
            }
            changed = true;
            return Object.assign({}, item, {
              text: workflowWelcomeText
            });
          });
          return changed ? next : prev;
        });
      },
      [workflowWelcomeText, locale]
    );

    useEffect(function () {
      function onKeyDown(event) {
        if (!event.altKey) {
          return;
        }
        const key = String(event.key || "");
        if (key === "+" || key === "=" || event.code === "NumpadAdd") {
          event.preventDefault();
          applyZoomDelta(ZOOM_STEP);
          return;
        }
        if (key === "-" || key === "_" || event.code === "NumpadSubtract") {
          event.preventDefault();
          applyZoomDelta(-ZOOM_STEP);
        }
      }
      window.addEventListener("keydown", onKeyDown);
      return function () {
        window.removeEventListener("keydown", onKeyDown);
      };
    }, []);

    useEffect(
      function () {
        if (!project) {
          return;
        }
        setProjectSettingsForm({
          auto_snapshot_minutes: String(project.settings.auto_snapshot_minutes),
          auto_snapshot_operations: String(project.settings.auto_snapshot_operations)
        });
      },
      [project ? project.id : "", project ? project.updated_at : ""]
    );

    useEffect(
      function () {
        if (!projectId) {
          setChatContextNodeId("");
          setArtifactContextNodeId("");
          setChatOpen(false);
          setArtifactOpen(false);
          setArtifactDiffSegments([]);
          setArtifactDiffNodeId("");
          setChatMessages([]);
          setGhostPlans([]);
          setExpandedGhostIds({});
          setSelectedGhostIds({});
          setRetiringGhostIds({});
          setNodeFlowStates({});
          setInsightData(null);
          setInsightError("");
          setInsightHighlightNodeIds([]);
        }
      },
      [projectId]
    );

    useEffect(
      function () {
        if (!artifactOpen) {
          return;
        }
        const contextId = String(artifactContextNodeId || "").trim();
        if (!contextId) {
          return;
        }
        const exists = nodes.some(function (item) {
          return item.id === contextId;
        });
        if (!exists) {
          setArtifactContextNodeId("");
        }
      },
      [artifactOpen, artifactContextNodeId, nodes]
    );

    useEffect(
      function () {
        if (!chatOpen) {
          return;
        }
        const contextId = String(chatContextNodeId || "").trim();
        if (!contextId) {
          return;
        }
        const exists = nodes.some(function (item) {
          return item.id === contextId;
        });
        if (!exists) {
          setChatContextNodeId("");
        }
      },
      [chatOpen, chatContextNodeId, nodes]
    );

    useEffect(
      function () {
        const log = chatLogRef.current;
        if (!log) {
          return;
        }
        log.scrollTop = log.scrollHeight;
      },
      [chatMessages, chatOpen, chatContextNodeId, artifactContextNodeId]
    );

    useEffect(function () {
      const timer = window.setInterval(function () {
        setNodeFlowStates(function (prev) {
          const keys = Object.keys(prev);
          if (keys.length === 0) {
            return prev;
          }
          const next = Object.assign({}, prev);
          keys.forEach(function (nodeId) {
            const item = next[nodeId];
            if (!item || !Array.isArray(item.phases) || item.phases.length <= 1) {
              return;
            }
            next[nodeId] = Object.assign({}, item, {
              index: (item.index + 1) % item.phases.length
            });
          });
          return next;
        });
      }, 900);
      return function () {
        window.clearInterval(timer);
      };
    }, []);

    function onLocaleChange(event) {
      const next = event.target.value;
      setLocale(next);
      setRuntimeField("locale", next);
      pushToast("ok", t("web.toast.language_switched", { locale: next }));
    }

    function setFormField(key, value) {
      setNewNodeForm(function (prev) {
        return Object.assign({}, prev, { [key]: value });
      });
    }

    function setProjectSettingsField(key, value) {
      setProjectSettingsForm(function (prev) {
        return Object.assign({}, prev, { [key]: value });
      });
    }

    function setOutlineGuideField(key, value) {
      setOutlineGuideForm(function (prev) {
        return Object.assign({}, prev, { [key]: value });
      });
    }

    function setRuntimeField(key, value) {
      setRuntimeSettings(function (prev) {
        return Object.assign({}, prev, { [key]: value });
      });
    }

    async function saveRuntimeSettings() {
      const normalized = Object.assign({}, runtimeSettings, {
        auto_complete: Boolean(runtimeSettings.auto_complete),
        think_switch: Boolean(runtimeSettings.think_switch),
        think_depth: String(runtimeSettings.think_depth || "medium"),
        thinking_budget: Math.max(1, Math.floor(asNumber(runtimeSettings.thinking_budget, 2048))),
        web_search_enabled: Boolean(runtimeSettings.web_search_enabled),
        web_search_context_size: String(runtimeSettings.web_search_context_size || "medium"),
        web_search_max_results: Math.max(1, Math.floor(asNumber(runtimeSettings.web_search_max_results, 5))),
        llm_request_timeout: Math.max(5, Math.floor(asNumber(runtimeSettings.llm_request_timeout, 90))),
        web_request_timeout_ms: Math.max(30000, Math.floor(asNumber(runtimeSettings.web_request_timeout_ms, 240000))),
        default_token_budget: Math.max(1, Math.floor(asNumber(runtimeSettings.default_token_budget, 2200))),
        default_workflow_mode: runtimeSettings.default_workflow_mode === "single" ? "single" : "multi_agent",
        web_port: Math.max(1, Math.floor(asNumber(runtimeSettings.web_port, 8765)))
      });
      const payload = await runApi(
        function () {
          return apiRequest("/api/settings/runtime", {
            method: "PUT",
            body: normalized
          });
        },
        t("web.toast.saved")
      );
      if (!payload) {
        return;
      }
      applyRuntimePayload(payload, { syncLocale: true, syncAiDefaults: false });
      addActivity("success", "runtime settings saved");
    }

    async function switchRuntimeProfile(profile, createIfMissing) {
      const payload = await runApi(
        function () {
          return apiRequest("/api/settings/runtime/switch", {
            method: "POST",
            body: {
              profile: profile,
              create_if_missing: Boolean(createIfMissing)
            }
          });
        },
        t("web.toast.loaded")
      );
      if (!payload) {
        return;
      }
      applyRuntimePayload(payload, { syncLocale: true, syncAiDefaults: true });
      setRenameRuntimeProfile("");
      addActivity("info", "runtime profile switched: " + profile);
    }

    async function createRuntimeProfile() {
      const profile = newRuntimeProfile.trim();
      if (!profile) {
        return;
      }
      const created = await runApi(
        function () {
          return apiRequest("/api/settings/runtime/profiles", {
            method: "POST",
            body: {
              profile: profile,
              from_profile: activeRuntimeProfile
            }
          });
        },
        t("web.toast.created")
      );
      if (!created) {
        return;
      }
      setNewRuntimeProfile("");
      await switchRuntimeProfile(profile, false);
    }

    async function renameActiveRuntimeProfile() {
      if (activeRuntimeProfile === "core") {
        pushToast("warn", t("web.runtime.core_readonly"));
        return;
      }
      const newProfile = renameRuntimeProfile.trim();
      if (!newProfile) {
        return;
      }
      const payload = await runApi(
        function () {
          return apiRequest("/api/settings/runtime/profiles/rename", {
            method: "POST",
            body: {
              profile: activeRuntimeProfile,
              new_profile: newProfile
            }
          });
        },
        t("web.toast.saved")
      );
      if (!payload) {
        return;
      }
      applyRuntimePayload(payload, { syncLocale: true, syncAiDefaults: false });
      setRenameRuntimeProfile("");
      addActivity("success", "runtime profile renamed");
    }

    async function deleteActiveRuntimeProfile() {
      if (activeRuntimeProfile === "core") {
        pushToast("warn", t("web.runtime.core_readonly"));
        return;
      }
      const confirmed = await showConfirm(
        t("web.runtime.delete_profile_title"),
        t("web.runtime.delete_profile_body", { profile: activeRuntimeProfile })
      );
      if (!confirmed) {
        return;
      }
      const payload = await runApi(
        function () {
          return apiRequest("/api/settings/runtime/profiles/" + encodeURIComponent(activeRuntimeProfile), {
            method: "DELETE"
          });
        },
        t("web.toast.deleted")
      );
      if (!payload) {
        return;
      }
      applyRuntimePayload(payload, { syncLocale: true, syncAiDefaults: true });
      addActivity("success", "runtime profile deleted");
    }

    function applyRuntimeDefaults() {
      setAiConfig(function () {
        return {
          token_budget: String(Math.max(1, Math.floor(asNumber(runtimeSettings.default_token_budget, 2200)))),
          workflow_mode: runtimeSettings.default_workflow_mode === "single" ? "single" : "multi_agent"
        };
      });
      pushToast("ok", t("web.toast.runtime_applied"));
    }

    function clearCurrentChatHistory() {
      const activeContextId = resolveActiveChatContext(chatContextNodeId, artifactContextNodeId);
      const next = chatMessages.filter(function (item) {
        const itemContextId = String(item && item.context_node_id ? item.context_node_id : "").trim();
        return itemContextId !== activeContextId;
      });
      if (next.length === chatMessages.length) {
        pushToast("warn", t("web.chat.history_empty"));
        return;
      }
      setChatMessages(next);
      pushToast("ok", t("web.chat.history_cleared"));
    }

    function setInspectorField(key, value) {
      setInspector(function (prev) {
        if (!prev) {
          return prev;
        }
        return Object.assign({}, prev, { [key]: value });
      });
    }


    return {
      t,
      enumLabel,
      nodeTypeLabel,
      groupKindLabel,
      groupBindingLabel,
      nodeStatusLabel,
      nodeIsSuggested,
      isGroupCollapsed,
      toggleGroupCollapsed,
      hashString,
      storylineColor,
      nodeContentOf,
      hasProjectOutline,
      isMockProvider,
      formatAgentTrace,
      buildDiffSegments,
      renderMarkdownPreview,
      startNodeFlow,
      stopNodeFlow,
      edgeDisplayLabel,
      compareEdgesByNarrativeOrder,
      clampZoom,
      applyZoomDelta,
      applyRuntimePayload,
      pushToast,
      addActivity,
      aiRequestTimeoutMs,
      showModal,
      resolveModal,
      showConfirm,
      showInput,
      openTutorialModal,
      resolveErrorMessage,
      runApiDetailed,
      runApi,
      appendChatMessage,
      openChatForNode,
      applyNodeContentPatchLocal,
      sendChatMessage,
      clearCurrentChatHistory,
      projectActionHandlers,
      loadLocaleCatalog,
      loadRuntimeSettings,
      loadLlmPresets,
      applyRuntimePreset,
      refreshProjects,
      refreshProjectData,
      loadInsights,
      focusNodeOnViewport,
      openNodeFromInsight,
      validateGraph,
      exportGraph,
      createSnapshot,
      rollbackProject,
      createProject,
      runOutlineGuide,
      saveOutlineNodeFromGuide,
      deleteProject,
      toggleAllowCycles,
      saveProjectSettings,
      workflowActionHandlers,
      materializeWorkflowGraphPlan,
      saveWorkflowOutlineNode,
      handleWorkflowChat,
      ghostActionHandlers,
      createGhostPlansFromOptions,
      ghostOutlineText,
      sentimentToneColor,
      pruneGhostStateMap,
      restoreGhostFromArchive,
      removeGhostArchiveItem,
      clearGhostArchiveForProject,
      toggleGhostPreview,
      toggleGhostSelection,
      toggleGhostLock,
      fuseSelectedGhostPlans,
      adoptGhostPlan,
      previewGhostPlan,
      deleteGhostRoute,
      acceptSuggestedNode,
      clearSuggestedNodes,
      nodeActionHandlers,
      createNode,
      saveInspector,
      deleteNode,
      deleteEdge,
      createEdge,
      reorderEdge,
      runAi,
      onNodeClick,
      nodeMetadataObject,
      readGroupBinding,
      applyGroupBinding,
      sceneRenderSizeByMetadata,
      groupRenderSizeByMetadata,
      findContainingGroupId,
      arrangeGroupChildren,
      beginDrag,
      beginGhostDrag,
      beginNodeResize,
      beginViewportPan,
      storylineOptions,
      visibleGraph,
      visibleNodes,
      visibleEdges,
      visibleNodeIds,
      visibleGhostPlans,
      visibleGhostArchive,
      selectedGhostCount,
      visibleGhostById,
      insightHighlightSet,
      nodeById,
      nodeRenderSize,
      boardSize,
      edgeShapes,
      edgeRenderShapes,
      ghostEdgeShapes,
      onLocaleChange,
      setFormField,
      setProjectSettingsField,
      setOutlineGuideField,
      setRuntimeField,
      saveRuntimeSettings,
      switchRuntimeProfile,
      createRuntimeProfile,
      renameActiveRuntimeProfile,
      deleteActiveRuntimeProfile,
      applyRuntimeDefaults,
      setInspectorField
    };
  };
})();
