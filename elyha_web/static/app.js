(function () {
  "use strict";

  const { useEffect, useMemo, useRef, useState } = React;
  const h = React.createElement;

  const constants = window.ElyhaWebConstants || {};
  const helpers = window.ElyhaWebHelpers || {};
  const components = window.ElyhaWebComponents || {};
  const stateUtils = window.ElyhaWebStateUtils || {};
  const ghostUtils = window.ElyhaWebGhostUtils || {};
  const graphUtils = window.ElyhaWebGraphUtils || {};
  const textUtils = window.ElyhaWebTextUtils || {};
  const diffUtils = window.ElyhaWebDiffUtils || {};
  const artifactUtils = window.ElyhaWebArtifactUtils || {};
  const apiActions = window.ElyhaWebApiActions || {};
  const aiActions = window.ElyhaWebAiActions || {};
  const configActions = window.ElyhaWebConfigActions || {};
  const workflowActions = window.ElyhaWebAppWorkflowActions || {};
  const appGhostActions = window.ElyhaWebAppGhostActions || {};
  const projectActions = window.ElyhaWebAppProjectActions || {};
  const nodeActions = window.ElyhaWebAppNodeActions || {};

  const NODE_WIDTH = constants.NODE_WIDTH || 224;
  const NODE_HEIGHT = constants.NODE_HEIGHT || 120;
  const SUPPORTED_LOCALES = constants.SUPPORTED_LOCALES || ["zh", "en", "ja"];
  const DEFAULT_LOCALE = constants.DEFAULT_LOCALE || "zh";
  const NODE_TYPES = constants.NODE_TYPES || ["chapter", "group", "branch", "merge", "parallel", "checkpoint"];
  const GROUP_KINDS = ["phase", "chapter"];
  const GROUP_BINDINGS = ["independent", "bound"];
  const NODE_STATUSES = constants.NODE_STATUSES || ["draft", "generated", "reviewed", "approved"];
  const FALLBACK_TEXT = constants.FALLBACK_TEXT || {};
  const MIN_ZOOM = 0.4;
  const MAX_ZOOM = 2.4;
  const ZOOM_STEP = 0.1;
  const STORYLINE_ALL = "__all__";
  const WEB_STATE_KEY = "elyha_web_state_v1";
  const NODE_MIN_WIDTH = Math.round(NODE_WIDTH * 0.72);
  const NODE_MIN_HEIGHT = Math.round(NODE_HEIGHT * 0.72);
  const GROUP_MIN_WIDTH = Math.round(NODE_WIDTH * 1.8);
  const GROUP_MIN_HEIGHT = Math.round(NODE_HEIGHT * 1.6);
  const GROUP_LAYOUT_PADDING_X = 28;
  const GROUP_LAYOUT_PADDING_Y = 38;
  const GROUP_LAYOUT_GAP_X = 24;
  const GROUP_LAYOUT_GAP_Y = 20;

  const apiRequest = helpers.apiRequest;
  const formatValue = helpers.formatValue;
  const shortIso = helpers.shortIso;
  const asNumber = helpers.asNumber;
  const MetaItem = components.MetaItem;
  const Modal = components.Modal;
  const rectAnchor = graphUtils.rectAnchor;
  const cubicMidpoint = graphUtils.cubicMidpoint;
  const splitNodeMetadata = stateUtils.splitNodeMetadata;
  const asBoolean = stateUtils.asBoolean;
  const inferRuntimePreset = stateUtils.inferRuntimePreset;
  const loadWebStateValue = stateUtils.loadWebState;
  const saveWebStateValue = stateUtils.saveWebState;
  const loadWebState = function () {
    return loadWebStateValue(WEB_STATE_KEY);
  };
  const saveWebState = function (payload) {
    return saveWebStateValue(WEB_STATE_KEY, payload);
  };
  const safeArray = stateUtils.safeArray;
  const normalizeChatDiffSegments = stateUtils.normalizeChatDiffSegments;
  const normalizePersistedChatMessages = stateUtils.normalizePersistedChatMessages;
  const normalizePersistedMainView = stateUtils.normalizePersistedMainView;
  const normalizePersistedSidebarTab = stateUtils.normalizePersistedSidebarTab;
  const ghostIdWithSeed = ghostUtils.ghostIdWithSeed;
  const normalizeGhostSentiment = ghostUtils.normalizeGhostSentiment;
  const inferGhostSentimentFromText = ghostUtils.inferGhostSentimentFromText;
  const normalizeGhostOutlineSteps = ghostUtils.normalizeGhostOutlineSteps;
  const pickGhostOutlineSteps = ghostUtils.pickGhostOutlineSteps;
  const normalizePersistedGhostArchive = ghostUtils.normalizePersistedGhostArchive;
  const ghostOutlineTextValue = ghostUtils.ghostOutlineText;
  const sentimentToneColorValue = ghostUtils.sentimentToneColor;
  const pruneGhostStateMapValue = ghostUtils.pruneGhostStateMap;
  const edgeDisplayLabelValue = graphUtils.edgeDisplayLabel;
  const compareEdgesByNarrativeOrderValue = graphUtils.compareEdgesByNarrativeOrder;
  const clampZoomValue = graphUtils.clampZoom;
  const nodeMetadataObjectValue = graphUtils.nodeMetadataObject;
  const readGroupBindingValue = graphUtils.readGroupBinding;
  const applyGroupBindingValue = graphUtils.applyGroupBinding;
  const sceneRenderSizeByMetadataValue = graphUtils.sceneRenderSizeByMetadata;
  const groupRenderSizeByMetadataValue = graphUtils.groupRenderSizeByMetadata;
  const findContainingGroupIdValue = graphUtils.findContainingGroupId;
  const formatAgentTraceValue = textUtils.formatAgentTrace;
  const buildDiffSegmentsValue = textUtils.buildDiffSegments;
  const renderMarkdownPreviewValue = textUtils.renderMarkdownPreview;
  const parseWorkflowModeValue = textUtils.parseWorkflowMode;
  const isWorkflowBackgroundConfirmedValue = textUtils.isWorkflowBackgroundConfirmed;
  const isWorkflowOutlineConfirmedValue = textUtils.isWorkflowOutlineConfirmed;
  const parseBeatListValue = textUtils.parseBeatList;
  const beatTitleValue = textUtils.beatTitle;
  const normalizeDiffKindValue = diffUtils.normalizeDiffKind;
  const diffPrefixValue = diffUtils.diffPrefix;
  const resolveActiveChatContextValue = artifactUtils.resolveActiveChatContext;
  const nextArtifactDiffNodeIdValue = artifactUtils.nextArtifactDiffNodeId;
  const shouldShowArtifactDiffValue = artifactUtils.shouldShowArtifactDiff;
  const buildDefaultWorkflowStateValue = workflowActions.buildDefaultWorkflowState;
  const createWorkflowActionHandlersValue = workflowActions.createWorkflowActionHandlers;
  const createGhostActionHandlersValue = appGhostActions.createGhostActionHandlers;
  const createProjectActionHandlersValue = projectActions.createProjectActionHandlers;
  const createNodeActionHandlersValue = nodeActions.createNodeActionHandlers;

  if (
    !apiRequest ||
    !formatValue ||
    !shortIso ||
    !asNumber ||
    !MetaItem ||
    !Modal ||
    !rectAnchor ||
    !cubicMidpoint ||
    !splitNodeMetadata ||
    !asBoolean ||
    !inferRuntimePreset ||
    !loadWebStateValue ||
    !saveWebStateValue ||
    !safeArray ||
    !normalizeChatDiffSegments ||
    !normalizePersistedChatMessages ||
    !normalizePersistedMainView ||
    !normalizePersistedSidebarTab ||
    !ghostIdWithSeed ||
    !normalizeGhostSentiment ||
    !inferGhostSentimentFromText ||
    !normalizeGhostOutlineSteps ||
    !pickGhostOutlineSteps ||
    !normalizePersistedGhostArchive ||
    !ghostOutlineTextValue ||
    !sentimentToneColorValue ||
    !pruneGhostStateMapValue ||
    !edgeDisplayLabelValue ||
    !compareEdgesByNarrativeOrderValue ||
    !clampZoomValue ||
    !nodeMetadataObjectValue ||
    !readGroupBindingValue ||
    !applyGroupBindingValue ||
    !sceneRenderSizeByMetadataValue ||
    !groupRenderSizeByMetadataValue ||
    !findContainingGroupIdValue ||
    !formatAgentTraceValue ||
    !buildDiffSegmentsValue ||
    !renderMarkdownPreviewValue ||
    !parseWorkflowModeValue ||
    !isWorkflowBackgroundConfirmedValue ||
    !isWorkflowOutlineConfirmedValue ||
    !parseBeatListValue ||
    !beatTitleValue ||
    !normalizeDiffKindValue ||
    !diffPrefixValue ||
    !resolveActiveChatContextValue ||
    !nextArtifactDiffNodeIdValue ||
    !shouldShowArtifactDiffValue ||
    !buildDefaultWorkflowStateValue ||
    !createWorkflowActionHandlersValue ||
    !createGhostActionHandlersValue ||
    !createProjectActionHandlersValue ||
    !createNodeActionHandlersValue
  ) {
    throw new Error("Web runtime modules failed to load. Please check /web/static/web/*.js");
  }

  function App() {
    const buildDefaultWorkflowState = buildDefaultWorkflowStateValue;
    const resolveActiveChatContext = resolveActiveChatContextValue;
    const nextArtifactDiffNodeId = nextArtifactDiffNodeIdValue;
    const shouldShowArtifactDiff = shouldShowArtifactDiffValue;
    const normalizeDiffKind = normalizeDiffKindValue;
    const diffPrefix = diffPrefixValue;
    const [locale, setLocale] = useState(function () {
      const cached = window.localStorage.getItem("elyha_web_locale") || DEFAULT_LOCALE;
      return SUPPORTED_LOCALES.includes(cached) ? cached : DEFAULT_LOCALE;
    });
    const persistedWebStateRef = useRef(null);
    if (persistedWebStateRef.current === null) {
      persistedWebStateRef.current = loadWebState();
    }
    const persistedWebState = persistedWebStateRef.current || {};
    const persistedArtifactOpen = asBoolean(persistedWebState.artifact_open, false);
    const persistedChatOpen = asBoolean(persistedWebState.chat_open, false) && !persistedArtifactOpen;
    const [catalog, setCatalog] = useState({});
    const [projects, setProjects] = useState([]);
    const [projectId, setProjectId] = useState(function () {
      return typeof persistedWebState.project_id === "string" ? persistedWebState.project_id : "";
    });
    const [project, setProject] = useState(null);
    const [nodes, setNodes] = useState([]);
    const [edges, setEdges] = useState([]);
    const [selectedNodeId, setSelectedNodeId] = useState(function () {
      return typeof persistedWebState.selected_node_id === "string" ? persistedWebState.selected_node_id : "";
    });
    const [inspector, setInspector] = useState(null);
    const [newProjectTitle, setNewProjectTitle] = useState(function () {
      return typeof persistedWebState.new_project_title === "string" ? persistedWebState.new_project_title : "";
    });
    const [newNodeForm, setNewNodeForm] = useState(function () {
      const defaults = {
        title: "",
        type: "chapter",
        status: "draft",
        storyline_id: "",
        agent_preset: "",
        group_kind: "phase",
        group_width: "820",
        group_height: "460",
        pos_x: "120",
        pos_y: "120"
      };
      const raw = persistedWebState.new_node_form;
      if (!raw || typeof raw !== "object") {
        return defaults;
      }
      return Object.assign({}, defaults, raw);
    });
    const [projectSettingsForm, setProjectSettingsForm] = useState({
      auto_snapshot_minutes: "5",
      auto_snapshot_operations: "50"
    });
    const [outlineGuideForm, setOutlineGuideForm] = useState(function () {
      const defaults = {
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
      };
      const raw = persistedWebState.outline_guide_form;
      if (!raw || typeof raw !== "object") {
        return defaults;
      }
      const merged = Object.assign({}, defaults, raw);
      merged.questions = safeArray(merged.questions).map(String).slice(0, 16);
      merged.chapter_beats = safeArray(merged.chapter_beats).map(String).slice(0, 32);
      merged.next_steps = safeArray(merged.next_steps).map(String).slice(0, 16);
      return merged;
    });
    const [outlineGuideBusy, setOutlineGuideBusy] = useState(false);
    const [runtimeSettings, setRuntimeSettings] = useState({
      locale: DEFAULT_LOCALE,
      llm_provider: "mock",
      api_url: "",
      api_key: "",
      model_name: "",
      auto_complete: true,
      think_switch: false,
      think_depth: "medium",
      thinking_budget: 2048,
      web_search_enabled: false,
      web_search_context_size: "medium",
      web_search_max_results: 5,
      llm_request_timeout: 90,
      web_request_timeout_ms: 240000,
      default_token_budget: 2200,
      default_workflow_mode: "multi_agent",
      web_host: "127.0.0.1",
      web_port: 8765
    });
    const [runtimeProfiles, setRuntimeProfiles] = useState(["core"]);
    const [activeRuntimeProfile, setActiveRuntimeProfile] = useState("core");
    const [newRuntimeProfile, setNewRuntimeProfile] = useState("");
    const [renameRuntimeProfile, setRenameRuntimeProfile] = useState("");
    const [llmPresets, setLlmPresets] = useState([]);
    const [runtimePresetTag, setRuntimePresetTag] = useState("");
    const [sidebarTab, setSidebarTab] = useState(function () {
      return normalizePersistedSidebarTab(persistedWebState.sidebar_tab);
    });
    const [mainView, setMainView] = useState(function () {
      return normalizePersistedMainView(persistedWebState.main_view);
    });
    const [storylineFilter, setStorylineFilter] = useState(function () {
      return typeof persistedWebState.storyline_filter === "string"
        ? persistedWebState.storyline_filter
        : STORYLINE_ALL;
    });
    const [zoom, setZoom] = useState(function () {
      const raw = asNumber(persistedWebState.zoom, 1);
      if (!Number.isFinite(raw)) {
        return 1;
      }
      return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, raw));
    });
    const [aiConfig, setAiConfig] = useState(function () {
      const defaults = {
        token_budget: "2200",
        workflow_mode: "multi_agent"
      };
      const raw = persistedWebState.ai_config;
      if (!raw || typeof raw !== "object") {
        return defaults;
      }
      const merged = Object.assign({}, defaults, raw);
      merged.token_budget = String(merged.token_budget || defaults.token_budget);
      merged.workflow_mode = merged.workflow_mode === "single" ? "single" : "multi_agent";
      return merged;
    });
    const [aiResult, setAiResult] = useState("");
    const [edgeMode, setEdgeMode] = useState(function () {
      return asBoolean(persistedWebState.edge_mode, false);
    });
    const [autoBindOnDrop, setAutoBindOnDrop] = useState(function () {
      return asBoolean(persistedWebState.auto_bind_on_drop, true);
    });
    const [edgeSourceId, setEdgeSourceId] = useState("");
    const [validationReport, setValidationReport] = useState(null);
    const [activities, setActivities] = useState([]);
    const [toasts, setToasts] = useState([]);
    const [modal, setModal] = useState(null);
    const [chatOpen, setChatOpen] = useState(persistedChatOpen);
    const [artifactOpen, setArtifactOpen] = useState(persistedArtifactOpen);
    const [chatContextNodeId, setChatContextNodeId] = useState(function () {
      return typeof persistedWebState.chat_context_node_id === "string"
        ? persistedWebState.chat_context_node_id
        : "";
    });
    const [artifactContextNodeId, setArtifactContextNodeId] = useState(function () {
      return typeof persistedWebState.artifact_context_node_id === "string"
        ? persistedWebState.artifact_context_node_id
        : "";
    });
    const [chatInput, setChatInput] = useState(function () {
      return typeof persistedWebState.chat_input === "string" ? persistedWebState.chat_input : "";
    });
    const [chatMessages, setChatMessages] = useState(function () {
      return normalizePersistedChatMessages(persistedWebState.chat_messages);
    });
    const [chatBusy, setChatBusy] = useState(false);
    const [chatWorkflow, setChatWorkflow] = useState(function () {
      return buildDefaultWorkflowState();
    });
    const [artifactDiffSegments, setArtifactDiffSegments] = useState([]);
    const [artifactDiffNodeId, setArtifactDiffNodeId] = useState("");
    const [collapsedGroupIds, setCollapsedGroupIds] = useState(function () {
      const raw = persistedWebState.collapsed_group_ids;
      if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
        return {};
      }
      return Object.assign({}, raw);
    });
    const [ghostPlans, setGhostPlans] = useState([]);
    const [ghostArchive, setGhostArchive] = useState(function () {
      return normalizePersistedGhostArchive(persistedWebState.ghost_archive);
    });
    const [expandedGhostIds, setExpandedGhostIds] = useState({});
    const [selectedGhostIds, setSelectedGhostIds] = useState({});
    const [retiringGhostIds, setRetiringGhostIds] = useState({});
    const [ghostFusionBusy, setGhostFusionBusy] = useState(false);
    const [nodeFlowStates, setNodeFlowStates] = useState({});
    const [insightData, setInsightData] = useState(null);
    const [insightBusy, setInsightBusy] = useState(false);
    const [insightError, setInsightError] = useState("");
    const [insightHighlightNodeIds, setInsightHighlightNodeIds] = useState([]);

    const modalResolverRef = useRef(null);
    const nodesRef = useRef(nodes);
    const viewportRef = useRef(null);
    const contextMenuSuppressUntilRef = useRef(0);
    const ghostClickSuppressUntilRef = useRef(0);
    const chatLogRef = useRef(null);
    const outlineRequired = Boolean(projectId) && nodes.length === 0 && !hasProjectOutline(nodes);
    useEffect(
      function () {
        nodesRef.current = nodes;
      },
      [nodes]
    );

    useEffect(
      function () {
        setCollapsedGroupIds(function (prev) {
          const next = Object.assign({}, prev);
          let changed = false;
          const groupIds = new Set(
            nodes
              .filter(function (node) {
                return node.type === "group";
              })
              .map(function (node) {
                return node.id;
              })
          );
          groupIds.forEach(function (groupId) {
            if (!(groupId in next)) {
              next[groupId] = true;
              changed = true;
            }
          });
          Object.keys(next).forEach(function (groupId) {
            if (!groupIds.has(groupId)) {
              delete next[groupId];
              changed = true;
            }
          });
          return changed ? next : prev;
        });
      },
      [nodes]
    );

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
      const entry = {
        id: "chat_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 8),
        role: role,
        text: String(text || ""),
        meta: meta || "",
        at: new Date().toISOString(),
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
      appendChatMessage("user", text, contextNodeId ? t("web.chat.context_node", { node_id: contextNodeId }) : t("web.chat.context_global"));
      setChatInput("");
      setChatBusy(true);
      const consumedByWorkflow = await handleWorkflowChat(text);
      if (consumedByWorkflow) {
        setChatBusy(false);
        return;
      }
      if (isMockProvider()) {
        const blocked = t("web.ai.mock_blocked");
        appendChatMessage("assistant", blocked, t("web.chat.route_label", { route: "blocked" }));
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
              message: text,
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
          t("web.chat.route_label", { route: "error" })
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
      const replyText = String(payload.reply || "");
      let diffSegments = [];
      if (route === "writer" && contextNodeId) {
        diffSegments = buildDiffSegments(beforeContent, replyText);
        applyNodeContentPatchLocal(contextNodeId, replyText);
      }
      setArtifactDiffNodeId(nextArtifactDiffNodeId(route, contextNodeId));
      setArtifactDiffSegments(diffSegments);
      appendChatMessage("assistant", replyText, meta, { diffSegments: diffSegments });
      const options = Array.isArray(payload.suggested_options) ? payload.suggested_options : [];
      if (route === "planner" && contextNodeId && options.length > 0) {
        const nextGhosts = createGhostPlansFromOptions(contextNodeId, options);
        if (nextGhosts.length > 0) {
          setGhostPlans(function (prev) {
            const keep = prev.filter(function (item) {
              return item.source_id !== contextNodeId;
            });
            return keep.concat(nextGhosts);
          });
          pushToast("ok", t("web.chat.suggested_created", { count: nextGhosts.length }));
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
      chatWorkflow: chatWorkflow
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
                nextBinding = "bound";
                nextParentId = matchedGroupId;
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
            text: t("web.workflow.welcome"),
            meta: "workflow_init",
            at: new Date().toISOString(),
            diffSegments: []
          };
          return prev.concat(hello).slice(-120);
        });
      },
      [projectId, outlineRequired, chatOpen, chatContextNodeId]
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
      [chatMessages, chatOpen]
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

    function setInspectorField(key, value) {
      setInspector(function (prev) {
        if (!prev) {
          return prev;
        }
        return Object.assign({}, prev, { [key]: value });
      });
    }

    const validationItems = validationReport && Array.isArray(validationReport.issues)
      ? validationReport.issues
      : [];

    const projectOptions = projects.map(function (item) {
      return h(
        "option",
        {
          key: item.id,
          value: item.id
        },
        item.title + " (" + item.id + ")"
      );
    });

    const edgeItems = edgeShapes.length > 0
      ? edgeShapes.map(function (shape) {
          const sourceNode = nodeById[shape.edge.source_id];
          const sourceIsGroup = sourceNode && sourceNode.type === "group";
          return h(
            "div",
            { className: "edge-item", key: shape.edge.id },
            h(
              "div",
              { className: "edge-info" },
                h("strong", null, shape.sourceTitle + " -> " + shape.targetTitle),
                h("div", { className: "muted" }, edgeDisplayLabel(shape.edge) || "-")
              ),
            h(
              "div",
              { className: "row" },
              h(
                "button",
                {
                  className: "mini-btn",
                  disabled: sourceIsGroup,
                  onClick: function () {
                    void reorderEdge(shape.edge.id, -1);
                  }
                },
                t("web.edge.order_up")
              ),
              h(
                "button",
                {
                  className: "mini-btn",
                  disabled: sourceIsGroup,
                  onClick: function () {
                    void reorderEdge(shape.edge.id, 1);
                  }
                },
                t("web.edge.order_down")
              ),
              h(
                "button",
                {
                  className: "mini-btn",
                  onClick: function () {
                    void deleteEdge(shape.edge.id);
                  }
                },
                t("web.edge.delete")
              )
            )
          );
        })
      : [h("div", { className: "muted", key: "edge-empty" }, "-")];

    const activityItems = activities.length > 0
      ? activities.map(function (item) {
          return h(
            "div",
            { className: "activity-item", key: item.id },
            h("strong", { className: "activity-kind " + item.kind }, item.kind.toUpperCase()),
            h("div", null, item.message),
            h("div", { className: "muted" }, shortIso(item.at))
          );
        })
      : [h("div", { className: "muted", key: "activity-empty" }, t("web.activity.empty"))];

    const validationNodes = validationItems.length > 0
      ? validationItems.map(function (issue, index) {
          return h(
            "div",
            { className: "validation-item", key: issue.code + "_" + index.toString() },
            h(
              "div",
              { className: "validation-head" },
              h("strong", null, issue.level),
              h("span", { className: "muted" }, issue.code)
            ),
            h("div", null, issue.message),
            issue.node_id ? h("div", { className: "muted" }, "node: " + issue.node_id) : null,
            issue.edge_id ? h("div", { className: "muted" }, "edge: " + issue.edge_id) : null
          );
        })
      : [h("div", { className: "muted", key: "validation-empty" }, t("web.validation.empty"))];

    const orderedNodes = useMemo(
      function () {
        return visibleNodes
          .slice()
          .sort(function (left, right) {
            const leftRank = left.type === "group" ? 0 : 1;
            const rightRank = right.type === "group" ? 0 : 1;
            return leftRank - rightRank;
          });
      },
      [visibleNodes]
    );

    const groupNodes = useMemo(
      function () {
        return nodes
          .filter(function (item) {
            return item.type === "group";
          })
          .sort(function (left, right) {
            return String(left.title).localeCompare(String(right.title));
          });
      },
      [nodes]
    );
    const nodesView = orderedNodes.map(function (node) {
      const nodeClass = ["node-card"];
      const isGroup = node.type === "group";
      const collapsed = isGroup && isGroupCollapsed(node.id);
      const nodeSize = nodeRenderSize(node);
      const groupKind = node.metadata && node.metadata.group_kind === "chapter" ? "chapter" : "phase";
      const bindingInfo = readGroupBinding(nodeMetadataObject(node));
      const storyline = String(node.storyline_id || "").trim();
      const storylineTone = storylineColor(storyline);
      if (node.id === selectedNodeId) {
        nodeClass.push("selected");
      }
      if (edgeMode && node.id === edgeSourceId) {
        nodeClass.push("edge-source");
      }
      if (isGroup) {
        nodeClass.push("group-frame");
      }
      if (collapsed) {
        nodeClass.push("collapsed-group");
      }
      if (nodeIsSuggested(node)) {
        nodeClass.push("suggested-node");
      }
      if (storylineTone) {
        nodeClass.push("storyline-tagged");
      }
      if (insightHighlightSet.has(node.id)) {
        nodeClass.push("highlight-node");
      }
      const flow = nodeFlowStates[node.id];
      if (flow) {
        nodeClass.push("flow-active");
      }
      let zIndex = isGroup ? 1 : 3;
      if (node.id === selectedNodeId) {
        zIndex = isGroup ? 2 : 4;
      }

      return h(
        "div",
        {
          key: node.id,
          className: nodeClass.join(" "),
          style: {
            left: asNumber(node.pos_x, 0) + "px",
            top: asNumber(node.pos_y, 0) + "px",
            width: nodeSize.width + "px",
            minHeight: nodeSize.height + "px",
            zIndex: zIndex,
            "--storyline-color": storylineTone || undefined
          },
          onClick: function () {
            onNodeClick(node.id);
          },
          onDoubleClick: function () {
            openChatForNode(node.id);
          }
        },
        h(
          "div",
          {
            className: "node-head" + (isGroup ? " group-head" : ""),
            onMouseDown: function (event) {
              beginDrag(event, node);
            }
          },
          h("span", { className: "node-title" }, node.title),
          isGroup
            ? h(
                "button",
                {
                  className: "mini-toggle",
                  onMouseDown: function (event) {
                    event.stopPropagation();
                  },
                  onClick: function (event) {
                    event.stopPropagation();
                    toggleGroupCollapsed(node.id);
                  }
                },
                collapsed ? t("web.group.expand") : t("web.group.collapse")
              )
            : null,
          h("span", { className: "node-pill" }, isGroup ? groupKindLabel(groupKind) : nodeStatusLabel(node.status))
        ),
        h(
          "div",
          { className: "node-body" },
          h("span", { className: "node-type" }, nodeTypeLabel(node.type)),
          storyline ? h("span", { className: "muted" }, t("web.node.storyline", { storyline: storyline })) : null,
          isGroup
            ? h("span", { className: "muted" }, t("web.node.group_hint", { kind: groupKindLabel(groupKind) }))
            : h("span", null, node.id),
          !isGroup && bindingInfo.binding === "bound" && bindingInfo.parentId
            ? h("span", { className: "muted" }, t("web.node.bound_to", { group_id: bindingInfo.parentId }))
            : null,
          isGroup
            ? h(
                "span",
                { className: "muted" },
                "w=" + Math.round(nodeSize.width) + ", h=" + Math.round(nodeSize.height)
              )
            : h(
                "span",
                { className: "muted" },
                "x=" +
                  node.pos_x +
                  ", y=" +
                  node.pos_y +
                  ", w=" +
                  Math.round(nodeSize.width) +
                  ", h=" +
                  Math.round(nodeSize.height)
              ),
          isGroup && collapsed ? h("span", { className: "muted" }, t("web.group.collapsed_hint")) : null,
          flow && Array.isArray(flow.phases) && flow.phases.length > 0
            ? h("span", { className: "flow-chip" }, t("web.node.flow." + flow.phases[flow.index]))
            : null
        ),
        !collapsed
          ? h(
              "div",
              {
                className: "node-resize-handle" + (isGroup ? " group-resize-handle" : ""),
                onMouseDown: function (event) {
                  beginNodeResize(event, node);
                }
              },
              " "
            )
          : null
      );
    });

    const ghostNodesView = visibleGhostPlans.map(function (plan) {
      const storyline = String(plan.storyline_id || "").trim();
      const tone = storylineColor(storyline);
      const outline = ghostOutlineText(plan);
      const sentiment = normalizeGhostSentiment(plan.sentiment || inferGhostSentimentFromText(plan.title, outline));
      const sentimentTone = sentimentToneColor(sentiment);
      const expanded = Boolean(expandedGhostIds[plan.id]);
      const selectedForFusion = Boolean(selectedGhostIds[plan.id]);
      const retiring = Boolean(retiringGhostIds[plan.id]);
      const classes = ["node-card", "ghost-node"];
      if (tone) {
        classes.push("storyline-tagged");
      }
      classes.push("ghost-sentiment-" + sentiment);
      if (selectedForFusion) {
        classes.push("ghost-selected");
      }
      if (retiring) {
        classes.push("ghost-retiring");
      }
      return h(
        "div",
        {
          key: plan.id,
          className: classes.join(" "),
          style: {
            left: asNumber(plan.pos_x, 0) + "px",
            top: asNumber(plan.pos_y, 0) + "px",
            width: NODE_WIDTH + "px",
            minHeight: NODE_HEIGHT + "px",
            zIndex: 5,
            "--storyline-color": tone || undefined,
            "--ghost-tone-color": sentimentTone
          },
          onClick: function (event) {
            event.stopPropagation();
          }
        },
        h(
          "div",
          {
            className: "node-head",
            onMouseDown: function (event) {
              beginGhostDrag(event, plan);
            }
          },
          h("span", { className: "node-title" }, plan.title),
          h(
            "span",
            { className: "node-pill ghost-pill" },
            t("web.ghost.badge") + " · " + t("web.ghost.sentiment." + sentiment)
          )
        ),
        h(
          "div",
          { className: "node-body" },
          h("span", { className: "ghost-sentiment-label " + sentiment }, t("web.ghost.sentiment." + sentiment)),
          storyline ? h("span", { className: "muted" }, t("web.node.storyline", { storyline: storyline })) : null,
          h("span", { className: "ghost-outline compact", title: outline || "-" }, outline || "-"),
          expanded
            ? h(
                "div",
                { className: "ghost-preview-inline" },
                h(
                  "span",
                  { className: "ghost-preview-title" },
                  t("web.ghost.preview_source", { source: plan.source_title || plan.source_id || "-" })
                ),
                h("span", { className: "ghost-preview-body" }, outline || "-")
              )
            : null,
          h(
            "div",
            { className: "ghost-actions" },
            h(
              "button",
              {
                className: "ghost-node-btn",
                onClick: function (event) {
                  event.stopPropagation();
                  if (Date.now() <= ghostClickSuppressUntilRef.current) {
                    return;
                  }
                  void previewGhostPlan(plan.id);
                }
              },
              expanded ? t("web.ghost.preview_hide") : t("web.ghost.preview")
            ),
            h(
              "button",
              {
                className: "ghost-node-btn" + (selectedForFusion ? " selected" : ""),
                onClick: function (event) {
                  event.stopPropagation();
                  if (Date.now() <= ghostClickSuppressUntilRef.current) {
                    return;
                  }
                  toggleGhostSelection(plan.id);
                }
              },
              selectedForFusion ? t("web.ghost.selected") : t("web.ghost.select")
            ),
            h(
              "button",
              {
                className: "ghost-node-btn adopt",
                onClick: function (event) {
                  event.stopPropagation();
                  void adoptGhostPlan(plan.id);
                }
              },
              t("web.ghost.adopt")
            ),
            h(
              "button",
              {
                className: "ghost-node-btn delete",
                onClick: function (event) {
                  event.stopPropagation();
                  deleteGhostRoute(plan.id);
                }
              },
              t("web.ghost.delete_route")
            ),
            selectedGhostCount === 2 && selectedForFusion
              ? h(
                  "button",
                  {
                    className: "ghost-node-btn fuse",
                    disabled: ghostFusionBusy,
                    onClick: function (event) {
                      event.stopPropagation();
                      if (ghostFusionBusy) {
                        return;
                      }
                      void fuseSelectedGhostPlans();
                    }
                  },
                  ghostFusionBusy ? t("web.ghost.fusing") : t("web.ghost.fuse")
                )
              : null
          ),
          selectedGhostCount === 2 && selectedForFusion
            ? h("span", { className: "muted ghost-fuse-hint" }, t("web.ghost.fuse_ready_hint"))
            : null
        )
      );
    });

    const toastsView = toasts.map(function (toast) {
      const toastClass = ["toast"];
      if (toast.level === "warn") {
        toastClass.push("warn");
      }
      if (toast.level === "error") {
        toastClass.push("error");
      }
      return h(
        "div",
        { key: toast.id, className: toastClass.join(" ") },
        toast.message
      );
    });

    const sidebarTabs = [
      { id: "project", label: t("web.sidebar.tab.project") },
      { id: "runtime", label: t("web.sidebar.tab.runtime") },
      { id: "node", label: t("web.sidebar.tab.node") },
      { id: "ai", label: t("web.sidebar.tab.ai") },
      { id: "ops", label: t("web.sidebar.tab.ops") },
      { id: "tutorial", label: t("web.sidebar.tab.tutorial") }
    ];

    const chatContextOptions = nodes
      .slice()
      .sort(function (left, right) {
        return String(left.title).localeCompare(String(right.title));
      });
    const chatMessageViews = chatMessages.length > 0
      ? chatMessages.map(function (item) {
          const roleClass = item.role === "assistant" ? "assistant" : "user";
          return h(
            "div",
            { key: item.id, className: "chat-msg " + roleClass },
            h("div", { className: "chat-msg-head" }, (item.role === "assistant" ? "AI" : "You") + " · " + shortIso(item.at)),
            item.meta ? h("div", { className: "chat-msg-meta" }, item.meta) : null,
            h("div", { className: "chat-msg-body" }, item.text || "-"),
            item.role === "assistant" &&
              Array.isArray(item.diffSegments) &&
              item.diffSegments.length > 0
              ? h(
                  "div",
                  { className: "chat-diff-block" },
                  h("div", { className: "chat-diff-title" }, t("web.chat.diff_title")),
                  h(
                    "div",
                    { className: "chat-diff-body" },
                    item.diffSegments.slice(0, 420).map(function (segment, index) {
                      const kind = normalizeDiffKind(segment && segment.type);
                      const className = "chat-diff-row chat-diff-row-" + kind;
                      return h(
                        "div",
                        { key: item.id + "_diff_" + index.toString(), className: className },
                        h("span", { className: "chat-diff-prefix" }, diffPrefix(kind)),
                        h("span", { className: "chat-diff-text" }, String(segment && segment.text ? segment.text : ""))
                      );
                    })
                  )
                )
              : null
          );
        })
      : [h("div", { className: "muted", key: "chat-empty" }, t("web.chat.empty"))];
    const ghostArchiveViews = visibleGhostArchive.length > 0
      ? visibleGhostArchive.slice(0, 24).map(function (item) {
          const payload = item.payload && typeof item.payload === "object" ? item.payload : {};
          const sentiment = normalizeGhostSentiment(payload.sentiment);
          const outline = ghostOutlineText(payload);
          return h(
            "div",
            { className: "ghost-archive-item", key: item.id },
            h(
              "div",
              { className: "ghost-archive-head" },
              h("strong", null, String(payload.title || t("web.ghost.untitled"))),
              h("span", { className: "ghost-sentiment-label " + sentiment }, t("web.ghost.sentiment." + sentiment))
            ),
            h("div", { className: "muted ghost-archive-meta" }, shortIso(item.archived_at)),
            h("div", { className: "ghost-archive-outline" }, outline || "-"),
            h(
              "div",
              { className: "row" },
              h(
                "button",
                {
                  className: "mini-btn",
                  onClick: function () {
                    restoreGhostFromArchive(item.id);
                  }
                },
                t("web.ghost.archive_restore")
              ),
              h(
                "button",
                {
                  className: "mini-btn",
                  onClick: function () {
                    removeGhostArchiveItem(item.id);
                  }
                },
                t("web.ghost.archive_delete")
              )
            )
          );
        })
      : [h("div", { className: "muted", key: "ghost-archive-empty" }, t("web.ghost.archive_empty"))];
    const artifactTargetId = String(artifactContextNodeId || "").trim();
    const artifactContextNode = nodes.find(function (item) {
      return item.id === artifactTargetId;
    });
    const artifactPreview = artifactContextNode
      ? nodeContentOf(artifactContextNode.id)
      : "";
    const artifactContextText = artifactContextNode
      ? t("web.chat.context_node", { node_id: artifactContextNode.id })
      : t("web.chat.context_global");
    const artifactDiffVisible = shouldShowArtifactDiff(artifactTargetId, artifactDiffNodeId, artifactDiffSegments);

    const insightPayload = insightData && typeof insightData === "object" ? insightData : null;
    const insightWords = insightPayload && Array.isArray(insightPayload.word_frequency) ? insightPayload.word_frequency : [];
    const insightStorylines = insightPayload && Array.isArray(insightPayload.storylines) ? insightPayload.storylines : [];
    const insightCharacters = insightPayload && Array.isArray(insightPayload.characters) ? insightPayload.characters : [];
    const insightWorldviews = insightPayload && Array.isArray(insightPayload.worldviews) ? insightPayload.worldviews : [];
    const insightItems = insightPayload && Array.isArray(insightPayload.items) ? insightPayload.items : [];
    const relationGraph =
      insightPayload && insightPayload.relation_graph && typeof insightPayload.relation_graph === "object"
        ? insightPayload.relation_graph
        : { nodes: [], edges: [] };
    const relationNodes = Array.isArray(relationGraph.nodes) ? relationGraph.nodes : [];
    const relationEdges = Array.isArray(relationGraph.edges) ? relationGraph.edges : [];
    const relationWidth = 980;
    const relationHeight = 620;
    const relationCx = relationWidth / 2;
    const relationCy = relationHeight / 2;
    const relationRadius = Math.max(180, Math.min(270, relationNodes.length * 16));
    const relationLayout = relationNodes.map(function (node, index) {
      const angle = ((index + 1) / Math.max(1, relationNodes.length)) * Math.PI * 2;
      return {
        node: node,
        x: relationCx + Math.cos(angle) * relationRadius,
        y: relationCy + Math.sin(angle) * relationRadius
      };
    });
    const relationPosById = {};
    relationLayout.forEach(function (item) {
      relationPosById[item.node.id] = item;
    });

    return h(
      React.Fragment,
      null,
      h("div", { className: "backdrop" }),
      h(
        "div",
        { className: "shell" },
        h(
          "header",
          { className: "topbar panel" },
          h(
            "div",
            { className: "topbar-title" },
            h("h1", null, t("web.app.title")),
            h("p", null, t("web.app.subtitle"))
          ),
          h(
            "div",
            { className: "topbar-actions" },
            h(
              "button",
              {
                className: "btn ghost",
                onClick: function () {
                  if (!projectId) {
                    void refreshProjects("");
                    return;
                  }
                  void refreshProjectData(projectId, true);
                }
              },
              t("web.top.refresh_graph")
            ),
            h(
              "div",
              { className: "main-view-switch" },
              h(
                "button",
                {
                  className: "btn ghost" + (mainView === "story" ? " active" : ""),
                  onClick: function () {
                    setMainView("story");
                  }
                },
                t("web.main_view.story")
              ),
              h(
                "button",
                {
                  className: "btn ghost" + (mainView === "insight" ? " active" : ""),
                  onClick: function () {
                    setMainView("insight");
                  }
                },
                t("web.main_view.insight")
              )
            ),
            h(
              "button",
              {
                className: "btn",
                onClick: function () {
                  void validateGraph();
                }
              },
              t("web.top.validate")
            ),
            h(
              "button",
              {
                className: "btn",
                onClick: function () {
                  void exportGraph();
                }
              },
              t("web.top.export")
            ),
            h(
              "button",
              {
                className: "btn ghost",
                onClick: function () {
                  void openTutorialModal();
                }
              },
              t("web.top.tutorial")
            ),
            h(
              "label",
              { className: "locale-wrap" },
              h("span", { className: "muted" }, t("web.top.locale_label")),
              h(
                "select",
                {
                  value: locale,
                  onChange: onLocaleChange
                },
                SUPPORTED_LOCALES.map(function (item) {
                  return h(
                    "option",
                    { key: item, value: item },
                    item
                  );
                })
              )
            )
          )
        ),
        h(
          "main",
          { className: "workspace" },
          h(
            "aside",
            { className: "sidebar" },
            h(
              "section",
              { className: "panel section sidebar-tabs" },
              h(
                "div",
                { className: "subtab-bar" },
                sidebarTabs.map(function (tab) {
                  return h(
                    "button",
                    {
                      key: tab.id,
                      className: "btn ghost subtab-btn" + (sidebarTab === tab.id ? " active" : ""),
                      onClick: function () {
                        setSidebarTab(tab.id);
                      }
                    },
                    tab.label
                  );
                })
              )
            ),
            h(
              "section",
              { className: "panel section", hidden: sidebarTab !== "tutorial" },
              h("h2", null, t("web.section.tutorial")),
              h(
                "ol",
                { className: "tutorial-list" },
                h("li", null, t("web.tutorial.step_1")),
                h("li", null, t("web.tutorial.step_2")),
                h("li", null, t("web.tutorial.step_3")),
                h("li", null, t("web.tutorial.step_4")),
                h("li", null, t("web.tutorial.step_5")),
                h("li", null, t("web.tutorial.step_6"))
              ),
              h(
                "button",
                {
                  className: "btn ghost full",
                  onClick: function () {
                    void openTutorialModal();
                  }
                },
                t("web.tutorial.open_modal")
              )
            ),
            h(
              "section",
              { className: "panel section", hidden: sidebarTab !== "runtime" },
              h("h2", null, t("web.section.runtime")),
              h("div", { className: "muted profile-note" }, t("web.runtime.core_readonly")),
              h(
                "div",
                { className: "row" },
                h(
                  "select",
                  {
                    value: activeRuntimeProfile,
                    onChange: function (event) {
                      void switchRuntimeProfile(event.target.value, false);
                    }
                  },
                  runtimeProfiles.map(function (item) {
                    return h("option", { key: item, value: item }, item);
                  })
                ),
                h(
                  "button",
                  {
                    className: "btn ghost",
                    onClick: function () {
                      void loadRuntimeSettings();
                    }
                  },
                  t("web.project.reload")
                )
              ),
              h(
                "div",
                { className: "row" },
                h("input", {
                  value: newRuntimeProfile,
                  placeholder: t("web.runtime.new_profile_placeholder"),
                  onChange: function (event) {
                    setNewRuntimeProfile(event.target.value);
                  }
                }),
                h(
                  "button",
                  {
                    className: "btn",
                    onClick: function () {
                      void createRuntimeProfile();
                    }
                  },
                  t("web.runtime.create_profile")
                )
              ),
              h(
                "div",
                { className: "row" },
                h("input", {
                  value: renameRuntimeProfile,
                  placeholder: t("web.runtime.rename_profile_placeholder"),
                  disabled: activeRuntimeProfile === "core",
                  onChange: function (event) {
                    setRenameRuntimeProfile(event.target.value);
                  }
                }),
                h(
                  "button",
                  {
                    className: "btn ghost",
                    disabled: activeRuntimeProfile === "core",
                    onClick: function () {
                      void renameActiveRuntimeProfile();
                    }
                  },
                  t("web.runtime.rename_profile")
                )
              ),
              h(
                "div",
                { className: "row" },
                h(
                  "button",
                  {
                    className: "btn danger full",
                    disabled: activeRuntimeProfile === "core",
                    onClick: function () {
                      void deleteActiveRuntimeProfile();
                    }
                  },
                  t("web.runtime.delete_profile")
                )
              ),
              h(
                "div",
                { className: "form-grid" },
                h(
                  "label",
                  { className: "field-label" },
                  h("span", null, t("web.runtime.provider")),
                  h(
                    "select",
                    {
                      value: runtimeSettings.llm_provider,
                      disabled: activeRuntimeProfile === "core",
                      onChange: function (event) {
                        setRuntimeField("llm_provider", event.target.value);
                      }
                    },
                    h("option", { value: "mock" }, "mock"),
                    h("option", { value: "legacy" }, "legacy"),
                    h("option", { value: "llmrequester" }, "llmrequester")
                  )
                ),
                h(
                  "label",
                  { className: "field-label" },
                  h("span", null, t("web.runtime.preset")),
                  h(
                    "select",
                    {
                      value: runtimePresetTag,
                      disabled: activeRuntimeProfile === "core",
                      onChange: function (event) {
                        applyRuntimePreset(event.target.value);
                      }
                    },
                    h("option", { value: "" }, t("web.runtime.preset_none")),
                    llmPresets.map(function (preset) {
                      return h(
                        "option",
                        { key: preset.tag, value: preset.tag },
                        preset.name + " (" + preset.tag + ")"
                      );
                    })
                  )
                ),
                h(
                  "label",
                  { className: "field-label" },
                  h("span", null, t("web.runtime.api_url")),
                  h("input", {
                    value: runtimeSettings.api_url,
                    disabled: activeRuntimeProfile === "core",
                    onChange: function (event) {
                      setRuntimeField("api_url", event.target.value);
                    }
                  })
                ),
                h(
                  "label",
                  { className: "field-label" },
                  h("span", null, t("web.runtime.api_key")),
                  h("input", {
                    type: "password",
                    value: runtimeSettings.api_key,
                    disabled: activeRuntimeProfile === "core",
                    onChange: function (event) {
                      setRuntimeField("api_key", event.target.value);
                    }
                  })
                ),
                h(
                  "label",
                  { className: "field-label" },
                  h("span", null, t("web.runtime.model_name")),
                  h("input", {
                    value: runtimeSettings.model_name,
                    disabled: activeRuntimeProfile === "core",
                    onChange: function (event) {
                      setRuntimeField("model_name", event.target.value);
                    }
                  })
                ),
                h(
                  "label",
                  { className: "field-label checkbox-field" },
                  h("span", null, t("web.runtime.auto_complete")),
                  h(
                    "div",
                    { className: "checkbox-inline" },
                    h("input", {
                      type: "checkbox",
                      checked: Boolean(runtimeSettings.auto_complete),
                      disabled: activeRuntimeProfile === "core",
                      onChange: function (event) {
                        setRuntimeField("auto_complete", Boolean(event.target.checked));
                      }
                    }),
                    h("span", null, t("web.runtime.auto_complete_hint"))
                  )
                ),
                h(
                  "label",
                  { className: "field-label checkbox-field" },
                  h("span", null, t("web.runtime.think_switch")),
                  h(
                    "div",
                    { className: "checkbox-inline" },
                    h("input", {
                      type: "checkbox",
                      checked: Boolean(runtimeSettings.think_switch),
                      disabled: activeRuntimeProfile === "core",
                      onChange: function (event) {
                        setRuntimeField("think_switch", Boolean(event.target.checked));
                      }
                    }),
                    h("span", null, t("web.runtime.think_depth"))
                  )
                ),
                h(
                  "div",
                  { className: "row compact" },
                  h(
                    "select",
                    {
                      value: runtimeSettings.think_depth,
                      disabled: activeRuntimeProfile === "core",
                      onChange: function (event) {
                        setRuntimeField("think_depth", event.target.value);
                      }
                    },
                    h("option", { value: "low" }, "low"),
                    h("option", { value: "medium" }, "medium"),
                    h("option", { value: "high" }, "high")
                  ),
                  h("input", {
                    value: runtimeSettings.thinking_budget,
                    placeholder: t("web.runtime.thinking_budget"),
                    disabled: activeRuntimeProfile === "core",
                    onChange: function (event) {
                      setRuntimeField("thinking_budget", event.target.value);
                    }
                  })
                ),
                h(
                  "label",
                  { className: "field-label checkbox-field" },
                  h("span", null, t("web.runtime.web_search_enabled")),
                  h(
                    "div",
                    { className: "checkbox-inline" },
                    h("input", {
                      type: "checkbox",
                      checked: Boolean(runtimeSettings.web_search_enabled),
                      disabled: activeRuntimeProfile === "core",
                      onChange: function (event) {
                        setRuntimeField("web_search_enabled", Boolean(event.target.checked));
                      }
                    }),
                    h("span", null, t("web.runtime.search_hint"))
                  )
                ),
                h(
                  "div",
                  { className: "row compact" },
                  h(
                    "select",
                    {
                      value: runtimeSettings.web_search_context_size,
                      disabled: activeRuntimeProfile === "core",
                      onChange: function (event) {
                        setRuntimeField("web_search_context_size", event.target.value);
                      }
                    },
                    h("option", { value: "low" }, "low"),
                    h("option", { value: "medium" }, "medium"),
                    h("option", { value: "high" }, "high")
                  ),
                  h("input", {
                    value: runtimeSettings.web_search_max_results,
                    placeholder: t("web.runtime.web_search_max_results"),
                    disabled: activeRuntimeProfile === "core",
                    onChange: function (event) {
                      setRuntimeField("web_search_max_results", event.target.value);
                    }
                  })
                ),
                h(
                  "div",
                  { className: "row compact" },
                  h("input", {
                    value: runtimeSettings.llm_request_timeout,
                    placeholder: t("web.runtime.llm_request_timeout"),
                    disabled: activeRuntimeProfile === "core",
                    onChange: function (event) {
                      setRuntimeField("llm_request_timeout", event.target.value);
                    }
                  }),
                  h("input", {
                    value: runtimeSettings.web_request_timeout_ms,
                    placeholder: t("web.runtime.web_request_timeout_ms"),
                    disabled: activeRuntimeProfile === "core",
                    onChange: function (event) {
                      setRuntimeField("web_request_timeout_ms", event.target.value);
                    }
                  })
                ),
                h(
                  "div",
                  { className: "row compact" },
                  h("input", {
                    value: runtimeSettings.default_token_budget,
                    placeholder: t("web.runtime.default_token_budget"),
                    disabled: activeRuntimeProfile === "core",
                    onChange: function (event) {
                      setRuntimeField("default_token_budget", event.target.value);
                    }
                  }),
                  h(
                    "select",
                    {
                      value: runtimeSettings.default_workflow_mode,
                      disabled: activeRuntimeProfile === "core",
                      onChange: function (event) {
                        setRuntimeField("default_workflow_mode", event.target.value);
                      }
                    },
                    h("option", { value: "multi_agent" }, "multi_agent"),
                    h("option", { value: "single" }, "single")
                  )
                ),
                h(
                  "div",
                  { className: "row compact" },
                  h("input", {
                    value: runtimeSettings.web_host,
                    placeholder: t("web.runtime.web_host"),
                    disabled: activeRuntimeProfile === "core",
                    onChange: function (event) {
                      setRuntimeField("web_host", event.target.value);
                    }
                  }),
                  h("input", {
                    value: runtimeSettings.web_port,
                    placeholder: t("web.runtime.web_port"),
                    disabled: activeRuntimeProfile === "core",
                    onChange: function (event) {
                      setRuntimeField("web_port", event.target.value);
                    }
                  })
                ),
                h("div", { className: "muted profile-note" }, t("web.runtime.port_note")),
                h(
                  "div",
                  { className: "row" },
                  h(
                    "button",
                    {
                      className: "btn",
                      disabled: activeRuntimeProfile === "core",
                      onClick: function () {
                        void saveRuntimeSettings();
                      }
                    },
                    t("web.runtime.save")
                  ),
                  h(
                    "button",
                    {
                      className: "btn ghost",
                      onClick: applyRuntimeDefaults
                    },
                    t("web.runtime.apply_defaults")
                  )
                )
              )
            ),
            h(
              "section",
              { className: "panel section", hidden: sidebarTab !== "project" },
              h("h2", null, t("web.section.project")),
              h(
                "div",
                { className: "row" },
                h(
                  "select",
                  {
                    value: projectId,
                    onChange: function (event) {
                      setProjectId(event.target.value);
                    }
                  },
                  projectOptions.length > 0
                    ? projectOptions
                    : h("option", { value: "" }, t("web.project.no_projects"))
                ),
                h(
                  "button",
                  {
                    className: "btn ghost",
                    onClick: function () {
                      void refreshProjects(projectId);
                    }
                  },
                  t("web.project.reload")
                )
              ),
              h(
                "div",
                { className: "row" },
                h("input", {
                  value: newProjectTitle,
                  placeholder: t("web.project.new_placeholder"),
                  onChange: function (event) {
                    setNewProjectTitle(event.target.value);
                  }
                }),
                h(
                  "button",
                  {
                    className: "btn",
                    onClick: function () {
                      void createProject();
                    }
                  },
                  t("web.project.create")
                )
              ),
              project && outlineRequired
                ? h(
                    "div",
                    { className: "outline-guide-card" },
                    h("h3", null, t("web.outline.required_title")),
                    h("div", { className: "muted" }, t("web.outline.required_desc")),
                    h("div", { className: "muted outline-guide-tip" }, t("web.outline.flow_tip")),
                    h(
                      "div",
                      { className: "form-grid" },
                      h(
                        "label",
                        { className: "field-label" },
                        h("span", null, t("web.outline.goal")),
                        h("textarea", {
                          rows: 2,
                          value: outlineGuideForm.goal,
                          onChange: function (event) {
                            setOutlineGuideField("goal", event.target.value);
                          }
                        })
                      ),
                      h(
                        "label",
                        { className: "field-label" },
                        h("span", null, t("web.outline.sync_context")),
                        h("textarea", {
                          rows: 3,
                          value: outlineGuideForm.sync_context,
                          onChange: function (event) {
                            setOutlineGuideField("sync_context", event.target.value);
                          }
                        })
                      ),
                      h(
                        "label",
                        { className: "field-label" },
                        h("span", null, t("web.outline.specify")),
                        h("textarea", {
                          rows: 3,
                          value: outlineGuideForm.specify,
                          onChange: function (event) {
                            setOutlineGuideField("specify", event.target.value);
                          }
                        })
                      ),
                      h(
                        "label",
                        { className: "field-label" },
                        h("span", null, t("web.outline.clarify_answers")),
                        h("textarea", {
                          rows: 2,
                          value: outlineGuideForm.clarify_answers,
                          onChange: function (event) {
                            setOutlineGuideField("clarify_answers", event.target.value);
                          }
                        })
                      ),
                      h(
                        "label",
                        { className: "field-label" },
                        h("span", null, t("web.outline.plan_notes")),
                        h("textarea", {
                          rows: 2,
                          value: outlineGuideForm.plan_notes,
                          onChange: function (event) {
                            setOutlineGuideField("plan_notes", event.target.value);
                          }
                        })
                      ),
                      h(
                        "div",
                        { className: "row compact" },
                        h(
                          "label",
                          { className: "field-label" },
                          h("span", null, t("web.outline.constraints")),
                          h("input", {
                            value: outlineGuideForm.constraints,
                            onChange: function (event) {
                              setOutlineGuideField("constraints", event.target.value);
                            }
                          })
                        ),
                        h(
                          "label",
                          { className: "field-label" },
                          h("span", null, t("web.outline.tone")),
                          h("input", {
                            value: outlineGuideForm.tone,
                            onChange: function (event) {
                              setOutlineGuideField("tone", event.target.value);
                            }
                          })
                        )
                      ),
                      h(
                        "button",
                        {
                          className: "btn",
                          disabled: outlineGuideBusy,
                          onClick: function () {
                            void runOutlineGuide();
                          }
                        },
                        outlineGuideBusy ? t("web.outline.generating") : t("web.outline.generate")
                      ),
                      Array.isArray(outlineGuideForm.questions) && outlineGuideForm.questions.length > 0
                        ? h(
                            "div",
                            { className: "outline-guide-list" },
                            h("strong", null, t("web.outline.questions")),
                            h(
                              "ol",
                              null,
                              outlineGuideForm.questions.map(function (item, index) {
                                return h("li", { key: "oq_" + index.toString() }, String(item));
                              })
                            )
                          )
                        : null,
                      Array.isArray(outlineGuideForm.chapter_beats) && outlineGuideForm.chapter_beats.length > 0
                        ? h(
                            "div",
                            { className: "outline-guide-list" },
                            h("strong", null, t("web.outline.chapter_beats")),
                            h(
                              "ol",
                              null,
                              outlineGuideForm.chapter_beats.map(function (item, index) {
                                return h("li", { key: "ob_" + index.toString() }, String(item));
                              })
                            )
                          )
                        : null,
                      Array.isArray(outlineGuideForm.next_steps) && outlineGuideForm.next_steps.length > 0
                        ? h(
                            "div",
                            { className: "outline-guide-list" },
                            h("strong", null, t("web.outline.next_steps")),
                            h(
                              "ol",
                              null,
                              outlineGuideForm.next_steps.map(function (item, index) {
                                return h("li", { key: "on_" + index.toString() }, String(item));
                              })
                            )
                          )
                        : null,
                      h(
                        "label",
                        { className: "field-label" },
                        h("span", null, t("web.outline.markdown")),
                        h("textarea", {
                          rows: 10,
                          value: outlineGuideForm.outline_markdown,
                          onChange: function (event) {
                            setOutlineGuideField("outline_markdown", event.target.value);
                          }
                        })
                      ),
                      h(
                        "button",
                        {
                          className: "btn",
                          onClick: function () {
                            void saveOutlineNodeFromGuide();
                          }
                        },
                        t("web.outline.save_node")
                      )
                    )
                  )
                : null,
              project
                ? h(
                    "div",
                    { className: "meta-grid" },
                    h(MetaItem, { label: t("web.project.meta.id"), value: project.id }),
                    h(MetaItem, { label: t("web.project.meta.revision"), value: String(project.active_revision) }),
                    h(MetaItem, { label: t("web.project.meta.updated"), value: shortIso(project.updated_at) }),
                    h(
                      "div",
                      { className: "meta-item" },
                      h("strong", null, t("web.project.meta.allow_cycles")),
                      h("span", null, String(project.settings.allow_cycles)),
                      h(
                        "button",
                        {
                          className: "mini-toggle",
                          onClick: function () {
                            void toggleAllowCycles();
                          }
                        },
                        t("web.project.toggle_cycles")
                      )
                    ),
                    h(
                      "div",
                      { className: "meta-item" },
                      h("strong", null, t("web.project.meta.auto_snapshot_minutes")),
                      h("input", {
                        value: projectSettingsForm.auto_snapshot_minutes,
                        onChange: function (event) {
                          setProjectSettingsField("auto_snapshot_minutes", event.target.value);
                        }
                      })
                    ),
                    h(
                      "div",
                      { className: "meta-item" },
                      h("strong", null, t("web.project.meta.auto_snapshot_operations")),
                      h("input", {
                        value: projectSettingsForm.auto_snapshot_operations,
                        onChange: function (event) {
                          setProjectSettingsField("auto_snapshot_operations", event.target.value);
                        }
                      })
                    ),
                    h(
                      "button",
                      {
                        className: "btn full",
                        onClick: function () {
                          void saveProjectSettings();
                        }
                      },
                      t("web.project.save_settings")
                    ),
                    h(
                      "button",
                      {
                        className: "btn danger full",
                        onClick: function () {
                          void deleteProject();
                        }
                      },
                      t("web.project.delete")
                    )
                  )
                : h("div", { className: "muted" }, t("web.project.no_projects"))
            ),
            h(
              "section",
              { className: "panel section", hidden: sidebarTab !== "node" },
              h("h2", null, t("web.section.add_node")),
              h(
                "div",
                { className: "form-grid" },
                h("input", {
                  value: newNodeForm.title,
                  placeholder: t("web.add_node.title_placeholder"),
                  onChange: function (event) {
                    setFormField("title", event.target.value);
                  }
                }),
                h(
                  "div",
                  { className: "row" },
                  h(
                    "select",
                    {
                      value: newNodeForm.type,
                      onChange: function (event) {
                        setFormField("type", event.target.value);
                      }
                    },
                    NODE_TYPES.map(function (item) {
                      return h("option", { key: item, value: item }, nodeTypeLabel(item));
                    })
                  ),
                  h(
                    "select",
                    {
                      value: newNodeForm.status,
                      onChange: function (event) {
                        setFormField("status", event.target.value);
                      }
                    },
                    NODE_STATUSES.map(function (item) {
                      return h("option", { key: item, value: item }, nodeStatusLabel(item));
                    })
                  )
                ),
                h("input", {
                  value: newNodeForm.storyline_id,
                  placeholder: t("web.add_node.storyline_placeholder"),
                  onChange: function (event) {
                    setFormField("storyline_id", event.target.value);
                  }
                }),
                h(
                  "label",
                  { className: "field-label" },
                  h("span", null, t("web.node.agent_preset")),
                  h(
                    "select",
                    {
                      value: newNodeForm.agent_preset,
                      onChange: function (event) {
                        setFormField("agent_preset", event.target.value);
                      }
                    },
                    h("option", { value: "" }, t("web.node.agent_preset_none")),
                    llmPresets.map(function (preset) {
                      return h(
                        "option",
                        { key: preset.tag, value: preset.tag },
                        preset.name + " (" + preset.tag + ")"
                      );
                    })
                  )
                ),
                newNodeForm.type === "group"
                  ? h(
                      "div",
                      { className: "row compact" },
                      h(
                        "select",
                        {
                          value: newNodeForm.group_kind,
                          title: t("web.node.group_kind"),
                          onChange: function (event) {
                            setFormField("group_kind", event.target.value);
                          }
                        },
                        GROUP_KINDS.map(function (item) {
                          return h("option", { key: item, value: item }, groupKindLabel(item));
                        })
                      ),
                      h("input", {
                        value: newNodeForm.group_width,
                        onChange: function (event) {
                          setFormField("group_width", event.target.value);
                        },
                        placeholder: t("web.node.group_width")
                      }),
                      h("input", {
                        value: newNodeForm.group_height,
                        onChange: function (event) {
                          setFormField("group_height", event.target.value);
                        },
                        placeholder: t("web.node.group_height")
                      })
                    )
                  : null,
                h(
                  "div",
                  { className: "row compact" },
                  h("input", {
                    value: newNodeForm.pos_x,
                    onChange: function (event) {
                      setFormField("pos_x", event.target.value);
                    },
                    placeholder: t("web.add_node.pos_x")
                  }),
                  h("input", {
                    value: newNodeForm.pos_y,
                    onChange: function (event) {
                      setFormField("pos_y", event.target.value);
                    },
                    placeholder: t("web.add_node.pos_y")
                  })
                ),
                h(
                  "button",
                  {
                    className: "btn",
                    onClick: function () {
                      void createNode();
                    }
                  },
                  t("web.add_node.create")
                )
              )
            ),
            h(
              "section",
              { className: "panel section", hidden: sidebarTab !== "node" },
              h("h2", null, t("web.section.inspector")),
              inspector
                ? h(
                    "div",
                    { className: "form-grid" },
                    h("input", {
                      value: inspector.title,
                      placeholder: t("web.inspector.title_placeholder"),
                      onChange: function (event) {
                        setInspectorField("title", event.target.value);
                      }
                    }),
                    h(
                      "div",
                      { className: "row" },
                      h(
                        "select",
                        {
                          value: inspector.type,
                          onChange: function (event) {
                            setInspectorField("type", event.target.value);
                          }
                        },
                        NODE_TYPES.map(function (item) {
                          return h("option", { key: item, value: item }, nodeTypeLabel(item));
                        })
                      ),
                      h(
                        "select",
                        {
                          value: inspector.status,
                          onChange: function (event) {
                            setInspectorField("status", event.target.value);
                          }
                        },
                        NODE_STATUSES.map(function (item) {
                          return h("option", { key: item, value: item }, nodeStatusLabel(item));
                        })
                      )
                    ),
                    h("input", {
                      value: inspector.storyline_id,
                      placeholder: t("web.inspector.storyline_placeholder"),
                      onChange: function (event) {
                        setInspectorField("storyline_id", event.target.value);
                      }
                    }),
                    h(
                      "label",
                      { className: "field-label" },
                      h("span", null, t("web.node.agent_preset")),
                      h(
                        "select",
                        {
                          value: inspector.agent_preset || "",
                          onChange: function (event) {
                            setInspectorField("agent_preset", event.target.value);
                          }
                        },
                        h("option", { value: "" }, t("web.node.agent_preset_none")),
                        llmPresets.map(function (preset) {
                          return h(
                            "option",
                            { key: preset.tag, value: preset.tag },
                            preset.name + " (" + preset.tag + ")"
                          );
                        })
                      )
                    ),
                    inspector.type !== "group"
                      ? h(
                          "div",
                          { className: "row compact" },
                          h(
                            "label",
                            { className: "field-label" },
                            h("span", null, t("web.node.group_binding")),
                            h(
                              "select",
                              {
                                value: inspector.group_binding || "independent",
                                onChange: function (event) {
                                  const next = event.target.value;
                                  setInspector(function (prev) {
                                    if (!prev) {
                                      return prev;
                                    }
                                    return Object.assign({}, prev, {
                                      group_binding: next,
                                      group_parent_id:
                                        next === "bound" ? prev.group_parent_id || "" : ""
                                    });
                                  });
                                }
                              },
                              GROUP_BINDINGS.map(function (item) {
                                return h("option", { key: item, value: item }, groupBindingLabel(item));
                              })
                            )
                          ),
                          h(
                            "label",
                            { className: "field-label" },
                            h("span", null, t("web.node.group_parent_id")),
                            h(
                              "select",
                              {
                                value: inspector.group_parent_id || "",
                                disabled: (inspector.group_binding || "independent") !== "bound",
                                onChange: function (event) {
                                  setInspectorField("group_parent_id", event.target.value);
                                }
                              },
                              h("option", { value: "" }, t("web.node.group_parent_none")),
                              groupNodes
                                .filter(function (item) {
                                  return item.id !== selectedNodeId;
                                })
                                .map(function (item) {
                                  return h("option", { key: item.id, value: item.id }, item.title + " (" + item.id + ")");
                                })
                            )
                          )
                        )
                      : null,
                    inspector.type === "group"
                      ? h(
                          "div",
                          { className: "row compact" },
                          h(
                            "select",
                            {
                              value: inspector.group_kind || "phase",
                              title: t("web.node.group_kind"),
                              onChange: function (event) {
                                setInspectorField("group_kind", event.target.value);
                              }
                            },
                            GROUP_KINDS.map(function (item) {
                              return h("option", { key: item, value: item }, groupKindLabel(item));
                            })
                          ),
                          h("input", {
                            value: inspector.group_width || "",
                            onChange: function (event) {
                              setInspectorField("group_width", event.target.value);
                            },
                            placeholder: t("web.node.group_width")
                          }),
                          h("input", {
                            value: inspector.group_height || "",
                            onChange: function (event) {
                              setInspectorField("group_height", event.target.value);
                            },
                            placeholder: t("web.node.group_height")
                          })
                        )
                      : null,
                    h("textarea", {
                      rows: 4,
                      value: inspector.metadata_json,
                      placeholder: t("web.inspector.metadata_placeholder"),
                      onChange: function (event) {
                        setInspectorField("metadata_json", event.target.value);
                      }
                    }),
                    h(
                      "div",
                      { className: "row" },
                      h(
                        "button",
                        {
                          className: "btn",
                          onClick: function () {
                            void saveInspector();
                          }
                        },
                        t("web.inspector.save")
                      ),
                      h(
                        "button",
                        {
                          className: "btn danger",
                          onClick: function () {
                            void deleteNode();
                          }
                        },
                        t("web.inspector.delete")
                      )
                    )
                  )
                : h("div", { className: "muted" }, t("web.inspector.empty"))
            ),
            h(
              "section",
              { className: "panel section", hidden: sidebarTab !== "ai" },
              h("h2", null, t("web.section.ai")),
              h(
                "div",
                { className: "form-grid" },
                h(
                  "label",
                  { className: "field-label" },
                  h("span", null, t("web.ai.token_budget")),
                  h("input", {
                    value: aiConfig.token_budget,
                    onChange: function (event) {
                      setAiConfig(function (prev) {
                        return Object.assign({}, prev, { token_budget: event.target.value });
                      });
                    }
                  })
                ),
                h(
                  "label",
                  { className: "field-label" },
                  h("span", null, t("web.ai.workflow_mode")),
                  h(
                    "select",
                    {
                      value: aiConfig.workflow_mode,
                      onChange: function (event) {
                        setAiConfig(function (prev) {
                          return Object.assign({}, prev, { workflow_mode: event.target.value });
                        });
                      }
                    },
                    h("option", { value: "multi_agent" }, "multi_agent"),
                    h("option", { value: "single" }, "single")
                  )
                ),
                h(
                  "div",
                  { className: "row" },
                  h(
                    "button",
                    {
                      className: "btn",
                      onClick: function () {
                        void runAi("generate_chapter");
                      }
                    },
                    t("web.ai.generate_chapter")
                  ),
                  h(
                    "button",
                    {
                      className: "btn ghost",
                      onClick: function () {
                        void runAi("generate_branches");
                      }
                    },
                    t("web.ai.generate_branches")
                  )
                ),
                h(
                  "div",
                  { className: "row" },
                  h(
                    "button",
                    {
                      className: "btn ghost",
                      onClick: function () {
                        void runAi("review_lore");
                      }
                    },
                    t("web.ai.review_lore")
                  ),
                  h(
                    "button",
                    {
                      className: "btn ghost",
                      onClick: function () {
                        void runAi("review_logic");
                      }
                    },
                    t("web.ai.review_logic")
                  )
                ),
                h(
                  "textarea",
                  {
                    className: "ai-result",
                    value: aiResult,
                    readOnly: true,
                    placeholder: t("web.ai.result_placeholder")
                  }
                )
              )
            ),
            h(
              "section",
              { className: "panel section", hidden: sidebarTab !== "ops" },
              h("h2", null, t("web.section.edges")),
              h("div", { className: "edge-list" }, edgeItems)
            ),
            h(
              "section",
              { className: "panel section", hidden: sidebarTab !== "ops" },
              h("h2", null, t("web.section.validation")),
              h("div", { className: "validation-box" }, validationNodes)
            ),
            h(
              "section",
              { className: "panel section", hidden: sidebarTab !== "ops" },
              h("h2", null, t("web.section.activity")),
              h("div", { className: "activity-log" }, activityItems)
            )
          ),
          h(
            "section",
            { className: "canvas-area panel" },
            mainView === "story"
              ? [
                  h(
                    "div",
                    { className: "canvas-toolbar", key: "story-toolbar" },
                    h(
                      "button",
                      {
                        className: "btn ghost" + (edgeMode ? " active" : ""),
                        onClick: function () {
                          setEdgeMode(function (prev) {
                            const next = !prev;
                            if (!next) {
                              setEdgeSourceId("");
                            }
                            return next;
                          });
                        }
                      },
                      t("web.canvas.edge_mode") + ": " + (edgeMode ? t("web.canvas.edge_mode_on") : t("web.canvas.edge_mode_off"))
                    ),
                    h(
                      "button",
                      {
                        className: "btn ghost" + (autoBindOnDrop ? " active" : ""),
                        onClick: function () {
                          setAutoBindOnDrop(function (prev) {
                            return !prev;
                          });
                        }
                      },
                      t("web.canvas.auto_bind") + ": " + (autoBindOnDrop ? t("web.canvas.auto_bind_on") : t("web.canvas.auto_bind_off"))
                    ),
                    h("span", { className: "muted" }, t("web.canvas.edge_hint")),
                    h("span", { className: "edge-direction-legend" }, t("web.canvas.edge_direction")),
                    edgeMode && edgeSourceId
                      ? h("span", { className: "edge-source-tag" }, t("web.canvas.edge_pick_source", { node_id: edgeSourceId }))
                      : null,
                    h("span", { className: "muted" }, t("web.canvas.storyline_filter")),
                    h(
                      "select",
                      {
                        className: "storyline-select",
                        value: storylineFilter,
                        onChange: function (event) {
                          setStorylineFilter(event.target.value);
                        }
                      },
                      h("option", { value: STORYLINE_ALL }, t("web.canvas.storyline_all")),
                      storylineOptions.map(function (item) {
                        return h("option", { key: item, value: item }, item);
                      })
                    ),
                    h(
                      "button",
                      {
                        className: "btn ghost",
                        onClick: function () {
                          setCollapsedGroupIds(function (prev) {
                            const next = Object.assign({}, prev);
                            nodes.forEach(function (node) {
                              if (node.type === "group") {
                                next[node.id] = true;
                              }
                            });
                            return next;
                          });
                        }
                      },
                      t("web.group.collapse_all")
                    ),
                    h(
                      "button",
                      {
                        className: "btn ghost",
                        onClick: function () {
                          setCollapsedGroupIds(function (prev) {
                            const next = Object.assign({}, prev);
                            nodes.forEach(function (node) {
                              if (node.type === "group") {
                                next[node.id] = false;
                              }
                            });
                            return next;
                          });
                        }
                      },
                      t("web.group.expand_all")
                    ),
                    insightHighlightSet.size > 0
                      ? h(
                          "button",
                          {
                            className: "btn ghost",
                            onClick: function () {
                              setInsightHighlightNodeIds([]);
                            }
                          },
                          t("web.insight.clear_highlight")
                        )
                      : null,
                    h(
                      "button",
                      {
                        className: "btn ghost zoom-btn",
                        onClick: function () {
                          applyZoomDelta(-ZOOM_STEP);
                        }
                      },
                      "-"
                    ),
                    h("span", { className: "zoom-indicator" }, Math.round(zoom * 100).toString() + "%"),
                    h(
                      "button",
                      {
                        className: "btn ghost zoom-btn",
                        onClick: function () {
                          applyZoomDelta(ZOOM_STEP);
                        }
                      },
                      "+"
                    ),
                    h(
                      "button",
                      {
                        className: "btn ghost zoom-btn",
                        onClick: function () {
                          setZoom(1);
                        }
                      },
                      "1:1"
                    ),
                    h("span", { className: "muted zoom-hint" }, t("web.canvas.zoom_hint")),
                    h(
                      "button",
                      {
                        className: "btn ghost",
                        onClick: function () {
                          void createSnapshot();
                        }
                      },
                      t("web.top.snapshot")
                    ),
                    h(
                      "button",
                      {
                        className: "btn ghost",
                        onClick: function () {
                          void rollbackProject();
                        }
                      },
                      t("web.top.rollback")
                    ),
                    h(
                      "button",
                      {
                        className: "btn ghost" + (artifactOpen ? " active" : ""),
                        onClick: function () {
                          setArtifactOpen(function (prev) {
                            const next = !prev;
                            if (next) {
                              setChatOpen(false);
                            }
                            return next;
                          });
                        }
                      },
                      t("web.artifact.toggle")
                    ),
                    h(
                      "button",
                      {
                        className: "btn ghost" + (chatOpen ? " active" : ""),
                        onClick: function () {
                          setChatOpen(function (prev) {
                            const next = !prev;
                            if (next) {
                              setArtifactOpen(false);
                            }
                            return next;
                          });
                        }
                      },
                      t("web.chat.toggle")
                    )
                  ),
                  h(
                    "div",
                    {
                      className: "graph-viewport",
                      key: "story-viewport",
                      ref: viewportRef,
                      onMouseDown: function (event) {
                        beginViewportPan(event);
                      },
                      onContextMenu: function (event) {
                        if (Date.now() <= contextMenuSuppressUntilRef.current) {
                          event.preventDefault();
                        }
                      },
                      onWheel: function (event) {
                        if (!event.altKey) {
                          return;
                        }
                        event.preventDefault();
                        applyZoomDelta(event.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP);
                      }
                    },
                    h(
                      "div",
                      {
                        className: "graph-zoom-stage",
                        style: {
                          width: Math.round(boardSize.width * zoom) + "px",
                          height: Math.round(boardSize.height * zoom) + "px"
                        }
                      },
                      h(
                        "div",
                        {
                          className: "graph-board",
                          style: {
                            width: boardSize.width + "px",
                            height: boardSize.height + "px",
                            transform: "scale(" + zoom + ")",
                            transformOrigin: "0 0"
                          }
                        },
                        h(
                          "svg",
                          {
                            className: "edge-layer",
                            xmlns: "http://www.w3.org/2000/svg"
                          },
                          h(
                            "defs",
                            null,
                            h(
                              "marker",
                              {
                                id: "arrowHead",
                                markerWidth: "12",
                                markerHeight: "12",
                                refX: "12",
                                refY: "6",
                                orient: "auto-start-reverse",
                                markerUnits: "strokeWidth"
                              },
                              h("path", { className: "edge-arrow", d: "M0,0 L12,6 L0,12 L3.4,6 Z" })
                            ),
                            h(
                              "marker",
                              {
                                id: "ghostArrowHead",
                                markerWidth: "12",
                                markerHeight: "12",
                                refX: "12",
                                refY: "6",
                                orient: "auto-start-reverse",
                                markerUnits: "strokeWidth"
                              },
                              h("path", { className: "edge-arrow ghost-edge-arrow", d: "M0,0 L12,6 L0,12 L3.4,6 Z" })
                            )
                          ),
                          edgeRenderShapes.map(function (shape) {
                            const edgeText = edgeDisplayLabel(shape.edge);
                            return h(
                              "g",
                              { key: shape.edge.id },
                              h("path", {
                                className:
                                  "edge-line" +
                                  (shape.suggested ? " suggested-edge" : "") +
                                  (shape.highlight ? " highlight-edge" : ""),
                                d: shape.path,
                                markerEnd: "url(#arrowHead)",
                                style: shape.tone ? { stroke: shape.tone } : undefined
                              }),
                              edgeText
                                ? h(
                                    "text",
                                    {
                                      className: "edge-label",
                                      x: shape.labelX,
                                      y: shape.labelY,
                                      textAnchor: "middle"
                                    },
                                    edgeText
                                  )
                                : null
                            );
                          }),
                          ghostEdgeShapes.map(function (shape) {
                            return h(
                              "g",
                              { key: shape.id },
                              h("path", {
                                className: "edge-line ghost-edge-line",
                                d: shape.path,
                                markerEnd: "url(#ghostArrowHead)",
                                style: shape.tone ? { stroke: shape.tone } : undefined
                              }),
                              h(
                                "text",
                                {
                                  className: "edge-label ghost-edge-label",
                                  x: shape.labelX,
                                  y: shape.labelY,
                                  textAnchor: "middle"
                                },
                                t("web.ghost.edge_label")
                              )
                            );
                          })
                        ),
                        h("div", { className: "node-layer" }, nodesView.concat(ghostNodesView))
                      ),
                    )
                  ),
                  h(
                    "aside",
                    { className: "chat-drawer artifact-drawer" + (artifactOpen ? " open" : ""), key: "story-artifact" },
                    h(
                      "div",
                      { className: "chat-head" },
                      h(
                        "div",
                        { className: "chat-head-main" },
                        h("strong", null, t("web.artifact.title")),
                        h("span", { className: "muted" }, artifactContextText)
                      ),
                      h(
                        "button",
                        {
                          className: "mini-btn",
                          onClick: function () {
                            setArtifactOpen(false);
                          }
                        },
                        "×"
                      )
                    ),
                    h(
                      "div",
                      { className: "artifact-layout" },
                      h(
                        "section",
                        { className: "artifact-panel artifact-chat-panel" },
                        h(
                          "div",
                          { className: "chat-controls" },
                          h("span", { className: "muted" }, t("web.chat.context")),
                          h(
                            "select",
                            {
                              value: artifactTargetId,
                              onChange: function (event) {
                                setArtifactContextNodeId(event.target.value);
                              }
                            },
                            h("option", { value: "" }, t("web.chat.context_global")),
                            chatContextOptions.map(function (item) {
                              return h(
                                "option",
                                { key: "artifact_ctx_" + item.id, value: item.id },
                                item.title + " (" + item.id + ")"
                              );
                            })
                          )
                        )
                      ),
                      h(
                        "section",
                        { className: "artifact-panel artifact-preview-panel" },
                        h("div", { className: "artifact-panel-head" }, t("web.artifact.preview")),
                        h(
                          "div",
                          { className: "artifact-panel-body artifact-preview-body" },
                          artifactContextNode
                            ? renderMarkdownPreview(artifactPreview)
                            : h("div", { className: "muted" }, t("web.artifact.preview_global_hint"))
                        )
                      ),
                      h(
                        "section",
                        { className: "artifact-panel artifact-diff-panel" },
                        h("div", { className: "artifact-panel-head" }, t("web.artifact.diff")),
                        h(
                          "div",
                          { className: "artifact-panel-body" },
                          artifactDiffVisible
                            ? h(
                                "div",
                                { className: "chat-diff-body" },
                                artifactDiffSegments.slice(0, 420).map(function (segment, index) {
                                  const kind = normalizeDiffKind(segment && segment.type);
                                  const className = "chat-diff-row chat-diff-row-" + kind;
                                  return h(
                                    "div",
                                    { key: "artifact_diff_" + index.toString(), className: className },
                                    h("span", { className: "chat-diff-prefix" }, diffPrefix(kind)),
                                    h("span", { className: "chat-diff-text" }, String(segment && segment.text ? segment.text : ""))
                                  );
                                })
                              )
                            : h("div", { className: "muted" }, t("web.artifact.diff_empty"))
                        )
                      )
                    )
                  ),
                  h(
                    "aside",
                    { className: "chat-drawer" + (chatOpen ? " open" : ""), key: "story-chat" },
                    h(
                      "div",
                      { className: "chat-head" },
                      h(
                        "div",
                        { className: "chat-head-main" },
                        h("strong", null, t("web.chat.title")),
                        h("span", { className: "muted" }, chatContextNodeId ? t("web.chat.context_node", { node_id: chatContextNodeId }) : t("web.chat.context_global"))
                      ),
                      h(
                        "button",
                        {
                          className: "mini-btn",
                          onClick: function () {
                            setChatOpen(false);
                          }
                        },
                        "×"
                      )
                    ),
                    h(
                      "section",
                      { className: "artifact-panel artifact-chat-panel" },
                      h(
                        "div",
                        { className: "artifact-panel-head" },
                        t("web.chat.toggle")
                      ),
                      h(
                        "div",
                        { className: "artifact-panel-body" },
                        h(
                          "div",
                          { className: "chat-controls" },
                          h("span", { className: "muted" }, t("web.chat.context")),
                          h(
                            "select",
                            {
                              value: chatContextNodeId,
                              onChange: function (event) {
                                setChatContextNodeId(event.target.value);
                              }
                            },
                            h("option", { value: "" }, t("web.chat.context_global")),
                            chatContextOptions.map(function (item) {
                              return h(
                                "option",
                                { key: item.id, value: item.id },
                                item.title + " (" + item.id + ")"
                              );
                            })
                          ),
                          h(
                            "button",
                            {
                              className: "btn ghost full",
                              onClick: function () {
                                void clearSuggestedNodes(true);
                              }
                            },
                            t("web.chat.clear_suggestions")
                          ),
                          h(
                            "div",
                            { className: "ghost-archive-panel" },
                            h(
                              "div",
                              { className: "ghost-archive-toolbar" },
                              h("strong", null, t("web.ghost.archive_title")),
                              h("span", { className: "muted" }, t("web.ghost.archive_count", { count: visibleGhostArchive.length })),
                              visibleGhostArchive.length > 0
                                ? h(
                                    "button",
                                    {
                                      className: "mini-btn",
                                      onClick: function () {
                                        clearGhostArchiveForProject(projectId);
                                      }
                                    },
                                    t("web.ghost.archive_clear")
                                  )
                                : null
                            ),
                            h("div", { className: "ghost-archive-list" }, ghostArchiveViews)
                          ),
                          h("div", { className: "muted chat-hint" }, t("web.chat.hint")),
                          chatWorkflow.enabled && !chatContextNodeId
                            ? h(
                                "div",
                                { className: "muted chat-hint" },
                                t("web.workflow.step_status", { step: String(chatWorkflow.step || "start") })
                              )
                            : null
                        ),
                        h("div", { className: "chat-log", ref: chatLogRef }, chatMessageViews),
                        h(
                          "div",
                          { className: "chat-input-row" },
                          h("textarea", {
                            rows: 3,
                            value: chatInput,
                            placeholder:
                              chatWorkflow.enabled && !chatContextNodeId
                                ? t("web.workflow.input_hint")
                                : t("web.chat.placeholder"),
                            onChange: function (event) {
                              setChatInput(event.target.value);
                            }
                          }),
                          h(
                            "button",
                            {
                              className: "btn",
                              disabled: chatBusy,
                              onClick: function () {
                                void sendChatMessage();
                              }
                            },
                            chatBusy ? t("web.chat.sending") : t("web.chat.send")
                          )
                        )
                      )
                    )
                  )
                ]
              : [
                  h(
                    "div",
                    { className: "canvas-toolbar", key: "insight-toolbar" },
                    h("strong", null, t("web.insight.title")),
                    h("span", { className: "muted" }, t("web.insight.readonly_note")),
                    h(
                      "button",
                      {
                        className: "btn ghost",
                        onClick: function () {
                          void loadInsights(true);
                        }
                      },
                      t("web.insight.refresh")
                    ),
                    insightHighlightSet.size > 0
                      ? h(
                          "button",
                          {
                            className: "btn ghost",
                            onClick: function () {
                              setInsightHighlightNodeIds([]);
                            }
                          },
                          t("web.insight.clear_highlight")
                        )
                      : null
                  ),
                  h(
                    "div",
                    { className: "insight-view", key: "insight-view" },
                    insightBusy ? h("div", { className: "muted" }, t("web.insight.loading")) : null,
                    insightError ? h("div", { className: "muted" }, insightError) : null,
                    !insightBusy && !insightError
                      ? h(
                          "div",
                          { className: "insight-grid" },
                          h(
                            "section",
                            { className: "insight-card" },
                            h("h3", null, t("web.insight.storylines")),
                            insightStorylines.length > 0
                              ? insightStorylines.map(function (item, index) {
                                  const label = String(item.storyline_id || "").trim() || t("web.canvas.storyline_all");
                                  return h(
                                    "div",
                                    { className: "insight-row", key: "storyline_" + index.toString() },
                                    h("strong", null, label),
                                    h(
                                      "span",
                                      { className: "muted" },
                                      t("web.insight.storyline_stats", {
                                        nodes: String(item.node_count || 0),
                                        edges: String(item.edge_count || 0)
                                      })
                                    )
                                  );
                                })
                              : h("div", { className: "muted" }, "-")
                          ),
                          h(
                            "section",
                            { className: "insight-card insight-graph-card" },
                            h("h3", null, t("web.insight.relation_graph")),
                            h("div", { className: "muted" }, t("web.insight.graph_auto_generated")),
                            h(
                              "div",
                              { className: "insight-graph-wrap" },
                              h(
                                "svg",
                                {
                                  className: "insight-graph",
                                  viewBox: "0 0 " + relationWidth + " " + relationHeight
                                },
                                relationEdges.map(function (edge, index) {
                                  const source = relationPosById[edge.source];
                                  const target = relationPosById[edge.target];
                                  if (!source || !target) {
                                    return null;
                                  }
                                  return h(
                                    "g",
                                    { key: "re_" + index.toString() },
                                    h("line", {
                                      className: "insight-edge",
                                      x1: source.x,
                                      y1: source.y,
                                      x2: target.x,
                                      y2: target.y
                                    }),
                                    h(
                                      "text",
                                      {
                                        className: "insight-edge-label",
                                        x: (source.x + target.x) / 2,
                                        y: (source.y + target.y) / 2 - 4,
                                        textAnchor: "middle"
                                      },
                                      String(edge.relation || "")
                                    )
                                  );
                                }),
                                relationLayout.map(function (item) {
                                  const typeClass = "relation-node relation-node-" + String(item.node.type || "character");
                                  const radius = Math.max(14, Math.min(30, 12 + Math.sqrt(asNumber(item.node.weight, 1)) * 2.2));
                                  return h(
                                    "g",
                                    {
                                      key: "rn_" + item.node.id,
                                      className: "relation-node-wrap",
                                      onClick: function () {
                                        openNodeFromInsight(item.node.node_ids || []);
                                      }
                                    },
                                    h("circle", {
                                      className: typeClass,
                                      cx: item.x,
                                      cy: item.y,
                                      r: radius
                                    }),
                                    h(
                                      "text",
                                      {
                                        className: "relation-node-label",
                                        x: item.x,
                                        y: item.y + radius + 14,
                                        textAnchor: "middle"
                                      },
                                      String(item.node.label || "")
                                    )
                                  );
                                })
                              )
                            )
                          ),
                          h(
                            "section",
                            { className: "insight-card" },
                            h("h3", null, t("web.insight.word_frequency")),
                            h(
                              "div",
                              { className: "insight-chip-list" },
                              insightWords.slice(0, 48).map(function (item, index) {
                                return h(
                                  "button",
                                  {
                                    key: "w_" + index.toString(),
                                    className: "insight-chip",
                                    onClick: function () {
                                      openNodeFromInsight(item.node_ids || []);
                                    }
                                  },
                                  String(item.term || "-") + " · " + String(item.count || 0)
                                );
                              })
                            )
                          ),
                          h(
                            "section",
                            { className: "insight-card" },
                            h("h3", null, t("web.insight.characters")),
                            h(
                              "div",
                              { className: "insight-chip-list" },
                              insightCharacters.slice(0, 40).map(function (item, index) {
                                return h(
                                  "button",
                                  {
                                    key: "c_" + index.toString(),
                                    className: "insight-chip",
                                    onClick: function () {
                                      openNodeFromInsight(item.node_ids || []);
                                    }
                                  },
                                  String(item.name || "-") + " · " + String(item.count || 0)
                                );
                              })
                            )
                          ),
                          h(
                            "section",
                            { className: "insight-card" },
                            h("h3", null, t("web.insight.worldviews")),
                            h(
                              "div",
                              { className: "insight-chip-list" },
                              insightWorldviews.slice(0, 40).map(function (item, index) {
                                return h(
                                  "button",
                                  {
                                    key: "wv_" + index.toString(),
                                    className: "insight-chip",
                                    onClick: function () {
                                      openNodeFromInsight(item.node_ids || []);
                                    }
                                  },
                                  String(item.name || "-") + " · " + String(item.count || 0)
                                );
                              })
                            )
                          ),
                          h(
                            "section",
                            { className: "insight-card" },
                            h("h3", null, t("web.insight.items")),
                            h(
                              "div",
                              { className: "insight-chip-list" },
                              insightItems.slice(0, 40).map(function (item, index) {
                                const owner = String(item.owner || "").trim();
                                const text =
                                  String(item.name || "-") +
                                  " · " +
                                  String(item.count || 0) +
                                  (owner ? " · " + t("web.insight.item_owner", { owner: owner }) : "");
                                return h(
                                  "button",
                                  {
                                    key: "it_" + index.toString(),
                                    className: "insight-chip",
                                    onClick: function () {
                                      openNodeFromInsight(item.node_ids || []);
                                    }
                                  },
                                  text
                                );
                              })
                            )
                          )
                        )
                      : null
                  )
                ]
          )
        )
      ),
      h(Modal, { modal: modal, onResolve: resolveModal }),
      h("div", { className: "toast-stack" }, toastsView)
    );
  }

  ReactDOM.createRoot(document.getElementById("root")).render(h(App));
})();
