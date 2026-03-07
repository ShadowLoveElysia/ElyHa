(function () {
  "use strict";

  function buildDefaultWorkflowState() {
    return {
      enabled: false,
      step: "idle",
      mode: "",
      sync_context: "",
      sync_background_markdown: "",
      sync_must_confirm: [],
      sync_citations: [],
      sync_risk_notes: [],
      specify: "",
      clarify_questions: [],
      clarify_answers: "",
      plan_notes: "",
      constraints: "",
      tone: "",
      outline_markdown: "",
      chapter_beats: [],
      next_steps: []
    };
  }

  function createWorkflowActionHandlers(deps) {
    const context = deps || {};
    const projectId = context.projectId;
    const runApi = context.runApi;
    const runApiDetailed = context.runApiDetailed;
    const apiRequest = context.apiRequest;
    const t = context.t;
    const parseWorkflowModeValue = context.parseWorkflowModeValue;
    const isWorkflowBackgroundConfirmedValue = context.isWorkflowBackgroundConfirmedValue;
    const isWorkflowOutlineConfirmedValue = context.isWorkflowOutlineConfirmedValue;
    const parseBeatListValue = context.parseBeatListValue;
    const beatTitleValue = context.beatTitleValue;
    const pushToast = context.pushToast;
    const refreshProjectData = context.refreshProjectData;
    const validateGraph = context.validateGraph;
    const setSelectedNodeId = context.setSelectedNodeId;
    const setSidebarTab = context.setSidebarTab;
    const setChatContextNodeId = context.setChatContextNodeId;
    const setChatOpen = context.setChatOpen;
    const setArtifactOpen = context.setArtifactOpen;
    const setChatWorkflow = context.setChatWorkflow;
    const setOutlineGuideField = context.setOutlineGuideField;
    const setOutlineGuideForm = context.setOutlineGuideForm;
    const outlineGuideForm = context.outlineGuideForm;
    const aiConfig = context.aiConfig;
    const asNumber = context.asNumber;
    const aiRequestTimeoutMs = context.aiRequestTimeoutMs;
    const appendChatMessage = context.appendChatMessage;
    const outlineRequired = context.outlineRequired;
    const chatContextNodeId = context.chatContextNodeId;
    const chatWorkflow = context.chatWorkflow;

    const parseWorkflowMode = parseWorkflowModeValue;
    const isWorkflowBackgroundConfirmed = isWorkflowBackgroundConfirmedValue;
    const isWorkflowOutlineConfirmed = isWorkflowOutlineConfirmedValue;
    const parseBeatList = parseBeatListValue;
    const beatTitle = function (beat, index) {
      return beatTitleValue(beat, index, {
        defaultPrefix: t("web.outline.default_scene_prefix")
      });
    };

    async function materializeWorkflowGraphPlan(flow) {
      if (!projectId) {
        return false;
      }
      const beats = parseBeatList(flow.chapter_beats, 12);
      if (beats.length === 0) {
        return false;
      }
      const groupNode = await runApi(
        function () {
          return apiRequest("/api/projects/" + projectId + "/nodes", {
            method: "POST",
            body: {
              title: t("web.outline.default_group_title"),
              type: "group",
              status: "draft",
              storyline_id: null,
              pos_x: 120,
              pos_y: 120,
              metadata: {
                group_kind: "chapter",
                group_width: 920,
                group_height: 520,
                ai_from_workflow: true,
                ai_workflow_mode: flow.mode || "original"
              }
            }
          });
        },
        null
      );
      if (!groupNode) {
        return false;
      }
      const created = [];
      for (let index = 0; index < beats.length; index += 1) {
        const beat = beats[index];
        const node = await runApi(
          function () {
            return apiRequest("/api/projects/" + projectId + "/nodes", {
              method: "POST",
              body: {
                title: beatTitle(beat, index),
                type: "chapter",
                status: "draft",
                storyline_id: null,
                pos_x: 170 + index * 220,
                pos_y: 220,
                metadata: {
                  group_parent_id: groupNode.id,
                  group_binding: "bound",
                  ai_from_workflow: true,
                  content: String(beat || ""),
                  summary: String(beat || "").slice(0, 180),
                  narrative_index: index + 1
                }
              }
            });
          },
          null
        );
        if (node) {
          created.push(node);
        }
      }
      for (let i = 1; i < created.length; i += 1) {
        await runApi(
          function () {
            return apiRequest("/api/projects/" + projectId + "/edges", {
              method: "POST",
              body: {
                source_id: created[i - 1].id,
                target_id: created[i].id,
                label: "next"
              }
            });
          },
          null
        );
      }
      await refreshProjectData(projectId, true);
      await validateGraph();
      pushToast("ok", t("web.workflow.graph_created", { count: String(created.length) }));
      return created.length > 0;
    }

    async function saveWorkflowOutlineNode(flow) {
      if (!projectId) {
        return false;
      }
      const outlineText = String(flow.outline_markdown || "").trim();
      if (!outlineText) {
        return false;
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
                outline_mode: flow.mode || "",
                outline_sync_context: String(flow.sync_context || ""),
                outline_sync_background: String(flow.sync_background_markdown || ""),
                outline_sync_must_confirm: parseBeatList(flow.sync_must_confirm, 16),
                outline_sync_citations: parseBeatList(flow.sync_citations, 20),
                outline_sync_risk_notes: parseBeatList(flow.sync_risk_notes, 12),
                outline_questions: parseBeatList(flow.clarify_questions, 12),
                outline_clarify_answers: String(flow.clarify_answers || ""),
                outline_plan_notes: String(flow.plan_notes || ""),
                outline_constraints: String(flow.constraints || ""),
                outline_tone: String(flow.tone || ""),
                outline_chapter_beats: parseBeatList(flow.chapter_beats, 20),
                outline_next_steps: parseBeatList(flow.next_steps, 12),
                content: outlineText,
                summary: outlineText.slice(0, 200)
              }
            }
          });
        },
        null
      );
      if (!node) {
        return false;
      }
      await refreshProjectData(projectId, true);
      setSelectedNodeId(node.id);
      setSidebarTab("node");
      setChatContextNodeId(node.id);
      setChatOpen(true);
      setArtifactOpen(false);
      pushToast("ok", t("web.outline.saved"));
      return true;
    }

    async function handleWorkflowChat(text) {
      if (!outlineRequired) {
        return false;
      }
      if (chatContextNodeId.trim()) {
        return false;
      }
      const message = String(text || "").trim();
      const current = chatWorkflow && typeof chatWorkflow === "object" ? chatWorkflow : buildDefaultWorkflowState();
      if (!current.enabled) {
        return false;
      }
      const step = String(current.step || "start");
      if (step === "start") {
        const mode = parseWorkflowMode(message);
        if (!mode) {
          appendChatMessage("assistant", t("web.workflow.need_mode"), t("web.chat.route_label", { route: "workflow" }));
          return true;
        }
        setChatWorkflow(function (prev) {
          return Object.assign({}, prev, { mode: mode, step: "goal" });
        });
        appendChatMessage("assistant", t("web.workflow.ask_goal"), t("web.chat.route_label", { route: "workflow" }));
        return true;
      }
      if (step === "goal") {
        if (message.length < 6) {
          appendChatMessage("assistant", t("web.workflow.need_goal"), t("web.chat.route_label", { route: "workflow" }));
          return true;
        }
        setChatWorkflow(function (prev) {
          return Object.assign({}, prev, { step: "sync" });
        });
        setOutlineGuideField("goal", message);
        appendChatMessage("assistant", t("web.workflow.ask_sync"), t("web.chat.route_label", { route: "workflow" }));
        return true;
      }
      if (step === "sync") {
        if (message.length < 8) {
          appendChatMessage("assistant", t("web.workflow.need_sync"), t("web.chat.route_label", { route: "workflow" }));
          return true;
        }
        const syncOutcome = await runApiDetailed(
          function () {
            return apiRequest("/api/ai/workflow/sync", {
              method: "POST",
              timeout_ms: aiRequestTimeoutMs(),
              body: {
                project_id: projectId,
                goal: String(outlineGuideForm.goal || ""),
                sync_context: message,
                mode: String(current.mode || ""),
                constraints: String(current.constraints || ""),
                tone: String(current.tone || ""),
                token_budget: Math.max(1000, Math.floor(asNumber(aiConfig.token_budget, 2200) / 2))
              }
            });
          },
          null
        );
        if (!syncOutcome.ok) {
          appendChatMessage("assistant", t("web.workflow.sync_failed"), t("web.chat.route_label", { route: "workflow" }));
          return true;
        }
        const syncPayload = syncOutcome.data || {};
        const backgroundMarkdown = String(syncPayload.background_markdown || "").trim();
        const mustConfirm = parseBeatList(syncPayload.must_confirm, 10);
        const citations = parseBeatList(syncPayload.citations, 12);
        const risks = parseBeatList(syncPayload.risk_notes, 8);
        setChatWorkflow(function (prev) {
          return Object.assign({}, prev, {
            sync_context: message,
            sync_background_markdown: backgroundMarkdown,
            sync_must_confirm: mustConfirm,
            sync_citations: citations,
            sync_risk_notes: risks,
            step: "sync_confirm"
          });
        });
        setOutlineGuideField("sync_context", message);
        appendChatMessage(
          "assistant",
          t("web.workflow.sync_ready") +
            "\n\n" +
            (backgroundMarkdown || "-") +
            (mustConfirm.length > 0
              ? "\n\n[Must Confirm]\n" +
                mustConfirm.map(function (item, index) {
                  return String(index + 1) + ". " + item;
                }).join("\n")
              : "") +
            (citations.length > 0
              ? "\n\n[Citations]\n" +
                citations.map(function (item, index) {
                  return String(index + 1) + ". " + item;
                }).join("\n")
              : "") +
            (risks.length > 0
              ? "\n\n[Risk Notes]\n" +
                risks.map(function (item, index) {
                  return String(index + 1) + ". " + item;
                }).join("\n")
              : "") +
            "\n\n" +
            t("web.workflow.sync_confirm_keyword"),
          t("web.chat.route_label", { route: "workflow" })
        );
        return true;
      }
      if (step === "sync_confirm") {
        if (isWorkflowBackgroundConfirmed(message)) {
          setChatWorkflow(function (prev) {
            return Object.assign({}, prev, { step: "specify" });
          });
          appendChatMessage("assistant", t("web.workflow.ask_specify"), t("web.chat.route_label", { route: "workflow" }));
          return true;
        }
        if (message.length < 2) {
          appendChatMessage("assistant", t("web.workflow.sync_wait_confirm"), t("web.chat.route_label", { route: "workflow" }));
          return true;
        }
        const mergedSync = [String(current.sync_context || "").trim(), message]
          .filter(Boolean)
          .join("\n[补充]\n");
        const syncOutcome = await runApiDetailed(
          function () {
            return apiRequest("/api/ai/workflow/sync", {
              method: "POST",
              timeout_ms: aiRequestTimeoutMs(),
              body: {
                project_id: projectId,
                goal: String(outlineGuideForm.goal || ""),
                sync_context: mergedSync,
                mode: String(current.mode || ""),
                constraints: String(current.constraints || ""),
                tone: String(current.tone || ""),
                token_budget: Math.max(1000, Math.floor(asNumber(aiConfig.token_budget, 2200) / 2))
              }
            });
          },
          null
        );
        if (!syncOutcome.ok) {
          appendChatMessage("assistant", t("web.workflow.sync_failed"), t("web.chat.route_label", { route: "workflow" }));
          return true;
        }
        const syncPayload = syncOutcome.data || {};
        const backgroundMarkdown = String(syncPayload.background_markdown || "").trim();
        const mustConfirm = parseBeatList(syncPayload.must_confirm, 10);
        const citations = parseBeatList(syncPayload.citations, 12);
        const risks = parseBeatList(syncPayload.risk_notes, 8);
        setChatWorkflow(function (prev) {
          return Object.assign({}, prev, {
            sync_context: mergedSync,
            sync_background_markdown: backgroundMarkdown,
            sync_must_confirm: mustConfirm,
            sync_citations: citations,
            sync_risk_notes: risks,
            step: "sync_confirm"
          });
        });
        setOutlineGuideField("sync_context", mergedSync);
        appendChatMessage(
          "assistant",
          t("web.workflow.sync_ready") +
            "\n\n" +
            (backgroundMarkdown || "-") +
            "\n\n" +
            t("web.workflow.sync_confirm_keyword"),
          t("web.chat.route_label", { route: "workflow" })
        );
        return true;
      }
      if (step === "specify") {
        if (message.length < 8) {
          appendChatMessage("assistant", t("web.workflow.need_specify"), t("web.chat.route_label", { route: "workflow" }));
          return true;
        }
        setChatWorkflow(function (prev) {
          return Object.assign({}, prev, { specify: message });
        });
        setOutlineGuideField("specify", message);
        const clarifyOutcome = await runApiDetailed(
          function () {
            return apiRequest("/api/ai/workflow/clarify", {
              method: "POST",
              timeout_ms: aiRequestTimeoutMs(),
              body: {
                project_id: projectId,
                goal: String(outlineGuideForm.goal || message),
                sync_context: String(current.sync_context || ""),
                specify: message,
                constraints: String(current.constraints || ""),
                tone: String(current.tone || ""),
                token_budget: Math.max(900, Math.floor(asNumber(aiConfig.token_budget, 2200) / 2))
              }
            });
          },
          null
        );
        if (!clarifyOutcome.ok) {
          appendChatMessage("assistant", t("web.workflow.clarify_failed"), t("web.chat.route_label", { route: "workflow" }));
          return true;
        }
        const questions = parseBeatList(clarifyOutcome.data && clarifyOutcome.data.questions, 8);
        setChatWorkflow(function (prev) {
          return Object.assign({}, prev, {
            clarify_questions: questions,
            step: "clarify_answers"
          });
        });
        setOutlineGuideField("questions", questions);
        appendChatMessage(
          "assistant",
          t("web.workflow.ask_clarify_answers") +
            "\n" +
            questions.map(function (item, index) {
              return String(index + 1) + ". " + item;
            }).join("\n"),
          t("web.chat.route_label", { route: "workflow" })
        );
        return true;
      }
      if (step === "clarify_answers") {
        if (message.length < 8) {
          appendChatMessage("assistant", t("web.workflow.need_clarify_answers"), t("web.chat.route_label", { route: "workflow" }));
          return true;
        }
        setChatWorkflow(function (prev) {
          return Object.assign({}, prev, {
            clarify_answers: message,
            step: "plan_notes"
          });
        });
        setOutlineGuideField("clarify_answers", message);
        appendChatMessage("assistant", t("web.workflow.ask_plan_notes"), t("web.chat.route_label", { route: "workflow" }));
        return true;
      }
      if (step === "plan_notes") {
        const planNotes = message;
        setChatWorkflow(function (prev) {
          return Object.assign({}, prev, {
            plan_notes: planNotes,
            step: "confirm_outline"
          });
        });
        setOutlineGuideField("plan_notes", planNotes);
        const planOutcome = await runApiDetailed(
          function () {
            return apiRequest("/api/ai/outline/guide", {
              method: "POST",
              timeout_ms: aiRequestTimeoutMs(),
              body: {
                project_id: projectId,
                goal: String(outlineGuideForm.goal || ""),
                sync_context: String(current.sync_context || ""),
                specify: String(current.specify || ""),
                clarify_answers: String(current.clarify_answers || ""),
                plan_notes: planNotes,
                constraints: String(current.constraints || ""),
                tone: String(current.tone || ""),
                token_budget: Math.max(1400, Math.floor(asNumber(aiConfig.token_budget, 2200)))
              }
            });
          },
          null
        );
        if (!planOutcome.ok) {
          appendChatMessage("assistant", t("web.workflow.plan_failed"), t("web.chat.route_label", { route: "workflow" }));
          return true;
        }
        const payload = planOutcome.data || {};
        const outline = String(payload.outline_markdown || "").trim();
        const beats = parseBeatList(payload.chapter_beats, 16);
        const nextSteps = parseBeatList(payload.next_steps, 10);
        setChatWorkflow(function (prev) {
          return Object.assign({}, prev, {
            outline_markdown: outline,
            chapter_beats: beats,
            next_steps: nextSteps
          });
        });
        setOutlineGuideForm(function (prev) {
          return Object.assign({}, prev, {
            outline_markdown: outline,
            chapter_beats: beats,
            next_steps: nextSteps
          });
        });
        appendChatMessage(
          "assistant",
          t("web.workflow.outline_ready") +
            "\n\n" +
            outline +
            "\n\n" +
            t("web.workflow.confirm_keyword"),
          t("web.chat.route_label", { route: "workflow" })
        );
        return true;
      }
      if (step === "confirm_outline") {
        if (!isWorkflowOutlineConfirmed(message)) {
          appendChatMessage("assistant", t("web.workflow.wait_confirm"), t("web.chat.route_label", { route: "workflow" }));
          return true;
        }
        const flow = chatWorkflow;
        const saved = await saveWorkflowOutlineNode(flow);
        if (!saved) {
          appendChatMessage("assistant", t("web.workflow.save_outline_failed"), t("web.chat.route_label", { route: "workflow" }));
          return true;
        }
        await materializeWorkflowGraphPlan(flow);
        setChatWorkflow(buildDefaultWorkflowState());
        appendChatMessage("assistant", t("web.workflow.done"), t("web.chat.route_label", { route: "workflow" }));
        return true;
      }
      return false;
    }

    return {
      materializeWorkflowGraphPlan: materializeWorkflowGraphPlan,
      saveWorkflowOutlineNode: saveWorkflowOutlineNode,
      handleWorkflowChat: handleWorkflowChat
    };
  }

  window.ElyhaWebAppWorkflowActions = {
    buildDefaultWorkflowState: buildDefaultWorkflowState,
    createWorkflowActionHandlers: createWorkflowActionHandlers
  };
})();
