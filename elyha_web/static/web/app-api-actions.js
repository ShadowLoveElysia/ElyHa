/**
 * app-api-actions.js
 * API 调用相关的操作函数（项目、节点、边、快照、导出等）
 */

(function () {
  "use strict";

  window.ElyhaWebApiActions = {
    // 项目相关
    createProjectAction: createProjectAction,
    deleteProjectAction: deleteProjectAction,
    saveProjectSettingsAction: saveProjectSettingsAction,
    refreshProjectsAction: refreshProjectsAction,
    refreshProjectDataAction: refreshProjectDataAction,

    // 节点相关
    createNodeAction: createNodeAction,
    deleteNodeAction: deleteNodeAction,
    updateNodeAction: updateNodeAction,
    acceptSuggestedNodeAction: acceptSuggestedNodeAction,
    clearSuggestedNodesAction: clearSuggestedNodesAction,

    // 边相关
    createEdgeAction: createEdgeAction,
    deleteEdgeAction: deleteEdgeAction,
    reorderEdgeAction: reorderEdgeAction,

    // 验证和导出
    validateProjectAction: validateProjectAction,
    exportProjectAction: exportProjectAction,

    // 快照和回滚
    createSnapshotAction: createSnapshotAction,
    rollbackProjectAction: rollbackProjectAction,

    // 洞察
    fetchInsightsAction: fetchInsightsAction
  };

  const helpers = window.ElyhaWebHelpers || {};
  const apiRequest = helpers.apiRequest;

  if (!apiRequest) {
    throw new Error("ElyhaWebHelpers.apiRequest is required");
  }

  // ========== 项目相关 ==========

  async function createProjectAction(title) {
    return apiRequest("/api/projects", {
      method: "POST",
      body: { title: title }
    });
  }

  async function deleteProjectAction(projectId) {
    return apiRequest("/api/projects/" + projectId, {
      method: "DELETE"
    });
  }

  async function saveProjectSettingsAction(projectId, settings) {
    return apiRequest("/api/projects/" + projectId + "/settings", {
      method: "PUT",
      body: settings
    });
  }

  async function refreshProjectsAction() {
    return apiRequest("/api/projects");
  }

  async function refreshProjectDataAction(projectId) {
    const results = await Promise.all([
      apiRequest("/api/projects/" + projectId),
      apiRequest("/api/projects/" + projectId + "/nodes"),
      apiRequest("/api/projects/" + projectId + "/edges")
    ]);
    return {
      project: results[0],
      nodes: results[1],
      edges: results[2]
    };
  }

  // ========== 节点相关 ==========

  async function createNodeAction(projectId, nodeData) {
    return apiRequest("/api/projects/" + projectId + "/nodes", {
      method: "POST",
      body: nodeData
    });
  }

  async function deleteNodeAction(projectId, nodeId) {
    return apiRequest("/api/projects/" + projectId + "/nodes/" + nodeId, {
      method: "DELETE"
    });
  }

  async function updateNodeAction(projectId, nodeId, updates) {
    return apiRequest("/api/projects/" + projectId + "/nodes/" + nodeId, {
      method: "PUT",
      body: updates
    });
  }

  async function acceptSuggestedNodeAction(projectId, nodeId) {
    return apiRequest("/api/projects/" + projectId + "/nodes/" + nodeId, {
      method: "PUT",
      body: { metadata: { suggested: "false" } }
    });
  }

  async function clearSuggestedNodesAction(projectId) {
    return apiRequest("/api/projects/" + projectId + "/suggestions/cleanup", {
      method: "POST"
    });
  }

  // ========== 边相关 ==========

  async function createEdgeAction(projectId, sourceId, targetId, label) {
    return apiRequest("/api/projects/" + projectId + "/edges", {
      method: "POST",
      body: {
        source_id: sourceId,
        target_id: targetId,
        label: label || ""
      }
    });
  }

  async function deleteEdgeAction(projectId, edgeId) {
    return apiRequest("/api/projects/" + projectId + "/edges/" + edgeId, {
      method: "DELETE"
    });
  }

  async function reorderEdgeAction(projectId, edgeId, direction) {
    const sourceId = String(edgeId || "");
    const edgeIds = Array.isArray(direction) ? direction : [];
    return apiRequest("/api/projects/" + projectId + "/edges/reorder", {
      method: "POST",
      body: {
        source_id: sourceId,
        edge_ids: edgeIds
      }
    });
  }

  // ========== 验证和导出 ==========

  async function validateProjectAction(projectId) {
    return apiRequest("/api/projects/" + projectId + "/validate", {
      method: "POST"
    });
  }

  async function exportProjectAction(projectId, strategy) {
    return apiRequest("/api/projects/" + projectId + "/export", {
      method: "POST",
      body: { traversal: strategy || "mainline" }
    });
  }

  // ========== 快照和回滚 ==========

  async function createSnapshotAction(projectId) {
    return apiRequest("/api/projects/" + projectId + "/snapshots", {
      method: "POST"
    });
  }

  async function rollbackProjectAction(projectId, revision) {
    return apiRequest("/api/projects/" + projectId + "/rollback", {
      method: "POST",
      body: { revision: revision }
    });
  }

  // ========== 洞察 ==========

  async function fetchInsightsAction(projectId) {
    return apiRequest("/api/projects/" + projectId + "/insights");
  }

})();
