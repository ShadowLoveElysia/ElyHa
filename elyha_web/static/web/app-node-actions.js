(function () {
  "use strict";

  function createNodeActionHandlers(deps) {
    const context = deps || {};
    const projectId = context.projectId;
    const outlineRequired = context.outlineRequired;
    const pushToast = context.pushToast;
    const t = context.t;
    const setSidebarTab = context.setSidebarTab;
    const newNodeForm = context.newNodeForm;
    const NODE_WIDTH = context.NODE_WIDTH;
    const NODE_HEIGHT = context.NODE_HEIGHT;
    const asNumber = context.asNumber;
    const runApi = context.runApi;
    const runApiDetailed = context.runApiDetailed;
    const apiRequest = context.apiRequest;
    const apiActions = context.apiActions;
    const setNewNodeForm = context.setNewNodeForm;
    const setSelectedNodeId = context.setSelectedNodeId;
    const addActivity = context.addActivity;
    const refreshProjectData = context.refreshProjectData;
    const selectedNodeId = context.selectedNodeId;
    const inspector = context.inspector;
    const applyGroupBinding = context.applyGroupBinding;
    const arrangeGroupChildren = context.arrangeGroupChildren;
    const clearSuggestedNodes = context.clearSuggestedNodes;
    const showConfirm = context.showConfirm;
    const nodes = context.nodes;
    const edges = context.edges;
    const showInput = context.showInput;
    const acceptSuggestedNode = context.acceptSuggestedNode;
    const getNodeById = context.getNodeById;
    const compareEdgesByNarrativeOrder = context.compareEdgesByNarrativeOrder;
    const validateGraph = context.validateGraph;
    const aiRequestTimeoutMs = context.aiRequestTimeoutMs;
    const isMockProvider = context.isMockProvider;
    const setAiResult = context.setAiResult;
    const aiConfig = context.aiConfig;
    const startNodeFlow = context.startNodeFlow;
    const stopNodeFlow = context.stopNodeFlow;
    const formatAgentTrace = context.formatAgentTrace;

async function createNode() {
      if (!projectId) {
        pushToast("warn", t("web.toast.project_required"));
        return;
      }
      if (outlineRequired) {
        pushToast("warn", t("web.outline.required_before_node"));
        setSidebarTab("project");
        return;
      }
      const title = newNodeForm.title.trim();
      if (!title) {
        return;
      }
      const metadata = {};
      const agentPreset = String(newNodeForm.agent_preset || "").trim();
      if (agentPreset) {
        metadata.agent_preset = agentPreset;
      }
      if (newNodeForm.type === "group") {
        metadata.group_kind = newNodeForm.group_kind === "chapter" ? "chapter" : "phase";
        metadata.group_width = Math.max(NODE_WIDTH * 1.8, asNumber(newNodeForm.group_width, 820));
        metadata.group_height = Math.max(NODE_HEIGHT * 1.6, asNumber(newNodeForm.group_height, 460));
      }
      const payload = {
        title: title,
        type: newNodeForm.type,
        status: newNodeForm.status,
        storyline_id: newNodeForm.storyline_id.trim() || null,
        pos_x: asNumber(newNodeForm.pos_x, 120),
        pos_y: asNumber(newNodeForm.pos_y, 120),
        metadata: metadata
      };
      const node = await runApi(
        function () {
          return apiActions.createNodeAction(projectId, payload);
        },
        t("web.toast.created")
      );
      if (!node) {
        return;
      }
      setNewNodeForm(function (prev) {
        return Object.assign({}, prev, {
          title: "",
          storyline_id: "",
          agent_preset: "",
          group_kind: "phase",
          group_width: "820",
          group_height: "460"
        });
      });
      setSelectedNodeId(node.id);
      addActivity("success", "node created: " + node.id);
      await refreshProjectData(projectId, true);
    }
    
    async function saveInspector() {
      if (!projectId || !selectedNodeId || !inspector) {
        pushToast("warn", t("web.toast.node_required"));
        return;
      }
      let metadata = {};
      const source = (inspector.metadata_json || "").trim();
      if (source) {
        try {
          const parsed = JSON.parse(source);
          if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
            pushToast("warn", t("web.toast.metadata_json_error"));
            return;
          }
          metadata = parsed;
        } catch (_error) {
          pushToast("warn", t("web.toast.metadata_json_error"));
          return;
        }
      }
      const agentPreset = String(inspector.agent_preset || "").trim();
      if (agentPreset) {
        metadata.agent_preset = agentPreset;
      }
      if (inspector.type === "group") {
        metadata.group_kind = inspector.group_kind === "chapter" ? "chapter" : "phase";
        metadata.group_width = Math.max(NODE_WIDTH * 1.8, asNumber(inspector.group_width, 820));
        metadata.group_height = Math.max(NODE_HEIGHT * 1.6, asNumber(inspector.group_height, 460));
        delete metadata.group_binding;
        delete metadata.group_parent_id;
      } else {
        const binding = inspector.group_binding === "bound" ? "bound" : "independent";
        const parentId = String(inspector.group_parent_id || "").trim();
        metadata = applyGroupBinding(metadata, binding, parentId);
        delete metadata.group_kind;
        delete metadata.group_width;
        delete metadata.group_height;
      }
    
      const payload = {
        title: inspector.title.trim() || "Untitled",
        type: inspector.type,
        status: inspector.status,
        storyline_id: inspector.storyline_id.trim() || null,
        metadata: metadata
      };
    
      const node = await runApi(
        function () {
          return apiActions.updateNodeAction(projectId, selectedNodeId, payload);
        },
        t("web.toast.saved")
      );
      if (!node) {
        return;
      }
      addActivity("success", "node updated: " + node.id);
      await refreshProjectData(projectId, true);
      if (inspector.type === "group") {
        await arrangeGroupChildren(node.id);
      } else if ((inspector.group_binding || "independent") === "bound" && (inspector.group_parent_id || "").trim()) {
        await arrangeGroupChildren(String(inspector.group_parent_id).trim());
      }
      await clearSuggestedNodes(false);
    }
    
    async function deleteNode() {
      if (!projectId || !selectedNodeId) {
        pushToast("warn", t("web.toast.node_required"));
        return;
      }
      const selectedNode = nodes.find(function (item) {
        return item.id === selectedNodeId;
      });
      if (!selectedNode) {
        return;
      }
      const confirmed = await showConfirm(
        t("web.modal.node_delete_title"),
        t("web.modal.node_delete_body", { title: selectedNode.title })
      );
      if (!confirmed) {
        return;
      }
      const result = await runApi(
        function () {
          return apiActions.deleteNodeAction(projectId, selectedNodeId);
        },
        t("web.toast.deleted")
      );
      if (!result) {
        return;
      }
      setSelectedNodeId("");
      addActivity("success", "node deleted: " + selectedNodeId);
      await refreshProjectData(projectId, true);
      await validateGraph();
    }
    
    async function deleteEdge(edgeId) {
      if (!projectId) {
        return;
      }
      const edge = edges.find(function (item) {
        return item.id === edgeId;
      });
      if (!edge) {
        return;
      }
      const confirmed = await showConfirm(
        t("web.modal.edge_delete_title"),
        t("web.modal.edge_delete_body", {
          source: edge.source_id,
          target: edge.target_id
        })
      );
      if (!confirmed) {
        return;
      }
      const result = await runApi(
        function () {
          return apiActions.deleteEdgeAction(projectId, edgeId);
        },
        t("web.toast.deleted")
      );
      if (!result) {
        return;
      }
      addActivity("success", "edge deleted: " + edgeId);
      await refreshProjectData(projectId, true);
      await validateGraph();
    }
    
    async function createEdge(sourceId, targetId) {
      if (!projectId) {
        return;
      }
      const labelText = await showInput(
        t("web.modal.edge_label_title"),
        t("web.modal.edge_label_body"),
        t("web.modal.edge_label_placeholder"),
        ""
      );
      if (labelText === null) {
        return;
      }
      const edge = await runApi(
        function () {
          return apiActions.createEdgeAction(projectId, sourceId, targetId, labelText.trim());
        },
        t("web.toast.created")
      );
      if (!edge) {
        return;
      }
      const sourceAccepted = await acceptSuggestedNode(sourceId);
      const targetAccepted = await acceptSuggestedNode(targetId);
      if (!sourceAccepted || !targetAccepted) {
        await refreshProjectData(projectId, true);
        return;
      }
      addActivity("success", "edge created: " + edge.id);
      await refreshProjectData(projectId, true);
      await validateGraph();
    }
    
    async function reorderEdge(edgeId, direction) {
      if (!projectId) {
        return;
      }
      const edge = edges.find(function (item) {
        return item.id === edgeId;
      });
      if (!edge) {
        return;
      }
      const nodeMap = typeof getNodeById === "function" ? getNodeById() : {};
      const source = nodeMap && typeof nodeMap === "object" ? nodeMap[edge.source_id] : null;
      if (source && source.type === "group") {
        pushToast("warn", t("web.toast.edge_group_reorder_not_supported"));
        return;
      }
      const siblings = edges
        .filter(function (item) {
          return item.source_id === edge.source_id;
        })
        .slice()
        .sort(compareEdgesByNarrativeOrder);
      if (siblings.length < 2) {
        return;
      }
      const index = siblings.findIndex(function (item) {
        return item.id === edgeId;
      });
      if (index < 0) {
        return;
      }
      const targetIndex = index + direction;
      if (targetIndex < 0 || targetIndex >= siblings.length) {
        return;
      }
      const orderedIds = siblings.map(function (item) {
        return item.id;
      });
      const temp = orderedIds[index];
      orderedIds[index] = orderedIds[targetIndex];
      orderedIds[targetIndex] = temp;
      const result = await runApi(
        function () {
          return apiRequest("/api/projects/" + projectId + "/edges/reorder", {
            method: "POST",
            body: {
              source_id: edge.source_id,
              edge_ids: orderedIds
            }
          });
        },
        t("web.toast.saved")
      );
      if (!result) {
        return;
      }
      addActivity("info", "edge reordered: source=" + edge.source_id);
      await refreshProjectData(projectId, true);
    }
    
    async function runAi(action) {
      if (!projectId || !selectedNodeId) {
        pushToast("warn", t("web.toast.node_required"));
        return;
      }
      if (isMockProvider()) {
        const blocked = t("web.ai.mock_blocked");
        setAiResult(blocked);
        pushToast("warn", blocked);
        return;
      }
      const tokenBudget = Math.max(1, Math.floor(asNumber(aiConfig.token_budget, 2200)));
      let flowSuccess = false;
      if (action === "generate_chapter") {
        startNodeFlow(selectedNodeId, ["running"]);
      } else if (action === "generate_branches") {
        startNodeFlow(selectedNodeId, ["planning"]);
      } else {
        startNodeFlow(selectedNodeId, ["reviewing"]);
      }
    
      if (action === "generate_chapter") {
        const outcome = await runApiDetailed(
          function () {
            return apiRequest("/api/generate/chapter", {
              method: "POST",
              timeout_ms: aiRequestTimeoutMs(),
              body: {
                project_id: projectId,
                node_id: selectedNodeId,
                token_budget: tokenBudget,
                workflow_mode: aiConfig.workflow_mode
              }
            });
          },
          t("web.toast.ai_done")
        );
        if (!outcome.ok) {
          setAiResult(t("web.ai.error_result", { message: outcome.error }));
          stopNodeFlow(selectedNodeId);
          return;
        }
        const result = outcome.data;
        if (!result) {
          setAiResult(t("web.ai.error_result", { message: "-" }));
          stopNodeFlow(selectedNodeId);
          return;
        }
        const content = String(result.content || "").trim();
        const traceText = formatAgentTrace(result.agent_trace);
        const resultText = traceText ? [content || "-", "", "---", traceText].join("\n") : content || "-";
        setAiResult(resultText);
        flowSuccess = true;
      }
    
      if (action === "generate_branches") {
        const outcome = await runApiDetailed(
          function () {
            return apiRequest("/api/generate/branches", {
              method: "POST",
              timeout_ms: aiRequestTimeoutMs(),
              body: {
                project_id: projectId,
                node_id: selectedNodeId,
                n: 3,
                token_budget: tokenBudget
              }
            });
          },
          t("web.toast.ai_done")
        );
        if (!outcome.ok) {
          setAiResult(t("web.ai.error_result", { message: outcome.error }));
          stopNodeFlow(selectedNodeId);
          return;
        }
        const result = outcome.data;
        if (!result) {
          setAiResult(t("web.ai.error_result", { message: "-" }));
          stopNodeFlow(selectedNodeId);
          return;
        }
        const lines = (result.options || []).map(function (item, index) {
          return (index + 1).toString() + ". " + item.title + "\n" + item.description;
        });
        setAiResult(lines.join("\n\n"));
        flowSuccess = true;
      }
    
      if (action === "review_lore" || action === "review_logic") {
        const endpoint = action === "review_lore" ? "/api/review/lore" : "/api/review/logic";
        const outcome = await runApiDetailed(
          function () {
            return apiRequest(endpoint, {
              method: "POST",
              timeout_ms: aiRequestTimeoutMs(),
              body: {
                project_id: projectId,
                node_id: selectedNodeId,
                token_budget: tokenBudget
              }
            });
          },
          t("web.toast.ai_done")
        );
        if (!outcome.ok) {
          setAiResult(t("web.ai.error_result", { message: outcome.error }));
          stopNodeFlow(selectedNodeId);
          return;
        }
        const result = outcome.data;
        if (!result) {
          setAiResult(t("web.ai.error_result", { message: "-" }));
          stopNodeFlow(selectedNodeId);
          return;
        }
        const issues = Array.isArray(result.issues) ? result.issues : [];
        const text = [
          "summary: " + (result.summary || "-"),
          "score: " + String(result.score),
          "",
          "issues:",
          issues.length > 0
            ? issues.map(function (item, index) {
                return "- " + (index + 1).toString() + ") " + String(item);
              }).join("\n")
            : "- none"
        ].join("\n");
        setAiResult(text);
        flowSuccess = true;
      }
    
      addActivity("info", "ai action: " + action + " node=" + selectedNodeId);
      await refreshProjectData(projectId, true);
      if (flowSuccess) {
        setTimeout(function () {
          stopNodeFlow(selectedNodeId);
        }, 320);
      } else {
        stopNodeFlow(selectedNodeId);
      }
    }

    return {
      createNode: createNode,
      saveInspector: saveInspector,
      deleteNode: deleteNode,
      deleteEdge: deleteEdge,
      createEdge: createEdge,
      reorderEdge: reorderEdge,
      runAi: runAi
    };
  }

  window.ElyhaWebAppNodeActions = {
    createNodeActionHandlers: createNodeActionHandlers
  };
})();
