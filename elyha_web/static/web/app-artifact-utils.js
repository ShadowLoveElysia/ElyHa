(function () {
  "use strict";

  function resolveActiveChatContext(chatContextNodeId, artifactContextNodeId) {
    const chatId = String(chatContextNodeId || "").trim();
    if (chatId) {
      return chatId;
    }
    return String(artifactContextNodeId || "").trim();
  }

  function nextArtifactDiffNodeId(route, contextNodeId) {
    if (String(route || "") === "writer" && String(contextNodeId || "").trim()) {
      return String(contextNodeId || "").trim();
    }
    return "";
  }

  function shouldShowArtifactDiff(artifactTargetId, artifactDiffNodeId, diffSegments) {
    if (!Array.isArray(diffSegments) || diffSegments.length === 0) {
      return false;
    }
    const targetId = String(artifactTargetId || "").trim();
    const diffNodeId = String(artifactDiffNodeId || "").trim();
    if (!targetId || !diffNodeId) {
      return true;
    }
    return targetId === diffNodeId;
  }

  window.ElyhaWebArtifactUtils = {
    resolveActiveChatContext: resolveActiveChatContext,
    nextArtifactDiffNodeId: nextArtifactDiffNodeId,
    shouldShowArtifactDiff: shouldShowArtifactDiff
  };
})();
