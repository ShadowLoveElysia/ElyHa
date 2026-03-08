/**
 * app-config-actions.js
 * 配置和设置相关的 API 调用
 */

(function () {
  "use strict";

  window.ElyhaWebConfigActions = {
    fetchRuntimeSettingsAction: fetchRuntimeSettingsAction,
    fetchLlmPresetsAction: fetchLlmPresetsAction,
    saveRuntimeProfileAction: saveRuntimeProfileAction,
    deleteRuntimeProfileAction: deleteRuntimeProfileAction,
    switchRuntimeProfileAction: switchRuntimeProfileAction
  };

  const helpers = window.ElyhaWebHelpers || {};
  const apiRequest = helpers.apiRequest;

  if (!apiRequest) {
    throw new Error("ElyhaWebHelpers.apiRequest is required");
  }

  async function fetchRuntimeSettingsAction() {
    return apiRequest("/api/settings/runtime");
  }

  async function fetchLlmPresetsAction() {
    return apiRequest("/api/llm/presets");
  }

  async function saveRuntimeProfileAction(profileName, config) {
    return apiRequest("/api/settings/runtime/profiles/" + profileName, {
      method: "PUT",
      body: config
    });
  }

  async function deleteRuntimeProfileAction(profileName) {
    return apiRequest("/api/settings/runtime/profiles/" + profileName, {
      method: "DELETE"
    });
  }

  async function switchRuntimeProfileAction(profileName) {
    return apiRequest("/api/settings/runtime/active", {
      method: "POST",
      body: { profile: profileName }
    });
  }

})();
