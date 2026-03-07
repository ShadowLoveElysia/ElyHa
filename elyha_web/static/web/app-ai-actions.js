/**
 * app-ai-actions.js
 * AI 和工作流相关的 API 调用
 */

(function () {
  "use strict";

  window.ElyhaWebAiActions = {
    // 聊天
    sendChatMessageAction: sendChatMessageAction,

    // 工作流
    syncWorkflowBackgroundAction: syncWorkflowBackgroundAction,
    syncWorkflowOutlineAction: syncWorkflowOutlineAction,
    clarifyWorkflowAction: clarifyWorkflowAction,
    guideOutlineAction: guideOutlineAction,

    // 生成
    generateChapterAction: generateChapterAction,
    generateBranchesAction: generateBranchesAction,
    reviewLoreAction: reviewLoreAction,
    reviewLogicAction: reviewLogicAction
  };

  const helpers = window.ElyhaWebHelpers || {};
  const apiRequest = helpers.apiRequest;

  if (!apiRequest) {
    throw new Error("ElyhaWebHelpers.apiRequest is required");
  }

  // ========== 聊天 ==========

  async function sendChatMessageAction(payload) {
    return apiRequest("/api/ai/chat", {
      method: "POST",
      body: payload
    });
  }

  // ========== 工作流 ==========

  async function syncWorkflowBackgroundAction(projectId, nodeId, payload) {
    return apiRequest("/api/ai/workflow/sync", {
      method: "POST",
      body: Object.assign({}, payload, {
        project_id: projectId,
        node_id: nodeId,
        phase: "background"
      })
    });
  }

  async function syncWorkflowOutlineAction(projectId, nodeId, payload) {
    return apiRequest("/api/ai/workflow/sync", {
      method: "POST",
      body: Object.assign({}, payload, {
        project_id: projectId,
        node_id: nodeId,
        phase: "outline"
      })
    });
  }

  async function clarifyWorkflowAction(projectId, nodeId, payload) {
    return apiRequest("/api/ai/workflow/clarify", {
      method: "POST",
      body: Object.assign({}, payload, {
        project_id: projectId,
        node_id: nodeId
      })
    });
  }

  async function guideOutlineAction(projectId, nodeId, payload) {
    return apiRequest("/api/ai/outline/guide", {
      method: "POST",
      body: Object.assign({}, payload, {
        project_id: projectId,
        node_id: nodeId
      })
    });
  }

  // ========== 生成 ==========

  async function generateChapterAction(projectId, nodeId, config) {
    return apiRequest("/api/projects/" + projectId + "/nodes/" + nodeId + "/generate", {
      method: "POST",
      body: config
    });
  }

  async function generateBranchesAction(projectId, nodeId, config) {
    return apiRequest("/api/projects/" + projectId + "/nodes/" + nodeId + "/branches", {
      method: "POST",
      body: config
    });
  }

  async function reviewLoreAction(projectId, nodeId, config) {
    return apiRequest("/api/projects/" + projectId + "/nodes/" + nodeId + "/review/lore", {
      method: "POST",
      body: config
    });
  }

  async function reviewLogicAction(projectId, nodeId, config) {
    return apiRequest("/api/projects/" + projectId + "/nodes/" + nodeId + "/review/logic", {
      method: "POST",
      body: config
    });
  }

})();
