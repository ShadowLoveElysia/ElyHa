import React, {useEffect, useRef, useState} from 'react';
import {Send, Bot, User, X, Sparkles, MoreHorizontal, PlusCircle, ShieldCheck} from 'lucide-react';
import {cn} from '../utils';
import {
  getAgentSession,
  listAgentSettingProposals,
  reviewAgentSettingProposalsBatch,
  sendAiChat,
  startAgentSession,
  submitAgentDiffReview,
  submitAgentDecision,
} from '../api';
import type {AgentSessionPayload, AiSuggestedOption} from '../types';
import type {TranslationVars} from '../i18n';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  suggestions?: AiSuggestedOption[];
}

interface AIChatProps {
  isOpen: boolean;
  onClose: () => void;
  projectId?: string;
  selectedNodeId?: string;
  onCreateSuggestionNode?: (option: AiSuggestedOption) => Promise<void>;
  onRefreshProject?: () => Promise<void>;
  onStatus?: (text: string, isError?: boolean) => void;
  t: (key: string, vars?: TranslationVars) => string;
}

function errorToText(error: unknown, fallback = 'Unknown error'): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error || fallback);
}

function makeDecisionId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
}

export function AIChat({
  isOpen,
  onClose,
  projectId = '',
  selectedNodeId = '',
  onCreateSuggestionNode,
  onRefreshProject,
  onStatus,
  t,
}: AIChatProps) {
  const bootMessage = t('web.chat.boot_message');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [allowNodeWrite, setAllowNodeWrite] = useState(false);
  const [agentThreadId, setAgentThreadId] = useState('');
  const [agentSession, setAgentSession] = useState<AgentSessionPayload | null>(null);
  const [sessionBusy, setSessionBusy] = useState(false);
  const [correctionInput, setCorrectionInput] = useState('');
  const [persistDirective, setPersistDirective] = useState('');
  const [proposalBusy, setProposalBusy] = useState(false);
  const [proposalQueue, setProposalQueue] = useState<Array<Record<string, unknown>>>([]);
  const [selectedProposalIds, setSelectedProposalIds] = useState<string[]>([]);
  const [deferReviewEnabled, setDeferReviewEnabled] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMessages((prev) => {
      if (prev.length === 0) {
        return [{id: 'boot', role: 'assistant', content: bootMessage}];
      }
      const first = prev[0];
      if (first.id !== 'boot' || first.content === bootMessage) {
        return prev;
      }
      return [{...first, content: bootMessage}, ...prev.slice(1)];
    });
  }, [bootMessage]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({behavior: 'smooth'});
  }, [messages]);

  useEffect(() => {
    if (!agentSession) {
      return;
    }
    if (agentSession.status === 'AWAITING_SETTING_PROPOSAL_CONFIRM') {
      void loadProposalQueue();
    }
  }, [agentSession?.status]);

  const appendMessage = (message: ChatMessage) => {
    setMessages((prev) => [...prev, message]);
  };

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    const message = input.trim();
    if (!message || busy) {
      return;
    }
    if (!projectId) {
      appendMessage({
        id: `${Date.now()}-warn`,
        role: 'system',
        content: t('web.chat.project_required'),
      });
      return;
    }

    appendMessage({id: `${Date.now()}-user`, role: 'user', content: message});
    setInput('');
    setBusy(true);

    try {
      const response = await sendAiChat({
        project_id: projectId,
        message,
        node_id: allowNodeWrite && selectedNodeId ? selectedNodeId : undefined,
        token_budget: 1800,
      });

      appendMessage({
        id: `${Date.now()}-assistant`,
        role: 'assistant',
        content: response.reply || t('web.chat.empty_reply'),
        suggestions: response.suggested_options || [],
      });

      if (response.updated_node_id) {
        onStatus?.(t('web.toast.ai_node_updated', {node: response.updated_node_id}), false);
        if (onRefreshProject) {
          await onRefreshProject();
        }
      }
    } catch (error) {
      const text = errorToText(error, t('web.error.unknown'));
      appendMessage({
        id: `${Date.now()}-error`,
        role: 'system',
        content: t('web.chat.request_failed', {message: text}),
      });
      onStatus?.(text, true);
    } finally {
      setBusy(false);
    }
  };

  const adoptSuggestion = async (option: AiSuggestedOption) => {
    if (!onCreateSuggestionNode) {
      return;
    }
    try {
      await onCreateSuggestionNode(option);
      onStatus?.(t('web.chat.suggestion_adopted', {title: option.title || t('web.node.untitled')}), false);
    } catch (error) {
      onStatus?.(t('web.chat.suggestion_create_failed', {message: errorToText(error, t('web.error.unknown'))}), true);
    }
  };

  const applySessionPayload = (payload: {thread_id: string; session: AgentSessionPayload}) => {
    const cleanThreadId = String(payload.thread_id || '').trim();
    if (cleanThreadId) {
      setAgentThreadId(cleanThreadId);
    }
    setAgentSession(payload.session || null);
  };

  const startSession = async () => {
    if (!projectId) {
      onStatus?.(t('web.chat.project_required'), true);
      return;
    }
    if (!selectedNodeId) {
      onStatus?.('selected node required', true);
      return;
    }
    setSessionBusy(true);
    try {
      const payload = await startAgentSession({
        project_id: projectId,
        node_id: selectedNodeId,
        mode: 'single_agent',
        token_budget: 2200,
        thread_id: agentThreadId.trim() || undefined,
      });
      applySessionPayload(payload);
      onStatus?.(`agent session started: ${payload.thread_id}`, false);
      if (onRefreshProject) {
        await onRefreshProject();
      }
    } catch (error) {
      onStatus?.(errorToText(error, t('web.error.unknown')), true);
    } finally {
      setSessionBusy(false);
    }
  };

  const refreshSession = async () => {
    const threadId = agentThreadId.trim();
    if (!threadId) {
      onStatus?.('agent thread_id required', true);
      return;
    }
    setSessionBusy(true);
    try {
      const payload = await getAgentSession(threadId);
      applySessionPayload(payload);
      onStatus?.(`session status: ${payload.session.status}`, false);
    } catch (error) {
      onStatus?.(errorToText(error, t('web.error.unknown')), true);
    } finally {
      setSessionBusy(false);
    }
  };

  const submitSessionDecision = async (action: string, payload: Record<string, unknown> = {}) => {
    const threadId = agentThreadId.trim();
    if (!threadId) {
      onStatus?.('agent thread_id required', true);
      return;
    }
    setSessionBusy(true);
    try {
      const response = await submitAgentDecision({
        thread_id: threadId,
        action,
        decision_id: makeDecisionId('d-ui'),
        expected_state_version: agentSession?.state_version,
        payload,
      });
      applySessionPayload(response);
      onStatus?.(`decision applied: ${action} -> ${response.session.status}`, false);
      if (response.session.status === 'AWAITING_SETTING_PROPOSAL_CONFIRM') {
        void loadProposalQueue();
      }
      if (action === 'confirm_yes' || action === 'confirm_yes_persist_rule' || action === 'satisfied') {
        if (onRefreshProject) {
          await onRefreshProject();
        }
      }
    } catch (error) {
      onStatus?.(errorToText(error, t('web.error.unknown')), true);
    } finally {
      setSessionBusy(false);
    }
  };

  const applyDiffReview = async (rejectAll: boolean) => {
    const threadId = agentThreadId.trim();
    if (!threadId) {
      onStatus?.('agent thread_id required', true);
      return;
    }
    if (!agentSession) {
      onStatus?.('session not loaded', true);
      return;
    }
    const pendingMeta = asRecord(agentSession.pending_meta);
    const diffPatch = asRecord(pendingMeta.diff_patch);
    const diffId = String(diffPatch.diff_id || '').trim();
    if (!diffId) {
      onStatus?.('diff_patch missing', true);
      return;
    }
    const hunks = Array.isArray(diffPatch.hunks)
      ? diffPatch.hunks.map((item) => asRecord(item))
      : [];
    const allHunkIds = hunks
      .map((item) => String(item.hunk_id || '').trim())
      .filter(Boolean);
    setSessionBusy(true);
    try {
      const payload = await submitAgentDiffReview({
        thread_id: threadId,
        diff_id: diffId,
        decision_id: makeDecisionId('d-diff'),
        expected_base_revision: Number(diffPatch.base_revision || 0),
        expected_base_hash: String(diffPatch.base_content_hash || ''),
        expected_state_version: agentSession.state_version,
        accepted_hunk_ids: rejectAll ? [] : allHunkIds,
        rejected_hunk_ids: rejectAll ? allHunkIds : [],
      });
      applySessionPayload(payload);
      onStatus?.(
        rejectAll ? 'diff review done: rejected all hunks' : 'diff review done: applied selected hunks',
        false,
      );
    } catch (error) {
      onStatus?.(errorToText(error, t('web.error.unknown')), true);
    } finally {
      setSessionBusy(false);
    }
  };

  const loadProposalQueue = async () => {
    const threadId = (agentThreadId || agentSession?.thread_id || '').trim();
    if (!threadId) {
      onStatus?.('agent thread_id required', true);
      return;
    }
    setProposalBusy(true);
    try {
      const payload = await listAgentSettingProposals(threadId, 'pending_review');
      setProposalQueue(payload.setting_proposals || []);
      const ids = (payload.setting_proposals || [])
        .map((item) => String(item.id || '').trim())
        .filter(Boolean);
      setSelectedProposalIds(ids);
      onStatus?.(`pending proposals: ${payload.count}`, false);
    } catch (error) {
      onStatus?.(errorToText(error, t('web.error.unknown')), true);
    } finally {
      setProposalBusy(false);
    }
  };

  const reviewProposalBatch = async (action: 'approve' | 'reject') => {
    const threadId = (agentThreadId || agentSession?.thread_id || '').trim();
    if (!threadId) {
      onStatus?.('agent thread_id required', true);
      return;
    }
    if (selectedProposalIds.length === 0) {
      onStatus?.('no proposal selected', true);
      return;
    }
    setProposalBusy(true);
    try {
      const payload = await reviewAgentSettingProposalsBatch({
        thread_id: threadId,
        action,
        proposal_ids: selectedProposalIds,
        decision_id: makeDecisionId('d-batch'),
        expected_state_version: agentSession?.state_version,
      });
      applySessionPayload(payload);
      await loadProposalQueue();
      onStatus?.(`batch ${action} done: ${selectedProposalIds.length}`, false);
    } catch (error) {
      onStatus?.(errorToText(error, t('web.error.unknown')), true);
    } finally {
      setProposalBusy(false);
    }
  };

  const deferCurrentProposal = async () => {
    const threadId = (agentThreadId || agentSession?.thread_id || '').trim();
    if (!threadId) {
      onStatus?.('agent thread_id required', true);
      return;
    }
    await submitSessionDecision('defer_setting_update');
    void loadProposalQueue();
  };

  const toggleProposalSelected = (proposalId: string, checked: boolean) => {
    setSelectedProposalIds((prev) => {
      const clean = proposalId.trim();
      if (!clean) {
        return prev;
      }
      if (checked) {
        if (prev.includes(clean)) {
          return prev;
        }
        return [...prev, clean];
      }
      return prev.filter((item) => item !== clean);
    });
  };

  const sessionPendingMeta = asRecord(agentSession?.pending_meta);
  const sessionDiffPatch = asRecord(sessionPendingMeta.diff_patch);
  const sessionDiffHunks = Array.isArray(sessionDiffPatch.hunks)
    ? sessionDiffPatch.hunks.map((item) => asRecord(item)).filter((item) => String(item.hunk_id || '').trim())
    : [];
  const sessionStatus = String(agentSession?.status || '').trim();
  const pendingStateUpdateCount = Number(agentSession?.pending_state_update_count || 0);

  return (
    <div
      className={cn(
        'fixed inset-y-0 right-0 w-96 bg-white border-l border-slate-200 shadow-2xl flex flex-col transform transition-transform duration-300 ease-in-out z-50',
        isOpen ? 'translate-x-0' : 'translate-x-full',
      )}
    >
      <div className="h-14 border-b border-slate-200 flex items-center justify-between px-4 shrink-0 bg-white/95 backdrop-blur">
        <div className="flex items-center gap-2 text-slate-800">
          <Sparkles size={18} className="text-pink-500" />
          <span className="font-bold">{t('web.chat.drawer_title')}</span>
        </div>
        <div className="flex items-center gap-2">
          <button className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-md transition-colors">
            <MoreHorizontal size={18} />
          </button>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-md transition-colors"
          >
            <X size={18} />
          </button>
        </div>
      </div>

      <div className="px-4 py-2 border-b border-slate-100 bg-slate-50 text-xs text-slate-600">
        <div className="flex items-center justify-between gap-3">
          <span className="truncate">{t('web.chat.project_label', {project: projectId || t('web.top.project_unselected')})}</span>
          <label className="flex items-center gap-1.5 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={allowNodeWrite}
              onChange={(event) => setAllowNodeWrite(event.target.checked)}
            />
            <span className="inline-flex items-center gap-1">
              <ShieldCheck size={12} />
              {t('web.chat.allow_node_write')}
            </span>
          </label>
        </div>
      </div>

      <div className="px-4 py-2 border-b border-slate-100 bg-slate-50/70 text-[11px] text-slate-600 space-y-2">
        <div className="flex items-center gap-2">
          <input
            value={agentThreadId}
            onChange={(event) => setAgentThreadId(event.target.value)}
            placeholder="agent thread_id"
            className="flex-1 h-8 rounded-md border border-slate-200 bg-white px-2 text-xs"
          />
          <button
            onClick={() => void refreshSession()}
            disabled={sessionBusy || !agentThreadId.trim()}
            className="h-8 px-2 rounded-md border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-60"
          >
            Refresh
          </button>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => void startSession()}
            disabled={sessionBusy || !projectId || !selectedNodeId}
            className="h-8 px-3 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-200 hover:bg-indigo-100 disabled:opacity-60"
          >
            Start Session
          </button>
          <button
            onClick={() => void loadProposalQueue()}
            disabled={proposalBusy || !agentThreadId.trim()}
            className="h-8 px-3 rounded-md border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-60"
          >
            Load Proposals
          </button>
        </div>

        <div className="rounded-md border border-slate-200 bg-white p-2 text-[11px]">
          {agentSession ? (
            <div className="space-y-1">
              <div>
                status=<span className="font-semibold text-slate-800">{agentSession.status}</span>, version=
                {agentSession.state_version}
              </div>
              <div>
                pending_content_chars={String(agentSession.pending_content || '').length}, pending_state_update=
                {pendingStateUpdateCount}
              </div>
              <div>latest_setting_proposal_id={agentSession.latest_setting_proposal_id || '-'}</div>
            </div>
          ) : (
            <div className="text-slate-400">Session not loaded.</div>
          )}
        </div>

        <input
          value={correctionInput}
          onChange={(event) => setCorrectionInput(event.target.value)}
          placeholder="correction / unsatisfied note"
          className="w-full h-8 rounded-md border border-slate-200 bg-white px-2 text-xs"
        />
        <input
          value={persistDirective}
          onChange={(event) => setPersistDirective(event.target.value)}
          placeholder="directive for confirm_yes_persist_rule"
          className="w-full h-8 rounded-md border border-slate-200 bg-white px-2 text-xs"
        />

        {(sessionStatus === 'AWAITING_CONFIRM' || sessionStatus === 'AWAITING_CORRECTION_CONFIRM') && (
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => void submitSessionDecision('confirm_yes')}
              disabled={sessionBusy || !agentThreadId.trim()}
              className="h-8 px-3 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 disabled:opacity-60"
            >
              Confirm Yes
            </button>
            <button
              onClick={() =>
                void submitSessionDecision('confirm_yes_persist_rule', {directive: persistDirective.trim()})
              }
              disabled={sessionBusy || !agentThreadId.trim() || !persistDirective.trim()}
              className="h-8 px-3 rounded-md bg-cyan-50 text-cyan-700 border border-cyan-200 hover:bg-cyan-100 disabled:opacity-60"
            >
              Confirm + Persist
            </button>
            <button
              onClick={() =>
                void submitSessionDecision('correct', {
                  correction: correctionInput.trim() || '请继续修订并提高一致性。',
                })
              }
              disabled={sessionBusy || !agentThreadId.trim()}
              className="h-8 px-3 rounded-md bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100 disabled:opacity-60"
            >
              Correct
            </button>
            <button
              onClick={() => void submitSessionDecision('stop')}
              disabled={sessionBusy || !agentThreadId.trim()}
              className="h-8 px-3 rounded-md bg-rose-50 text-rose-700 border border-rose-200 hover:bg-rose-100 disabled:opacity-60"
            >
              Stop
            </button>
          </div>
        )}

        {sessionStatus === 'AWAITING_CHAPTER_REVIEW' && (
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => void submitSessionDecision('satisfied')}
              disabled={sessionBusy || !agentThreadId.trim()}
              className="h-8 px-3 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 disabled:opacity-60"
            >
              Chapter Satisfied
            </button>
            <button
              onClick={() =>
                void submitSessionDecision('unsatisfied', {
                  correction: correctionInput.trim() || '继续修订章节完成度。',
                })
              }
              disabled={sessionBusy || !agentThreadId.trim()}
              className="h-8 px-3 rounded-md bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100 disabled:opacity-60"
            >
              Chapter Unsatisfied
            </button>
          </div>
        )}

        {sessionStatus === 'AWAITING_SETTING_PROPOSAL_CONFIRM' && (
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() =>
                void submitSessionDecision('approve_setting_update', {
                  proposal_id: agentSession?.latest_setting_proposal_id || '',
                })
              }
              disabled={sessionBusy || !agentThreadId.trim()}
              className="h-8 px-3 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 disabled:opacity-60"
            >
              Approve Proposal
            </button>
            <button
              onClick={() =>
                void submitSessionDecision('reject_setting_update', {
                  proposal_id: agentSession?.latest_setting_proposal_id || '',
                })
              }
              disabled={sessionBusy || !agentThreadId.trim()}
              className="h-8 px-3 rounded-md bg-rose-50 text-rose-700 border border-rose-200 hover:bg-rose-100 disabled:opacity-60"
            >
              Reject Proposal
            </button>
            <button
              onClick={() => void deferCurrentProposal()}
              disabled={sessionBusy || !agentThreadId.trim() || !deferReviewEnabled}
              className="h-8 px-3 rounded-md border border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100 disabled:opacity-60"
            >
              Defer Current
            </button>
          </div>
        )}

        {sessionStatus === 'AWAITING_CORRECTION_CONFIRM' && sessionDiffHunks.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-slate-500">Diff hunks: {sessionDiffHunks.length}</span>
            <button
              onClick={() => void applyDiffReview(false)}
              disabled={sessionBusy || !agentThreadId.trim()}
              className="h-8 px-3 rounded-md bg-violet-50 text-violet-700 border border-violet-200 hover:bg-violet-100 disabled:opacity-60"
            >
              Apply Diff Hunks
            </button>
            <button
              onClick={() => void applyDiffReview(true)}
              disabled={sessionBusy || !agentThreadId.trim()}
              className="h-8 px-3 rounded-md bg-slate-100 text-slate-700 border border-slate-200 hover:bg-slate-200 disabled:opacity-60"
            >
              Reject All Hunks
            </button>
          </div>
        )}

        <div className="flex items-center justify-between">
          <label className="inline-flex items-center gap-1">
            <input
              type="checkbox"
              checked={deferReviewEnabled}
              onChange={(event) => setDeferReviewEnabled(event.target.checked)}
            />
            <span>Enable defer-review shortcut</span>
          </label>
        </div>

        {proposalQueue.length > 0 ? (
          <div className="space-y-1 max-h-28 overflow-y-auto rounded-md border border-slate-200 bg-white p-2">
            {proposalQueue.map((proposal) => {
              const proposalId = String(proposal.id || '').trim();
              const checked = selectedProposalIds.includes(proposalId);
              const proposalType = String(proposal.proposal_type || '');
              const proposalStatus = String(proposal.status || '');
              return (
                <label key={proposalId} className="flex items-center gap-2 text-[11px]">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(event) => toggleProposalSelected(proposalId, event.target.checked)}
                  />
                  <span className="truncate">
                    {proposalId} [{proposalType || 'unknown'} / {proposalStatus || 'pending'}]
                  </span>
                </label>
              );
            })}
          </div>
        ) : (
          <div className="text-slate-400">No pending setting proposals.</div>
        )}

        <div className="flex items-center gap-2">
          <button
            onClick={() => void reviewProposalBatch('approve')}
            disabled={proposalBusy || selectedProposalIds.length === 0}
            className="h-8 px-3 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 disabled:opacity-60"
          >
            Approve Selected
          </button>
          <button
            onClick={() => void reviewProposalBatch('reject')}
            disabled={proposalBusy || selectedProposalIds.length === 0}
            className="h-8 px-3 rounded-md bg-rose-50 text-rose-700 border border-rose-200 hover:bg-rose-100 disabled:opacity-60"
          >
            Reject Selected
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {messages.map((msg) => (
          <div key={msg.id} className={cn('flex gap-3', msg.role === 'user' ? 'flex-row-reverse' : 'flex-row')}>
            <div
              className={cn(
                'w-8 h-8 rounded-full flex items-center justify-center shrink-0 shadow-sm',
                msg.role === 'user'
                  ? 'bg-slate-100 text-slate-600 border border-slate-200'
                  : msg.role === 'assistant'
                    ? 'bg-pink-500 text-white'
                    : 'bg-amber-100 text-amber-700 border border-amber-200',
              )}
            >
              {msg.role === 'user' ? <User size={16} /> : <Bot size={16} />}
            </div>
            <div className="max-w-[80%] space-y-2">
              <div
                className={cn(
                  'rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm',
                  msg.role === 'user'
                    ? 'bg-slate-100 text-slate-800 rounded-tr-sm border border-slate-200/50'
                    : msg.role === 'assistant'
                      ? 'bg-pink-50 text-pink-900 border border-pink-100 rounded-tl-sm'
                      : 'bg-amber-50 text-amber-900 border border-amber-200 rounded-tl-sm',
                )}
              >
                {msg.content}
              </div>

              {msg.suggestions && msg.suggestions.length > 0 ? (
                <div className="space-y-2">
                  {msg.suggestions.map((option, idx) => (
                    <div key={`${msg.id}-${idx}`} className="rounded-xl border border-slate-200 bg-white p-3 text-xs shadow-sm">
                      <div className="font-semibold text-slate-800">{option.title || t('web.chat.suggestion_index_title', {index: idx + 1})}</div>
                      <div className="text-slate-600 mt-1 whitespace-pre-wrap">
                        {option.summary || option.description || option.outline_steps || t('web.chat.no_summary')}
                      </div>
                      <button
                        onClick={() => void adoptSuggestion(option)}
                        className="mt-2 inline-flex items-center gap-1 rounded-md bg-emerald-50 text-emerald-700 px-2.5 py-1.5 text-xs font-semibold hover:bg-emerald-100"
                      >
                        <PlusCircle size={13} />
                        {t('web.chat.create_suggestion_node')}
                      </button>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="p-4 border-t border-slate-200 bg-white">
        <form onSubmit={(event) => void handleSend(event)} className="relative flex items-end gap-2">
          <div className="relative flex-1">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder={projectId ? t('web.chat.input_placeholder') : t('web.chat.project_required')}
              disabled={!projectId || busy}
              className="w-full bg-slate-50 border border-slate-200 rounded-xl py-3 pl-4 pr-12 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-pink-500 focus:border-transparent resize-none min-h-[44px] max-h-32 shadow-inner disabled:opacity-60"
              rows={1}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void handleSend(event);
                }
              }}
            />
            <button
              type="submit"
              disabled={!input.trim() || !projectId || busy}
              className="absolute right-2 bottom-2 p-1.5 bg-pink-500 text-white rounded-lg hover:bg-pink-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
            >
              <Send size={16} />
            </button>
          </div>
        </form>
        <div className="mt-2 flex items-center justify-between text-[10px] text-slate-400 font-medium">
          <span>{t('web.chat.shift_enter_hint')}</span>
          <span>{busy ? t('web.chat.processing') : t('web.chat.endpoint_hint')}</span>
        </div>
      </div>
    </div>
  );
}
