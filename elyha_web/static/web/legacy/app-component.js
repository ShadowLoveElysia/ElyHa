(function () {
  "use strict";

  const { useEffect, useMemo, useRef, useState } = React;
  const h = React.createElement;

  window.ElyhaWebAppComponent = function () {
    const setup = window.ElyhaWebAppSetup || {};
    const {
      DEFAULT_LOCALE,
      SUPPORTED_LOCALES,
      STORYLINE_ALL,
      MIN_ZOOM,
      MAX_ZOOM,
      asBoolean,
      asNumber,
      loadWebState,
      saveWebState,
      safeArray,
      normalizePersistedChatMessages,
      normalizePersistedMainView,
      normalizePersistedSidebarTab,
      normalizePersistedGhostArchive,
      buildDefaultWorkflowStateValue
    } = setup;

    function App() {
      const buildDefaultWorkflowState = buildDefaultWorkflowStateValue;
      const resolveActiveChatContext = setup.resolveActiveChatContextValue;
      const nextArtifactDiffNodeId = setup.nextArtifactDiffNodeIdValue;
      const shouldShowArtifactDiff = setup.shouldShowArtifactDiffValue;
      const normalizeDiffKind = setup.normalizeDiffKindValue;
      const diffPrefix = setup.diffPrefixValue;

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
