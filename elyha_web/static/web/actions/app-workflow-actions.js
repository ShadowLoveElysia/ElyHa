(function () {
  "use strict";

  const WORKFLOW_OUTLINE_SEED_MARKER = "workflow_outline_seed_v1";

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
    const chatMessages = context.chatMessages;

    const parseWorkflowMode = parseWorkflowModeValue;
    const isWorkflowBackgroundConfirmed = isWorkflowBackgroundConfirmedValue;
    const isWorkflowOutlineConfirmed = isWorkflowOutlineConfirmedValue;
    const parseBeatList = parseBeatListValue;
    const beatTitle = function (beat, index) {
      return beatTitleValue(beat, index, {
        defaultPrefix: t("web.outline.default_scene_prefix")
      });
    };

    function compactWorkflowLine(value, maxLen) {
      const source = String(value || "").replace(/\s+/g, " ").trim();
      const limit = Math.max(16, Math.floor(asNumber(maxLen, 200)));
      if (!source) {
        return "";
      }
      return source.length <= limit ? source : source.slice(0, Math.max(0, limit - 1)) + "…";
    }

    function buildGoalDecisionMessage(message, flowState) {
      const history = Array.isArray(chatMessages) ? chatMessages : [];
      const scoped = history
        .filter(function (item) {
          const contextId = String(item && item.context_node_id ? item.context_node_id : "").trim();
          const role = String(item && item.role ? item.role : "").trim().toLowerCase();
          const meta = String(item && item.meta ? item.meta : "");
          return !contextId && (role === "user" || role === "assistant") && !meta.includes("workflow_init");
        })
        .slice(-16);
      const lines = scoped.map(function (item, index) {
        const role = String(item && item.role ? item.role : "user").toLowerCase() === "assistant" ? "assistant" : "user";
        return String(index + 1) + ". [" + role + "] " + compactWorkflowLine(item && item.text ? item.text : "", 220);
      });
      const mode = String(flowState && flowState.mode ? flowState.mode : "");
      const goalSeed = String(outlineGuideForm.goal || "").trim();
      const wrapped = [
        "You are the workflow goal-stage judge for a novel project.",
        "Decide if the user's latest message already provides a concrete writing goal.",
        "Output strict JSON only with this schema:",
        "{\"decision\":\"goal_ready|collect_more\",\"goal\":\"...\",\"assistant_reply\":\"...\"}",
        "Rules:",
        "1) decision=goal_ready only if goal is concrete, actionable, and sufficient to enter /sync.",
        "2) If collect_more: ask focused follow-up and optionally provide candidate goal options.",
        "3) If goal_ready: goal must be one concise sentence in user's language.",
        "4) assistant_reply must be user-facing natural text in user's language (no markdown code fence).",
        "",
        "[Workflow Mode]",
        mode || "-",
        "",
        "[Current Goal Draft]",
        goalSeed || "-",
        "",
        "[Conversation History]",
        lines.join("\n") || "-",
        "",
        "[Current User Message]",
        String(message || "")
      ].join("\n");
      return wrapped.slice(0, 3900);
    }

    function parseGoalDecisionReply(rawReply) {
      const raw = String(rawReply || "").trim();
      const candidates = [];
      const fencedMatches = raw.match(/```(?:json)?\s*[\s\S]*?```/gi) || [];
      fencedMatches.forEach(function (block) {
        const cleaned = String(block)
          .replace(/^```(?:json)?\s*/i, "")
          .replace(/```$/i, "")
          .trim();
        if (cleaned) {
          candidates.push(cleaned);
        }
      });
      if (raw) {
        candidates.push(raw);
      }
      const braceMatched = raw.match(/\{[\s\S]*\}/);
      if (braceMatched && String(braceMatched[0] || "").trim()) {
        candidates.push(String(braceMatched[0]).trim());
      }
      let parsed = null;
      for (let index = 0; index < candidates.length; index += 1) {
        try {
          const data = JSON.parse(candidates[index]);
          if (data && typeof data === "object") {
            parsed = data;
            break;
          }
        } catch (error) {
          parsed = null;
        }
      }
      if (!parsed) {
        return {
          decision: "collect_more",
          goal: "",
          assistantReply: raw || t("web.workflow.need_goal")
        };
      }
      const decisionRaw = String(parsed.decision || parsed.next || parsed.state || "").trim().toLowerCase();
      const decision = decisionRaw === "goal_ready" || decisionRaw === "ready" || decisionRaw === "confirm_goal"
        ? "goal_ready"
        : "collect_more";
      const goal = compactWorkflowLine(parsed.goal || parsed.normalized_goal || parsed.goal_summary || "", 320);
      const assistantReply = String(parsed.assistant_reply || parsed.reply || parsed.message || "").trim();
      return {
        decision: decision,
        goal: goal,
        assistantReply: assistantReply || raw || t("web.workflow.need_goal")
      };
    }

    async function materializeWorkflowGraphPlan(flow) {
      if (!projectId) {
        return false;
      }
      const fallbackBeats = parseBeatList(flow.chapter_beats, 8);
      const outlineText = String(flow.outline_markdown || "").trim();
      if (!outlineText && fallbackBeats.length === 0) {
        return false;
      }
      const detailOutcome = await runApiDetailed(
        function () {
          return apiRequest("/api/ai/outline/detail_nodes", {
            method: "POST",
            timeout_ms: aiRequestTimeoutMs(),
            body: {
              project_id: projectId,
              outline_markdown: outlineText,
              chapter_beats: fallbackBeats,
              user_request: String(flow.goal || flow.specify || flow.plan_notes || ""),
              mode: String(flow.mode || ""),
              token_budget: Math.max(1200, Math.floor(asNumber(aiConfig.token_budget, 2200))),
              max_nodes: 8
            }
          });
        },
        null
      );
      const detailNodesRaw =
        detailOutcome.ok && detailOutcome.data && Array.isArray(detailOutcome.data.nodes)
          ? detailOutcome.data.nodes
          : [];
      const detailNodes = detailNodesRaw
        .map(function (item, index) {
          const raw = item && typeof item === "object" ? item : {};
          const title = String(raw.title || "").trim();
          const outline = String(raw.outline_markdown || raw.outline || "").trim();
          const summary = String(raw.summary || "").trim();
          if (!outline) {
            return null;
          }
          return {
            title: title || beatTitle(summary || outline, index),
            outline_markdown: outline,
            summary: summary || outline.replace(/\s+/g, " ").slice(0, 180)
          };
        })
        .filter(function (item) {
          return Boolean(item && item.outline_markdown);
        })
        .slice(0, 8);
      const fallbackDetailNodes = fallbackBeats.map(function (beat, index) {
        const text = String(beat || "").trim();
        return {
          title: beatTitle(text, index),
          outline_markdown: text ? "- " + text : "",
          summary: text.slice(0, 180)
        };
      }).filter(function (item) {
        return Boolean(item.outline_markdown);
      }).slice(0, 8);
      const detailList = detailNodes.length > 0 ? detailNodes : fallbackDetailNodes;
      if (detailList.length === 0) {
        return false;
      }
      const groupWidth = Math.max(920, 340 + detailList.length * 230);
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
                group_width: groupWidth,
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
      for (let index = 0; index < detailList.length; index += 1) {
        const detail = detailList[index];
        const node = await runApi(
          function () {
            return apiRequest("/api/projects/" + projectId + "/nodes", {
              method: "POST",
              body: {
                title: detail.title,
                type: "chapter",
                status: "draft",
                storyline_id: null,
                pos_x: 170 + index * 220,
                pos_y: 220,
                metadata: {
                  group_parent_id: groupNode.id,
                  group_binding: "bound",
                  ai_from_workflow: true,
                  ai_outline_seed_marker: WORKFLOW_OUTLINE_SEED_MARKER,
                  outline_markdown: String(detail.outline_markdown || ""),
                  summary: String(detail.summary || "").slice(0, 180),
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
                ai_outline_seed: true,
                ai_outline_seed_marker: WORKFLOW_OUTLINE_SEED_MARKER,
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
                outline_markdown: outlineText,
                summary: outlineText.slice(0, 200)
              }
            }
          });
        },
        null
      );
      if (!node) {
        return "";
      }
      await refreshProjectData(projectId, true);
      setSelectedNodeId(node.id);
      setSidebarTab("node");
      setChatContextNodeId(node.id);
      setChatOpen(true);
      setArtifactOpen(false);
      pushToast("ok", t("web.outline.saved"));
      return String(node.id || "");
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
          return false;
        }
        setChatWorkflow(function (prev) {
          return Object.assign({}, prev, { mode: mode, step: "goal" });
        });
        appendChatMessage("assistant", t("web.workflow.ask_goal"), t("web.chat.route_label", { route: "workflow" }));
        return true;
      }
      if (step === "goal") {
        const goalDecisionOutcome = await runApiDetailed(
          function () {
            return apiRequest("/api/ai/chat", {
              method: "POST",
              timeout_ms: aiRequestTimeoutMs(),
              body: {
                project_id: projectId,
                node_id: null,
                message: buildGoalDecisionMessage(message, current),
                token_budget: Math.max(900, Math.floor(asNumber(aiConfig.token_budget, 2200) / 2))
              }
            });
          },
          null
        );
        if (!goalDecisionOutcome.ok || !goalDecisionOutcome.data) {
          appendChatMessage(
            "assistant",
            t("web.chat.error_reply", { message: goalDecisionOutcome.error || t("web.workflow.need_goal") }),
            t("web.chat.route_label", { route: "workflow" })
          );
          return true;
        }
        const judged = parseGoalDecisionReply(goalDecisionOutcome.data.reply);
        const resolvedGoal = String(judged.goal || message || "").trim();
        if (judged.decision !== "goal_ready" || resolvedGoal.length < 6) {
          appendChatMessage(
            "assistant",
            String(judged.assistantReply || t("web.workflow.need_goal")),
            t("web.chat.route_label", { route: "workflow" })
          );
          return true;
        }
        setChatWorkflow(function (prev) {
          return Object.assign({}, prev, { step: "sync" });
        });
        setOutlineGuideField("goal", resolvedGoal);
        const ack = String(judged.assistantReply || "").trim();
        appendChatMessage(
          "assistant",
          (ack ? ack + "\n\n" : "") + t("web.workflow.ask_sync"),
          t("web.chat.route_label", { route: "workflow" })
        );
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
        const savedNodeId = await saveWorkflowOutlineNode(flow);
        if (!savedNodeId) {
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
