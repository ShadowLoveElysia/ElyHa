(function () {
  "use strict";

  window.ElyhaWebAppModules = window.ElyhaWebAppModules || {};

  window.ElyhaWebAppModules.renderAppView = function renderAppView(deps) {
    const {
      h,
      useMemo,
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
      createNodeActionHandlersValue,
      buildDefaultWorkflowState,
      resolveActiveChatContext,
      nextArtifactDiffNodeId,
      shouldShowArtifactDiff,
      normalizeDiffKind,
      diffPrefix,
      locale,
      setLocale,
      persistedWebStateRef,
      persistedWebState,
      persistedArtifactOpen,
      persistedChatOpen,
      catalog,
      setCatalog,
      projects,
      setProjects,
      projectId,
      setProjectId,
      project,
      setProject,
      nodes,
      setNodes,
      edges,
      setEdges,
      selectedNodeId,
      setSelectedNodeId,
      inspector,
      setInspector,
      newProjectTitle,
      setNewProjectTitle,
      newNodeForm,
      setNewNodeForm,
      projectSettingsForm,
      setProjectSettingsForm,
      outlineGuideForm,
      setOutlineGuideForm,
      outlineGuideBusy,
      setOutlineGuideBusy,
      runtimeSettings,
      setRuntimeSettings,
      runtimeProfiles,
      setRuntimeProfiles,
      activeRuntimeProfile,
      setActiveRuntimeProfile,
      newRuntimeProfile,
      setNewRuntimeProfile,
      renameRuntimeProfile,
      setRenameRuntimeProfile,
      llmPresets,
      setLlmPresets,
      runtimePresetTag,
      setRuntimePresetTag,
      sidebarTab,
      setSidebarTab,
      mainView,
      setMainView,
      storylineFilter,
      setStorylineFilter,
      zoom,
      setZoom,
      aiConfig,
      setAiConfig,
      aiResult,
      setAiResult,
      edgeMode,
      setEdgeMode,
      autoBindOnDrop,
      setAutoBindOnDrop,
      edgeSourceId,
      setEdgeSourceId,
      validationReport,
      setValidationReport,
      activities,
      setActivities,
      toasts,
      setToasts,
      modal,
      setModal,
      chatOpen,
      setChatOpen,
      artifactOpen,
      setArtifactOpen,
      chatContextNodeId,
      setChatContextNodeId,
      artifactContextNodeId,
      setArtifactContextNodeId,
      chatInput,
      setChatInput,
      chatMessages,
      setChatMessages,
      chatBusy,
      setChatBusy,
      chatWorkflow,
      setChatWorkflow,
      artifactDiffSegments,
      setArtifactDiffSegments,
      artifactDiffNodeId,
      setArtifactDiffNodeId,
      collapsedGroupIds,
      setCollapsedGroupIds,
      ghostPlans,
      setGhostPlans,
      ghostArchive,
      setGhostArchive,
      expandedGhostIds,
      setExpandedGhostIds,
      selectedGhostIds,
      setSelectedGhostIds,
      retiringGhostIds,
      setRetiringGhostIds,
      ghostFusionBusy,
      setGhostFusionBusy,
      nodeFlowStates,
      setNodeFlowStates,
      insightData,
      setInsightData,
      insightBusy,
      setInsightBusy,
      insightError,
      setInsightError,
      insightHighlightNodeIds,
      setInsightHighlightNodeIds,
      modalResolverRef,
      nodesRef,
      viewportRef,
      contextMenuSuppressUntilRef,
      ghostClickSuppressUntilRef,
      chatLogRef,
      outlineRequired
    } = deps;

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
  };
})();
