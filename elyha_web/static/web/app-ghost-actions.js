(function () {
  "use strict";

  function createGhostActionHandlers(deps) {
    const context = deps || {};
    const nodesRef = context.nodesRef;
    const nodeRenderSize = context.nodeRenderSize;
    const asNumber = context.asNumber;
    const t = context.t;
    const pickGhostOutlineSteps = context.pickGhostOutlineSteps;
    const normalizeGhostSentiment = context.normalizeGhostSentiment;
    const inferGhostSentimentFromText = context.inferGhostSentimentFromText;
    const ghostIdWithSeed = context.ghostIdWithSeed;
    const ghostOutlineTextValue = context.ghostOutlineTextValue;
    const sentimentToneColorValue = context.sentimentToneColorValue;
    const normalizeGhostOutlineSteps = context.normalizeGhostOutlineSteps;
    const safeArray = context.safeArray;
    const setGhostArchive = context.setGhostArchive;
    const ghostArchive = context.ghostArchive;
    const setGhostPlans = context.setGhostPlans;
    const setExpandedGhostIds = context.setExpandedGhostIds;
    const pushToast = context.pushToast;
    const setSelectedGhostIds = context.setSelectedGhostIds;
    const projectId = context.projectId;
    const ghostFusionBusy = context.ghostFusionBusy;
    const selectedGhostIds = context.selectedGhostIds;
    const ghostPlans = context.ghostPlans;
    const aiConfig = context.aiConfig;
    const runApiDetailed = context.runApiDetailed;
    const apiRequest = context.apiRequest;
    const aiRequestTimeoutMs = context.aiRequestTimeoutMs;
    const setGhostFusionBusy = context.setGhostFusionBusy;
    const addActivity = context.addActivity;
    const runApi = context.runApi;
    const validateGraph = context.validateGraph;
    const refreshProjectData = context.refreshProjectData;
    const setRetiringGhostIds = context.setRetiringGhostIds;
    const nodeIsSuggested = context.nodeIsSuggested;
    const nodeMetadataObject = context.nodeMetadataObject;
    const apiActions = context.apiActions;
    const pruneGhostStateMapValue = context.pruneGhostStateMapValue;

    function createGhostPlansFromOptions(sourceNodeId, options) {
      const source = nodesRef.current.find(function (item) {
        return item.id === sourceNodeId;
      });
      if (!source || !Array.isArray(options) || options.length === 0) {
        return [];
      }
      const sourceSize = nodeRenderSize(source);
      const baseX = asNumber(source.pos_x, 0) + sourceSize.width + 170;
      const baseY = asNumber(source.pos_y, 0);
      const created = [];
      options.forEach(function (option, index) {
        const title = String(option && option.title ? option.title : "").trim() || t("web.ghost.untitled");
        const description = String(option && option.description ? option.description : "").trim();
        const outlineSteps = pickGhostOutlineSteps(option, description);
        const summary = description || (outlineSteps.length > 0 ? outlineSteps[0] : "-");
        const sentiment = normalizeGhostSentiment(
          option && option.sentiment
            ? option.sentiment
            : inferGhostSentimentFromText(title, [summary].concat(outlineSteps).join("\n"))
        );
        const rootId = ghostIdWithSeed("root_" + index.toString());
        const rootPlan = {
          id: rootId,
          source_id: sourceNodeId,
          source_ghost_id: "",
          chain_root_id: rootId,
          chain_index: 0,
          source_title: source.title,
          title: title.slice(0, 200),
          description: summary,
          outline_steps: outlineSteps,
          sentiment: sentiment,
          storyline_id: source.storyline_id || "",
          pos_x: baseX + index * 230,
          pos_y: baseY + (index - 1) * 140,
          created_at: new Date().toISOString()
        };
        created.push(rootPlan);
        let parent = rootPlan;
        const followUps = outlineSteps.slice(1, 3);
        while (followUps.length < 2) {
          followUps.push(t("web.ghost.chain_fallback", { index: followUps.length + 1 }));
        }
        followUps.forEach(function (stepText, stepIndex) {
          const childId = ghostIdWithSeed("next_" + index.toString() + "_" + (stepIndex + 1).toString());
          const childTitle = title + " · " + t("web.ghost.chain_step", { index: stepIndex + 1 });
          const child = {
            id: childId,
            source_id: sourceNodeId,
            source_ghost_id: parent.id,
            chain_root_id: rootId,
            chain_index: stepIndex + 1,
            source_title: source.title,
            title: childTitle.slice(0, 200),
            description: String(stepText || "").trim() || "-",
            outline_steps: [String(stepText || "").trim() || "-"],
            sentiment: sentiment,
            storyline_id: source.storyline_id || "",
            pos_x: asNumber(parent.pos_x, 0) + 248,
            pos_y: asNumber(parent.pos_y, 0),
            created_at: new Date().toISOString()
          };
          created.push(child);
          parent = child;
        });
      });
      return created;
    }
    
    const ghostOutlineText = ghostOutlineTextValue;
    const sentimentToneColor = sentimentToneColorValue;
    
    function archiveGhostPayload(plan) {
      if (!plan || typeof plan !== "object") {
        return null;
      }
      return {
        id: String(plan.id || ghostIdWithSeed("archived_src")),
        source_id: String(plan.source_id || ""),
        source_ghost_id: String(plan.source_ghost_id || ""),
        chain_root_id: String(plan.chain_root_id || plan.id || ""),
        chain_index: Math.max(0, Math.floor(asNumber(plan.chain_index, 0))),
        source_title: String(plan.source_title || ""),
        title: String(plan.title || t("web.ghost.untitled")).slice(0, 200),
        description: String(plan.description || "").trim(),
        outline_steps: normalizeGhostOutlineSteps(plan.outline_steps || plan.description, 3),
        sentiment: normalizeGhostSentiment(plan.sentiment),
        storyline_id: String(plan.storyline_id || ""),
        pos_x: asNumber(plan.pos_x, 0),
        pos_y: asNumber(plan.pos_y, 0),
        created_at: String(plan.created_at || new Date().toISOString())
      };
    }
    
    function archiveGhostPlans(projectValue, plansToArchive) {
      const archived = safeArray(plansToArchive)
        .map(function (plan) {
          const payload = archiveGhostPayload(plan);
          if (!payload) {
            return null;
          }
          return {
            id: "ghost_arc_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 8),
            project_id: String(projectValue || ""),
            archived_at: new Date().toISOString(),
            payload: payload
          };
        })
        .filter(Boolean);
      if (archived.length === 0) {
        return 0;
      }
      setGhostArchive(function (prev) {
        return archived.concat(prev).slice(0, 260);
      });
      return archived.length;
    }
    
    function restoreGhostFromArchive(archiveId) {
      const picked = ghostArchive.find(function (item) {
        return item.id === archiveId;
      });
      if (!picked || !picked.payload || typeof picked.payload !== "object") {
        return false;
      }
      setGhostArchive(function (prev) {
        return prev.filter(function (item) {
          return item.id !== archiveId;
        });
      });
      const restoredPlan = picked.payload;
      const restored = Object.assign({}, restoredPlan, {
        id: ghostIdWithSeed("restored"),
        created_at: new Date().toISOString(),
        source_ghost_id: String(restoredPlan.source_ghost_id || "")
      });
      setGhostPlans(function (prev) {
        return prev.concat([restored]);
      });
      setExpandedGhostIds(function (prev) {
        return Object.assign({}, prev, { [restored.id]: true });
      });
      pushToast("ok", t("web.ghost.archive_restored"));
      return true;
    }
    
    function removeGhostArchiveItem(archiveId) {
      const exists = ghostArchive.some(function (item) {
        return item.id === archiveId;
      });
      if (!exists) {
        return false;
      }
      setGhostArchive(function (prev) {
        return prev.filter(function (item) {
          return item.id !== archiveId;
        });
      });
      return true;
    }
    
    function clearGhostArchiveForProject(projectValue) {
      const projectText = String(projectValue || "");
      const deleted = ghostArchive.filter(function (item) {
        return String(item.project_id || "") === projectText;
      }).length;
      if (deleted === 0) {
        return 0;
      }
      setGhostArchive(function (prev) {
        return prev.filter(function (item) {
          return String(item.project_id || "") !== projectText;
        });
      });
      pushToast("ok", t("web.ghost.archive_cleared", { count: deleted }));
      return deleted;
    }
    
    const pruneGhostStateMap = pruneGhostStateMapValue;
    
    function toggleGhostPreview(ghostId) {
      if (!ghostId) {
        return;
      }
      setExpandedGhostIds(function (prev) {
        const next = Object.assign({}, prev);
        if (next[ghostId]) {
          delete next[ghostId];
        } else {
          next[ghostId] = true;
        }
        return next;
      });
    }
    
    function toggleGhostSelection(ghostId) {
      if (!ghostId) {
        return;
      }
      setSelectedGhostIds(function (prev) {
        const next = Object.assign({}, prev);
        if (next[ghostId]) {
          delete next[ghostId];
        } else {
          next[ghostId] = true;
        }
        return next;
      });
    }
    
    async function fuseSelectedGhostPlans() {
      if (!projectId || ghostFusionBusy) {
        return false;
      }
      const selectedIds = Object.keys(selectedGhostIds).filter(function (ghostId) {
        return Boolean(selectedGhostIds[ghostId]);
      });
      if (selectedIds.length !== 2) {
        pushToast("warn", t("web.ghost.fuse_need_two"));
        return false;
      }
      const selectedPlans = selectedIds
        .map(function (ghostId) {
          return ghostPlans.find(function (item) {
            return item.id === ghostId;
          });
        })
        .filter(Boolean);
      if (selectedPlans.length !== 2) {
        pushToast("warn", t("web.ghost.fuse_not_found"));
        return false;
      }
      const sourceId = String(selectedPlans[0].source_id || "").trim();
      if (!sourceId || selectedPlans.some(function (item) {
        return String(item.source_id || "").trim() !== sourceId;
      })) {
        pushToast("warn", t("web.ghost.fuse_same_source_required"));
        return false;
      }
      const sourceNode = nodesRef.current.find(function (item) {
        return item.id === sourceId;
      });
      if (!sourceNode) {
        pushToast("warn", t("web.ghost.fuse_source_missing"));
        return false;
      }
      const first = selectedPlans[0];
      const second = selectedPlans[1];
      const mergePrompt = [
        "@plan Merge these two branch ideas into one coherent branch for the same source node.",
        "Output exactly one line in this format: Title: Description",
        "Idea A title: " + String(first.title || ""),
        "Idea A description: " + String(first.description || "-"),
        "Idea B title: " + String(second.title || ""),
        "Idea B description: " + String(second.description || "-")
      ].join("\n");
      setGhostFusionBusy(true);
      try {
        const outcome = await runApiDetailed(
          function () {
            return apiRequest("/api/ai/chat", {
              method: "POST",
              timeout_ms: aiRequestTimeoutMs(),
              body: {
                project_id: projectId,
                node_id: sourceId,
                message: mergePrompt,
                token_budget: Math.max(600, Math.floor(asNumber(aiConfig.token_budget, 2200)))
              }
            });
          },
          null
        );
        if (!outcome.ok || !outcome.data) {
          return false;
        }
        const payload = outcome.data;
        const options = Array.isArray(payload.suggested_options) ? payload.suggested_options : [];
        const picked = options[0] || {};
        const fallbackReply = String(payload.reply || "").trim();
        const fusedTitle = String(picked.title || "").trim() || t("web.ghost.fuse_default_title");
        const fusedDescription = String(picked.description || "").trim() || fallbackReply || "-";
        const created = createGhostPlansFromOptions(sourceId, [
          {
            title: fusedTitle,
            description: fusedDescription
          }
        ]);
        if (created.length === 0) {
          return false;
        }
        const fused = created[0];
        const targetX = Math.max(asNumber(first.pos_x, 0), asNumber(second.pos_x, 0)) + 250;
        const targetY = (asNumber(first.pos_y, 0) + asNumber(second.pos_y, 0)) / 2;
        const deltaX = targetX - asNumber(fused.pos_x, 0);
        const deltaY = targetY - asNumber(fused.pos_y, 0);
        const shifted = created.map(function (item) {
          return Object.assign({}, item, {
            pos_x: asNumber(item.pos_x, 0) + deltaX,
            pos_y: asNumber(item.pos_y, 0) + deltaY,
            fused_from: selectedIds.slice()
          });
        });
        setGhostPlans(function (prev) {
          return prev.concat(shifted);
        });
        setSelectedGhostIds({});
        setExpandedGhostIds(function (prev) {
          return Object.assign({}, prev, { [fused.id]: true });
        });
        addActivity("info", "ghost plans fused: " + selectedIds.join(",") + " -> " + fused.id);
        pushToast("ok", t("web.ghost.fused_created"));
        return true;
      } finally {
        setGhostFusionBusy(false);
      }
    }
    
    async function adoptGhostPlan(ghostId) {
      if (!projectId) {
        return false;
      }
      const ghost = ghostPlans.find(function (item) {
        return item.id === ghostId;
      });
      if (!ghost) {
        return false;
      }
      const sourceNode = nodesRef.current.find(function (item) {
        return item.id === ghost.source_id;
      });
      const createdNode = await runApi(
        function () {
          return apiRequest("/api/projects/" + projectId + "/nodes", {
            method: "POST",
            body: {
              title: ghost.title,
              type: "branch",
              status: sourceNode ? sourceNode.status : "draft",
              storyline_id: String(ghost.storyline_id || "").trim() || null,
              pos_x: ghost.pos_x,
              pos_y: ghost.pos_y,
              metadata: {
                summary: ghost.description,
                content: ghost.description,
                ai_from_ghost_plan: true,
                ai_from_ghost_source: ghost.source_id,
                ai_from_ghost_adopted_at: new Date().toISOString()
              }
            }
          });
        },
        null
      );
      if (!createdNode) {
        return false;
      }
      if (ghost.source_id) {
        const edge = await runApi(
          function () {
            return apiRequest("/api/projects/" + projectId + "/edges", {
              method: "POST",
              body: {
                source_id: ghost.source_id,
                target_id: createdNode.id,
                label: t("web.ghost.edge_label")
              }
            });
          },
          null
        );
        if (!edge) {
          return false;
        }
      }
      const adoptedRootId = String(ghost.chain_root_id || ghost.id);
      const sameSource = ghostPlans.filter(function (item) {
        return String(item.source_id || "") === String(ghost.source_id || "");
      });
      const sameSourceIds = new Set(
        sameSource.map(function (item) {
          return item.id;
        })
      );
      const unadopted = sameSource.filter(function (item) {
        return String(item.chain_root_id || item.id) !== adoptedRootId;
      });
      const unadoptedIds = new Set(
        unadopted.map(function (item) {
          return item.id;
        })
      );
      if (unadoptedIds.size > 0) {
        setRetiringGhostIds(function (prev) {
          const next = Object.assign({}, prev);
          unadoptedIds.forEach(function (ghostPlanId) {
            next[ghostPlanId] = true;
          });
          return next;
        });
        await new Promise(function (resolve) {
          window.setTimeout(resolve, 260);
        });
      }
      const archivedCount = archiveGhostPlans(projectId, unadopted);
      setGhostPlans(function (prev) {
        return prev.filter(function (item) {
          return String(item.source_id || "") !== String(ghost.source_id || "");
        });
      });
      setExpandedGhostIds(function (prev) {
        const next = Object.assign({}, prev);
        Object.keys(next).forEach(function (id) {
          if (sameSourceIds.has(id)) {
            delete next[id];
          }
        });
        return next;
      });
      setSelectedGhostIds(function (prev) {
        const next = Object.assign({}, prev);
        Object.keys(next).forEach(function (id) {
          if (sameSourceIds.has(id)) {
            delete next[id];
          }
        });
        return next;
      });
      if (unadoptedIds.size > 0) {
        setRetiringGhostIds(function (prev) {
          const next = Object.assign({}, prev);
          unadoptedIds.forEach(function (ghostPlanId) {
            delete next[ghostPlanId];
          });
          return next;
        });
      }
      addActivity("success", "ghost plan adopted: " + createdNode.id);
      pushToast("ok", t("web.ghost.adopted"));
      if (archivedCount > 0) {
        pushToast("ok", t("web.ghost.archive_moved", { count: archivedCount }));
      }
      await refreshProjectData(projectId, true);
      await validateGraph();
      return true;
    }
    
    function previewGhostPlan(ghostId) {
      const ghost = ghostPlans.find(function (item) {
        return item.id === ghostId;
      });
      if (!ghost) {
        return;
      }
      toggleGhostPreview(ghostId);
    }
    
    function deleteGhostRoute(ghostId) {
      const ghost = ghostPlans.find(function (item) {
        return item.id === ghostId;
      });
      if (!ghost) {
        return false;
      }
      const sourceId = String(ghost.source_id || "");
      const routeRootId = String(ghost.chain_root_id || ghost.id);
      const removed = ghostPlans.filter(function (item) {
        const sameSource = String(item.source_id || "") === sourceId;
        const sameRoute = String(item.chain_root_id || item.id) === routeRootId;
        return sameSource && sameRoute;
      });
      const removedIds = new Set(
        removed.map(function (item) {
          return item.id;
        })
      );
      if (removedIds.size === 0) {
        return false;
      }
      setGhostPlans(function (prev) {
        return prev.filter(function (item) {
          return !removedIds.has(item.id);
        });
      });
      setExpandedGhostIds(function (prev) {
        const next = Object.assign({}, prev);
        removedIds.forEach(function (id) {
          delete next[id];
        });
        return next;
      });
      setSelectedGhostIds(function (prev) {
        const next = Object.assign({}, prev);
        removedIds.forEach(function (id) {
          delete next[id];
        });
        return next;
      });
      setRetiringGhostIds(function (prev) {
        const next = Object.assign({}, prev);
        removedIds.forEach(function (id) {
          delete next[id];
        });
        return next;
      });
      addActivity("info", "ghost route deleted: " + routeRootId + " (" + removedIds.size.toString() + ")");
      pushToast("ok", t("web.ghost.deleted_route", { count: removedIds.size }));
      return true;
    }
    
    async function acceptSuggestedNode(nodeId) {
      if (!projectId || !nodeId) {
        return true;
      }
      const target = nodesRef.current.find(function (item) {
        return item.id === nodeId;
      });
      if (!target || !nodeIsSuggested(target)) {
        return true;
      }
      const nextMeta = nodeMetadataObject(target);
      delete nextMeta.ai_suggested;
      nextMeta.ai_suggestion_state = "accepted";
      nextMeta.ai_suggestion_accepted_at = new Date().toISOString();
      const updated = await runApi(
        function () {
          return apiActions.updateNodeAction(projectId, nodeId, { metadata: nextMeta });
        },
        null
      );
      return Boolean(updated);
    }
    
    async function clearSuggestedNodes(showToastMessage) {
      const localCount = ghostPlans.length;
      if (localCount > 0) {
        setGhostPlans([]);
        setExpandedGhostIds({});
        setSelectedGhostIds({});
        setRetiringGhostIds({});
      }
      if (!projectId) {
        return localCount;
      }
      const result = await runApi(
        function () {
          return apiActions.clearSuggestedNodesAction(projectId);
        },
        null
      );
      if (!result) {
        return 0;
      }
      const deleted = Math.max(0, Math.floor(asNumber(result.deleted, 0)));
      const total = deleted + localCount;
      if (showToastMessage) {
        pushToast("ok", t("web.chat.suggestions_cleared", { count: total }));
      }
      if (deleted > 0) {
        addActivity("info", "suggestions cleared: " + deleted.toString());
        await refreshProjectData(projectId, true);
        await validateGraph();
      }
      return total;
    }

    return {
      createGhostPlansFromOptions: createGhostPlansFromOptions,
      ghostOutlineText: ghostOutlineText,
      sentimentToneColor: sentimentToneColor,
      pruneGhostStateMap: pruneGhostStateMap,
      restoreGhostFromArchive: restoreGhostFromArchive,
      removeGhostArchiveItem: removeGhostArchiveItem,
      clearGhostArchiveForProject: clearGhostArchiveForProject,
      toggleGhostPreview: toggleGhostPreview,
      toggleGhostSelection: toggleGhostSelection,
      fuseSelectedGhostPlans: fuseSelectedGhostPlans,
      adoptGhostPlan: adoptGhostPlan,
      previewGhostPlan: previewGhostPlan,
      deleteGhostRoute: deleteGhostRoute,
      acceptSuggestedNode: acceptSuggestedNode,
      clearSuggestedNodes: clearSuggestedNodes
    };
  }

  window.ElyhaWebAppGhostActions = {
    createGhostActionHandlers: createGhostActionHandlers
  };
})();
