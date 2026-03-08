(function () {
  "use strict";

  function createProjectActionHandlers(deps) {
    const context = deps || {};
    const SUPPORTED_LOCALES = context.SUPPORTED_LOCALES;
    const DEFAULT_LOCALE = context.DEFAULT_LOCALE;
    const runApi = context.runApi;
    const runApiDetailed = context.runApiDetailed;
    const apiRequest = context.apiRequest;
    const configActions = context.configActions;
    const apiActions = context.apiActions;
    const applyRuntimePayload = context.applyRuntimePayload;
    const addActivity = context.addActivity;
    const setCatalog = context.setCatalog;
    const setLlmPresets = context.setLlmPresets;
    const setRuntimePresetTag = context.setRuntimePresetTag;
    const llmPresets = context.llmPresets;
    const setRuntimeSettings = context.setRuntimeSettings;
    const asBoolean = context.asBoolean;
    const pushToast = context.pushToast;
    const t = context.t;
    const projectId = context.projectId;
    const setProjects = context.setProjects;
    const setProjectId = context.setProjectId;
    const setProject = context.setProject;
    const setNodes = context.setNodes;
    const setEdges = context.setEdges;
    const setSelectedNodeId = context.setSelectedNodeId;
    const setValidationReport = context.setValidationReport;
    const setGhostPlans = context.setGhostPlans;
    const setExpandedGhostIds = context.setExpandedGhostIds;
    const setSelectedGhostIds = context.setSelectedGhostIds;
    const setRetiringGhostIds = context.setRetiringGhostIds;
    const setNodeFlowStates = context.setNodeFlowStates;
    const selectedNodeId = context.selectedNodeId;
    const setInsightData = context.setInsightData;
    const setInsightError = context.setInsightError;
    const setInsightBusy = context.setInsightBusy;
    const viewportRef = context.viewportRef;
    const nodesRef = context.nodesRef;
    const nodeRenderSize = context.nodeRenderSize;
    const zoom = context.zoom;
    const asNumber = context.asNumber;
    const setInsightHighlightNodeIds = context.setInsightHighlightNodeIds;
    const setMainView = context.setMainView;
    const setSidebarTab = context.setSidebarTab;
    const showInput = context.showInput;
    const project = context.project;
    const newProjectTitle = context.newProjectTitle;
    const setNewProjectTitle = context.setNewProjectTitle;
    const isMockProvider = context.isMockProvider;
    const outlineGuideForm = context.outlineGuideForm;
    const setOutlineGuideBusy = context.setOutlineGuideBusy;
    const aiRequestTimeoutMs = context.aiRequestTimeoutMs;
    const aiConfig = context.aiConfig;
    const setOutlineGuideForm = context.setOutlineGuideForm;
    const setChatContextNodeId = context.setChatContextNodeId;
    const setChatOpen = context.setChatOpen;
    const setArtifactOpen = context.setArtifactOpen;
    const showConfirm = context.showConfirm;
    const projectSettingsForm = context.projectSettingsForm;
    const setProjectSettingsForm = context.setProjectSettingsForm;

async function loadLocaleCatalog(nextLocale) {
      const picked = SUPPORTED_LOCALES.includes(nextLocale) ? nextLocale : DEFAULT_LOCALE;
      const result = await runApi(
        function () {
          return apiRequest("/i18n/" + picked + ".json");
        },
        null
      );
      if (result && typeof result === "object") {
        setCatalog(result);
        window.localStorage.setItem("elyha_web_locale", picked);
      }
    }
    
    async function loadRuntimeSettings() {
      const payload = await runApi(
        function () {
          return configActions.fetchRuntimeSettingsAction();
        },
        null
      );
      if (!payload) {
        return;
      }
      applyRuntimePayload(payload, { syncLocale: true, syncAiDefaults: true });
      addActivity("info", "runtime settings loaded");
    }
    
    async function loadLlmPresets() {
      const payload = await runApi(
        function () {
          return configActions.fetchLlmPresetsAction();
        },
        null
      );
      if (!Array.isArray(payload)) {
        setLlmPresets([]);
        return;
      }
      setLlmPresets(payload);
      addActivity("info", "llm presets loaded: " + payload.length.toString());
    }
    
    function applyRuntimePreset(presetTag) {
      const tag = String(presetTag || "").trim();
      setRuntimePresetTag(tag);
      if (!tag) {
        return;
      }
      const preset = llmPresets.find(function (item) {
        return String(item.tag || "") === tag;
      });
      if (!preset) {
        return;
      }
      setRuntimeSettings(function (prev) {
        return Object.assign({}, prev, {
          llm_provider: "llmrequester",
          api_url: String(preset.api_url || prev.api_url || ""),
          model_name: String(preset.default_model || prev.model_name || ""),
          auto_complete: asBoolean(preset.auto_complete, prev.auto_complete)
        });
      });
      pushToast("ok", t("web.toast.preset_applied", { preset: preset.name || preset.tag }));
    }
    
    async function refreshProjects(preferredId) {
      const projectList = await runApi(
        function () {
          return apiActions.refreshProjectsAction();
        },
        null
      );
      if (!projectList) {
        return;
      }
      setProjects(projectList);
    
      const preferred = preferredId || projectId;
      const hasPreferred = preferred && projectList.some(function (item) {
        return item.id === preferred;
      });
      const nextId = hasPreferred ? preferred : projectList.length > 0 ? projectList[0].id : "";
      setProjectId(nextId);
      if (!nextId) {
        setProject(null);
        setNodes([]);
        setEdges([]);
        setSelectedNodeId("");
        setValidationReport(null);
        setGhostPlans([]);
        setExpandedGhostIds({});
        setSelectedGhostIds({});
        setRetiringGhostIds({});
        setNodeFlowStates({});
      }
    }
    
    async function refreshProjectData(activeProjectId, keepSelection) {
      if (!activeProjectId) {
        return;
      }
      const data = await runApi(
        async function () {
          const result = await apiActions.refreshProjectDataAction(activeProjectId);
          return [result.project, result.nodes, result.edges];
        },
        null
      );
      if (!data) {
        return;
      }
      const loadedProject = data[0];
      const loadedNodes = data[1];
      const loadedEdges = data[2];
    
      setProject(loadedProject);
      setNodes(loadedNodes);
      setEdges(loadedEdges);
    
      if (keepSelection) {
        const stillExists = loadedNodes.some(function (node) {
          return node.id === selectedNodeId;
        });
        if (!stillExists) {
          setSelectedNodeId("");
        }
      } else {
        setSelectedNodeId("");
      }
    }
    
    async function loadInsights(showToastMessage) {
      if (!projectId) {
        setInsightData(null);
        setInsightError("");
        return;
      }
      setInsightBusy(true);
      setInsightError("");
      const payload = await runApi(
        function () {
          return apiActions.fetchInsightsAction(projectId);
        },
        null
      );
      setInsightBusy(false);
      if (!payload) {
        setInsightError(t("web.insight.load_failed"));
        return;
      }
      setInsightData(payload);
      if (showToastMessage) {
        pushToast("ok", t("web.insight.loaded"));
      }
    }
    
    function focusNodeOnViewport(nodeId) {
      const viewport = viewportRef.current;
      if (!viewport || !nodeId) {
        return;
      }
      const targetNode = nodesRef.current.find(function (item) {
        return item.id === nodeId;
      });
      if (!targetNode) {
        return;
      }
      const size = nodeRenderSize(targetNode);
      const centerX = asNumber(targetNode.pos_x, 0) + size.width / 2;
      const centerY = asNumber(targetNode.pos_y, 0) + size.height / 2;
      const targetLeft = Math.max(0, Math.round(centerX * zoom - viewport.clientWidth / 2));
      const targetTop = Math.max(0, Math.round(centerY * zoom - viewport.clientHeight / 2));
      viewport.scrollTo({ left: targetLeft, top: targetTop, behavior: "smooth" });
    }
    
    function openNodeFromInsight(nodeIds) {
      const list = Array.isArray(nodeIds) ? nodeIds.filter(Boolean) : [];
      if (list.length === 0) {
        return;
      }
      const targetId = String(list[0]);
      setInsightHighlightNodeIds(list.slice(0, 256));
      setMainView("story");
      setSidebarTab("node");
      setSelectedNodeId(targetId);
      window.setTimeout(function () {
        focusNodeOnViewport(targetId);
      }, 20);
    }
    
    async function validateGraph() {
      if (!projectId) {
        pushToast("warn", t("web.toast.project_required"));
        return;
      }
      const report = await runApi(
        function () {
          return apiActions.validateProjectAction(projectId);
        },
        t("web.toast.loaded")
      );
      if (!report) {
        return;
      }
      setValidationReport(report);
      addActivity("info", "validate: errors=" + report.errors + ", warnings=" + report.warnings);
    }
    
    async function exportGraph() {
      if (!projectId) {
        pushToast("warn", t("web.toast.project_required"));
        return;
      }
      const traversal = await showInput(
        t("web.modal.export_title"),
        t("web.modal.export_body"),
        t("web.modal.export_placeholder"),
        "mainline"
      );
      if (traversal === null) {
        return;
      }
      const payload = { traversal: traversal.trim() || "mainline" };
      const result = await runApi(
        function () {
          return apiActions.exportProjectAction(projectId, payload.traversal);
        },
        null
      );
      if (!result) {
        return;
      }
      pushToast("ok", t("web.toast.exported", { path: result.path }));
      addActivity("success", "export => " + result.path);
    }
    
    async function createSnapshot() {
      if (!projectId) {
        pushToast("warn", t("web.toast.project_required"));
        return;
      }
      const snapshot = await runApi(
        function () {
          return apiActions.createSnapshotAction(projectId);
        },
        null
      );
      if (!snapshot) {
        return;
      }
      pushToast("ok", t("web.toast.snapshot", { revision: snapshot.revision }));
      addActivity("success", "snapshot revision=" + snapshot.revision);
      await refreshProjects(projectId);
      await refreshProjectData(projectId, true);
    }
    
    async function rollbackProject() {
      if (!projectId) {
        pushToast("warn", t("web.toast.project_required"));
        return;
      }
      const revisionText = await showInput(
        t("web.modal.rollback_title"),
        t("web.modal.rollback_body"),
        t("web.modal.rollback_placeholder"),
        String(project ? project.active_revision : 0)
      );
      if (revisionText === null) {
        return;
      }
      const revision = Number(revisionText);
      if (!Number.isInteger(revision) || revision < 0) {
        pushToast("warn", t("web.toast.number_error"));
        return;
      }
      const result = await runApi(
        function () {
          return apiActions.rollbackProjectAction(projectId, revision);
        },
        null
      );
      if (!result) {
        return;
      }
      pushToast("ok", t("web.toast.rolled_back", { revision: revision }));
      addActivity("success", "rollback => revision " + revision);
      await refreshProjects(projectId);
      await refreshProjectData(projectId, false);
      await validateGraph();
    }
    
    async function createProject() {
      const title = newProjectTitle.trim();
      if (!title) {
        return;
      }
      const created = await runApi(
        function () {
          return apiActions.createProjectAction(title);
        },
        t("web.toast.created")
      );
      if (!created) {
        return;
      }
      setNewProjectTitle("");
      await refreshProjects(created.id);
      await refreshProjectData(created.id, false);
      addActivity("success", "project created: " + created.id);
    }
    
    async function runOutlineGuide() {
      if (!projectId) {
        pushToast("warn", t("web.toast.project_required"));
        return;
      }
      if (isMockProvider()) {
        const blocked = t("web.ai.mock_blocked");
        pushToast("warn", blocked);
        return;
      }
      const goal = String(outlineGuideForm.goal || "").trim();
      if (!goal) {
        pushToast("warn", t("web.outline.missing_goal"));
        return;
      }
      setOutlineGuideBusy(true);
      const outcome = await runApiDetailed(
        function () {
          return apiRequest("/api/ai/outline/guide", {
            method: "POST",
            timeout_ms: aiRequestTimeoutMs(),
            body: {
              project_id: projectId,
              goal: goal,
              sync_context: String(outlineGuideForm.sync_context || ""),
              specify: String(outlineGuideForm.specify || ""),
              clarify_answers: String(outlineGuideForm.clarify_answers || ""),
              plan_notes: String(outlineGuideForm.plan_notes || ""),
              constraints: String(outlineGuideForm.constraints || ""),
              tone: String(outlineGuideForm.tone || ""),
              token_budget: Math.max(1200, Math.floor(asNumber(aiConfig.token_budget, 2200)))
            }
          });
        },
        null
      );
      setOutlineGuideBusy(false);
      if (!outcome.ok) {
        return;
      }
      const payload = outcome.data || {};
      setOutlineGuideForm(function (prev) {
        return Object.assign({}, prev, {
          outline_markdown: String(payload.outline_markdown || ""),
          questions: Array.isArray(payload.questions) ? payload.questions.slice(0, 12) : [],
          chapter_beats: Array.isArray(payload.chapter_beats) ? payload.chapter_beats.slice(0, 20) : [],
          next_steps: Array.isArray(payload.next_steps) ? payload.next_steps.slice(0, 12) : []
        });
      });
      pushToast("ok", t("web.toast.ai_done"));
      addActivity("success", "outline guide generated");
    }
    
    async function saveOutlineNodeFromGuide() {
      if (!projectId) {
        pushToast("warn", t("web.toast.project_required"));
        return;
      }
      const outlineText = String(outlineGuideForm.outline_markdown || "").trim();
      if (!outlineText) {
        pushToast("warn", t("web.outline.missing_outline"));
        return;
      }
      const node = await runApi(
        function () {
          return apiRequest("/api/projects/" + projectId + "/nodes", {
            method: "POST",
            body: {
              title: t("web.outline.default_node_title"),
              type: "chapter",
              status: "generated",
              storyline_id: null,
              pos_x: 120,
              pos_y: 120,
              metadata: {
                project_outline: true,
                outline_kind: "project_outline",
                ai_outline_seed: true,
                ai_outline_seed_marker: "workflow_outline_seed_v1",
                outline_goal: String(outlineGuideForm.goal || ""),
                outline_sync_context: String(outlineGuideForm.sync_context || ""),
                outline_specify: String(outlineGuideForm.specify || ""),
                outline_clarify_answers: String(outlineGuideForm.clarify_answers || ""),
                outline_plan_notes: String(outlineGuideForm.plan_notes || ""),
                outline_constraints: String(outlineGuideForm.constraints || ""),
                outline_tone: String(outlineGuideForm.tone || ""),
                outline_questions: Array.isArray(outlineGuideForm.questions) ? outlineGuideForm.questions : [],
                outline_chapter_beats: Array.isArray(outlineGuideForm.chapter_beats)
                  ? outlineGuideForm.chapter_beats
                  : [],
                outline_next_steps: Array.isArray(outlineGuideForm.next_steps) ? outlineGuideForm.next_steps : [],
                outline_markdown: outlineText,
                summary: outlineText.slice(0, 200)
              }
            }
          });
        },
        t("web.toast.created")
      );
      if (!node) {
        return;
      }
      await refreshProjectData(projectId, true);
      setSelectedNodeId(node.id);
      setSidebarTab("node");
      setChatContextNodeId(node.id);
      setChatOpen(true);
      setArtifactOpen(false);
      pushToast("ok", t("web.outline.saved"));
      addActivity("success", "outline node saved: " + node.id);
    }
    
    async function deleteProject() {
      if (!project || !projectId) {
        pushToast("warn", t("web.toast.project_required"));
        return;
      }
      const confirmed = await showConfirm(
        t("web.modal.project_delete_title"),
        t("web.modal.project_delete_body", { title: project.title })
      );
      if (!confirmed) {
        return;
      }
      const result = await runApi(
        function () {
          return apiActions.deleteProjectAction(projectId);
        },
        t("web.toast.deleted")
      );
      if (!result) {
        return;
      }
      addActivity("success", "project deleted: " + projectId);
      await refreshProjects("");
    }
    
    async function toggleAllowCycles() {
      if (!project || !projectId) {
        return;
      }
      const next = !project.settings.allow_cycles;
      const updated = await runApi(
        function () {
          return apiActions.saveProjectSettingsAction(projectId, { allow_cycles: next });
        },
        t("web.toast.saved")
      );
      if (!updated) {
        return;
      }
      setProject(updated);
      setProjects(function (prev) {
        return prev.map(function (item) {
          return item.id === updated.id ? updated : item;
        });
      });
      addActivity("info", "allow_cycles => " + String(next));
    }
    
    async function saveProjectSettings() {
      if (!project || !projectId) {
        pushToast("warn", t("web.toast.project_required"));
        return;
      }
      const minutes = Math.floor(asNumber(projectSettingsForm.auto_snapshot_minutes, NaN));
      const operations = Math.floor(asNumber(projectSettingsForm.auto_snapshot_operations, NaN));
      if (!Number.isFinite(minutes) || !Number.isFinite(operations) || minutes <= 0 || operations <= 0) {
        pushToast("warn", t("web.toast.number_error"));
        return;
      }
      const updated = await runApi(
        function () {
          return apiActions.saveProjectSettingsAction(projectId, {
            allow_cycles: project.settings.allow_cycles,
            auto_snapshot_minutes: minutes,
            auto_snapshot_operations: operations
          });
        },
        t("web.toast.saved")
      );
      if (!updated) {
        return;
      }
      setProject(updated);
      setProjects(function (prev) {
        return prev.map(function (item) {
          return item.id === updated.id ? updated : item;
        });
      });
      setProjectSettingsForm({
        auto_snapshot_minutes: String(updated.settings.auto_snapshot_minutes),
        auto_snapshot_operations: String(updated.settings.auto_snapshot_operations)
      });
      addActivity(
        "success",
        "project settings saved: minutes=" +
          updated.settings.auto_snapshot_minutes +
          ", ops=" +
          updated.settings.auto_snapshot_operations
      );
    }

    return {
      loadLocaleCatalog: loadLocaleCatalog,
      loadRuntimeSettings: loadRuntimeSettings,
      loadLlmPresets: loadLlmPresets,
      applyRuntimePreset: applyRuntimePreset,
      refreshProjects: refreshProjects,
      refreshProjectData: refreshProjectData,
      loadInsights: loadInsights,
      focusNodeOnViewport: focusNodeOnViewport,
      openNodeFromInsight: openNodeFromInsight,
      validateGraph: validateGraph,
      exportGraph: exportGraph,
      createSnapshot: createSnapshot,
      rollbackProject: rollbackProject,
      createProject: createProject,
      runOutlineGuide: runOutlineGuide,
      saveOutlineNodeFromGuide: saveOutlineNodeFromGuide,
      deleteProject: deleteProject,
      toggleAllowCycles: toggleAllowCycles,
      saveProjectSettings: saveProjectSettings
    };
  }

  window.ElyhaWebAppProjectActions = {
    createProjectActionHandlers: createProjectActionHandlers
  };
})();
