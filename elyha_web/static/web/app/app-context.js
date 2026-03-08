(function () {
  "use strict";

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

  window.ElyhaWebAppContext = {
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
    createNodeActionHandlersValue
  };
})();
