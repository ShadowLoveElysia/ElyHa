import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {Send, Bot, User, X, Sparkles, PlusCircle, ShieldCheck, Trash2} from 'lucide-react';
import {cn} from '../utils';
import {
  ApiTimeoutError,
  getAgentSession,
  getProjectChatThreadMessages,
  listAgentSettingProposals,
  listProjectChatThreads,
  reviewAgentSettingProposalsBatch,
  sendAiChat,
  startAgentSession,
  submitAgentDiffReview,
  submitAgentDecision,
} from '../api';
import type {AgentSessionPayload, AiSuggestedOption, ChatMessagePayload, ChatThreadSummary} from '../types';
import type {TranslationVars} from '../i18n';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  suggestions?: AiSuggestedOption[];
}

interface GuideDocStatusItem {
  key: string;
  title: string;
  filled: boolean;
}

interface AIChatProps {
  isOpen: boolean;
  onClose: () => void;
  projectId?: string;
  selectedNodeId?: string;
  resetVersion?: number;
  fullScreen?: boolean;
  guideMode?: boolean;
  guideDocStatus?: GuideDocStatusItem[];
  onGuideDocReply?: (reply: string) => Promise<void>;
  onGuideSkipDocumentRequest?: (docType: string) => Promise<boolean>;
  onCreateSuggestionNode?: (option: AiSuggestedOption) => Promise<void>;
  onRefreshProject?: () => Promise<void>;
  onStatus?: (text: string, isError?: boolean) => void;
  t: (key: string, vars?: TranslationVars) => string;
}

interface ChatWindowRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface DragState {
  startX: number;
  startY: number;
  originX: number;
  originY: number;
}

interface ResizeState {
  startX: number;
  startY: number;
  originWidth: number;
  originHeight: number;
}

const CHAT_MIN_WIDTH = 360;
const CHAT_MIN_HEIGHT = 420;
const CHAT_MARGIN = 12;
const CHAT_MIN_TOP = 56;
const LAST_CHAT_THREAD_STORAGE_KEY = 'elyha.chat.last_thread_by_project.v1';

function clampNumber(value: number, min: number, max: number): number {
  if (max <= min) {
    return min;
  }
  return Math.min(max, Math.max(min, value));
}

function readViewportSize(): {width: number; height: number} {
  if (typeof window === 'undefined') {
    return {width: 1400, height: 900};
  }
  return {width: window.innerWidth, height: window.innerHeight};
}

function getDefaultChatRect(): ChatWindowRect {
  const viewport = readViewportSize();
  const width = Math.round(Math.min(560, Math.max(420, viewport.width * 0.34)));
  const height = Math.round(Math.min(820, Math.max(520, viewport.height * 0.78)));
  return {
    x: Math.max(CHAT_MARGIN, viewport.width - width - 20),
    y: Math.max(CHAT_MIN_TOP, Math.round(viewport.height * 0.08)),
    width,
    height,
  };
}

function errorToText(
  error: unknown,
  t: (key: string, vars?: TranslationVars) => string,
  fallback: string,
): string {
  if (error instanceof ApiTimeoutError) {
    return t('web.error.request_timeout', {seconds: error.timeoutSeconds});
  }
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

function getLastThreadForProject(projectId: string): string {
  const cleanProject = String(projectId || '').trim();
  if (!cleanProject || typeof window === 'undefined') {
    return '';
  }
  try {
    const raw = window.localStorage.getItem(LAST_CHAT_THREAD_STORAGE_KEY);
    if (!raw) {
      return '';
    }
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return '';
    }
    const value = String((parsed as Record<string, unknown>)[cleanProject] || '').trim();
    return value;
  } catch {
    return '';
  }
}

function setLastThreadForProject(projectId: string, threadId: string): void {
  const cleanProject = String(projectId || '').trim();
  const cleanThread = String(threadId || '').trim();
  if (!cleanProject || !cleanThread || typeof window === 'undefined') {
    return;
  }
  try {
    const raw = window.localStorage.getItem(LAST_CHAT_THREAD_STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : {};
    const base =
      parsed && typeof parsed === 'object' && !Array.isArray(parsed)
        ? (parsed as Record<string, unknown>)
        : {};
    const next: Record<string, string> = {};
    for (const [key, value] of Object.entries(base)) {
      const cleanKey = String(key || '').trim();
      const cleanValue = String(value || '').trim();
      if (cleanKey && cleanValue) {
        next[cleanKey] = cleanValue;
      }
    }
    next[cleanProject] = cleanThread;
    window.localStorage.setItem(LAST_CHAT_THREAD_STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Ignore storage errors and continue with in-memory session.
  }
}

function clearLastThreadForProject(projectId: string): void {
  const cleanProject = String(projectId || '').trim();
  if (!cleanProject || typeof window === 'undefined') {
    return;
  }
  try {
    const raw = window.localStorage.getItem(LAST_CHAT_THREAD_STORAGE_KEY);
    if (!raw) {
      return;
    }
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return;
    }
    const next: Record<string, string> = {};
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      const cleanKey = String(key || '').trim();
      const cleanValue = String(value || '').trim();
      if (!cleanKey || !cleanValue || cleanKey === cleanProject) {
        continue;
      }
      next[cleanKey] = cleanValue;
    }
    window.localStorage.setItem(LAST_CHAT_THREAD_STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Ignore storage errors and continue with in-memory session.
  }
}

export function AIChat({
  isOpen,
  onClose,
  projectId = '',
  selectedNodeId = '',
  resetVersion,
  fullScreen = false,
  guideMode = false,
  guideDocStatus = [],
  onGuideDocReply,
  onGuideSkipDocumentRequest,
  onCreateSuggestionNode,
  onRefreshProject,
  onStatus,
  t,
}: AIChatProps) {
  const bootMessage = guideMode ? t('web.chat.guide_boot_message') : t('web.chat.boot_message');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [chatThreadId, setChatThreadId] = useState('');
  const [chatThreadProjectId, setChatThreadProjectId] = useState('');
  const [chatThreads, setChatThreads] = useState<ChatThreadSummary[]>([]);
  const [threadsBusy, setThreadsBusy] = useState(false);
  const [restoringThread, setRestoringThread] = useState(false);
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
  const [windowRect, setWindowRect] = useState<ChatWindowRect>(() => getDefaultChatRect());

  const dragStateRef = useRef<DragState | null>(null);
  const resizeStateRef = useRef<ResizeState | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatThreadIdRef = useRef('');
  const chatThreadProjectIdRef = useRef('');

  const clampWindowRect = useCallback((next: ChatWindowRect): ChatWindowRect => {
    const viewport = readViewportSize();
    const maxWidth = Math.max(240, viewport.width - CHAT_MARGIN * 2);
    const maxHeight = Math.max(260, viewport.height - CHAT_MARGIN * 2);
    const minWidth = Math.min(CHAT_MIN_WIDTH, maxWidth);
    const minHeight = Math.min(CHAT_MIN_HEIGHT, maxHeight);

    const width = clampNumber(next.width, minWidth, maxWidth);
    const height = clampNumber(next.height, minHeight, maxHeight);
    const maxX = Math.max(CHAT_MARGIN, viewport.width - width - CHAT_MARGIN);
    const maxY = Math.max(CHAT_MIN_TOP, viewport.height - height - CHAT_MARGIN);

    return {
      x: clampNumber(next.x, CHAT_MARGIN, maxX),
      y: clampNumber(next.y, CHAT_MIN_TOP, maxY),
      width,
      height,
    };
  }, []);

  const contentScale = useMemo(() => {
    if (fullScreen) {
      return 1;
    }
    const widthScale = windowRect.width / 460;
    const heightScale = windowRect.height / 760;
    return clampNumber(Math.min(widthScale, heightScale), 0.82, 1.08);
  }, [fullScreen, windowRect.height, windowRect.width]);

  const handlePointerMove = useCallback(
    (event: PointerEvent) => {
      if (dragStateRef.current) {
        const drag = dragStateRef.current;
        const nextX = drag.originX + (event.clientX - drag.startX);
        const nextY = drag.originY + (event.clientY - drag.startY);
        setWindowRect((prev) => clampWindowRect({...prev, x: nextX, y: nextY}));
        return;
      }
      if (resizeStateRef.current) {
        const resize = resizeStateRef.current;
        const nextWidth = resize.originWidth + (event.clientX - resize.startX);
        const nextHeight = resize.originHeight + (event.clientY - resize.startY);
        setWindowRect((prev) => clampWindowRect({...prev, width: nextWidth, height: nextHeight}));
      }
    },
    [clampWindowRect],
  );

  const stopPointerInteraction = useCallback(() => {
    dragStateRef.current = null;
    resizeStateRef.current = null;
    window.removeEventListener('pointermove', handlePointerMove);
    window.removeEventListener('pointerup', stopPointerInteraction);
  }, [handlePointerMove]);

  const beginPointerInteraction = useCallback(() => {
    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', stopPointerInteraction);
  }, [handlePointerMove, stopPointerInteraction]);

  const startDrag = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (fullScreen) {
        return;
      }
      if (event.pointerType === 'mouse' && event.button !== 0) {
        return;
      }
      const target = event.target as HTMLElement;
      if (target.closest('[data-chat-no-drag="true"]')) {
        return;
      }
      event.preventDefault();
      stopPointerInteraction();
      dragStateRef.current = {
        startX: event.clientX,
        startY: event.clientY,
        originX: windowRect.x,
        originY: windowRect.y,
      };
      beginPointerInteraction();
    },
    [beginPointerInteraction, fullScreen, stopPointerInteraction, windowRect.x, windowRect.y],
  );

  const startResize = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (fullScreen) {
        return;
      }
      if (event.pointerType === 'mouse' && event.button !== 0) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      stopPointerInteraction();
      resizeStateRef.current = {
        startX: event.clientX,
        startY: event.clientY,
        originWidth: windowRect.width,
        originHeight: windowRect.height,
      };
      beginPointerInteraction();
    },
    [beginPointerInteraction, fullScreen, stopPointerInteraction, windowRect.height, windowRect.width],
  );

  const lastResetVersionRef = useRef<number | undefined>(resetVersion);
  const guideKickoffRef = useRef('');

  const previewThreadLabel = useCallback(
    (item: ChatThreadSummary): string => {
      const cleanId = String(item.thread_id || '').trim();
      const suffix = cleanId ? cleanId.slice(-8) : '';
      const count = Math.max(0, Number(item.message_count || 0));
      const raw = String(item.last_content || '').replace(/\s+/g, ' ').trim();
      const preview = raw ? raw.slice(0, 28) : t('web.chat.thread_preview_empty');
      return `${suffix || '-'} · ${count}${t('web.chat.thread_count_suffix')} · ${preview}`;
    },
    [t],
  );

  const toChatMessages = useCallback(
    (rows: ChatMessagePayload[]): ChatMessage[] => {
      const normalized = (rows || [])
        .map((item, index) => {
          const roleRaw = String(item.role || '').trim().toLowerCase();
          const role: ChatMessage['role'] =
            roleRaw === 'assistant' ? 'assistant' : roleRaw === 'user' ? 'user' : 'system';
          return {
            id: `${String(item.created_at || '')}-${index}`,
            role,
            content: String(item.content || '').trim(),
          };
        })
        .filter((item) => item.content);
      if (normalized.length > 0) {
        return normalized;
      }
      return [{id: 'boot', role: 'assistant', content: bootMessage}];
    },
    [bootMessage],
  );

  const activeChatThreadId = useMemo(() => {
    const cleanThread = String(chatThreadId || '').trim();
    const cleanOwnerProject = String(chatThreadProjectId || '').trim();
    const cleanCurrentProject = String(projectId || '').trim();
    if (!cleanThread || !cleanOwnerProject || !cleanCurrentProject) {
      return '';
    }
    if (cleanOwnerProject !== cleanCurrentProject) {
      return '';
    }
    return cleanThread;
  }, [chatThreadId, chatThreadProjectId, projectId]);

  const refreshChatThreads = useCallback(
    async (nextThreadId = ''): Promise<ChatThreadSummary[]> => {
      const cleanProject = String(projectId || '').trim();
      if (!cleanProject) {
        setChatThreads([]);
        return [];
      }
      setThreadsBusy(true);
      try {
        const payload = await listProjectChatThreads(cleanProject, 80);
        const rows = Array.isArray(payload.threads) ? payload.threads : [];
        setChatThreads(rows);
        const target = String(nextThreadId || '').trim();
        if (!target) {
          return rows;
        }
        if (!rows.some((item) => String(item.thread_id || '').trim() === target)) {
          setChatThreadId('');
          setChatThreadProjectId('');
          clearLastThreadForProject(cleanProject);
          return rows;
        }
        setChatThreadProjectId(cleanProject);
        return rows;
      } catch (error) {
        const text = errorToText(error, t, t('web.error.unknown'));
        onStatus?.(t('web.chat.thread_list_failed', {message: text}), true);
        return [];
      } finally {
        setThreadsBusy(false);
      }
    },
    [onStatus, projectId, t],
  );

  const loadThreadMessages = useCallback(
    async (threadId: string): Promise<void> => {
      const cleanProject = String(projectId || '').trim();
      const cleanThread = String(threadId || '').trim();
      if (!cleanProject || !cleanThread) {
        setMessages([{id: 'boot', role: 'assistant', content: bootMessage}]);
        return;
      }
      setBusy(true);
      try {
        const payload = await getProjectChatThreadMessages(cleanProject, cleanThread, 120);
        setMessages(toChatMessages(payload.messages || []));
      } catch (error) {
        const text = errorToText(error, t, t('web.error.unknown'));
        setMessages([{id: 'boot', role: 'assistant', content: bootMessage}]);
        onStatus?.(t('web.chat.thread_load_failed', {message: text}), true);
      } finally {
        setBusy(false);
      }
    },
    [bootMessage, onStatus, projectId, t, toChatMessages],
  );

  const clearCurrentSession = useCallback(
    (notify = true) => {
      setMessages([{id: 'boot', role: 'assistant', content: bootMessage}]);
      setInput('');
      setBusy(false);
      setChatThreadId('');
      setChatThreadProjectId('');
      setAllowNodeWrite(false);
      setAgentThreadId('');
      setAgentSession(null);
      setSessionBusy(false);
      setCorrectionInput('');
      setPersistDirective('');
      setProposalBusy(false);
      setProposalQueue([]);
      setSelectedProposalIds([]);
      if (guideMode) {
        guideKickoffRef.current = '';
      }
      if (notify) {
        onStatus?.(t('web.chat.session_cleared'), false);
      }
    },
    [bootMessage, guideMode, onStatus, t],
  );

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
    chatThreadIdRef.current = String(chatThreadId || '').trim();
  }, [chatThreadId]);

  useEffect(() => {
    chatThreadProjectIdRef.current = String(chatThreadProjectId || '').trim();
  }, [chatThreadProjectId]);

  useEffect(() => {
    if (!agentSession) {
      return;
    }
    if (agentSession.status === 'AWAITING_SETTING_PROPOSAL_CONFIRM') {
      void loadProposalQueue();
    }
  }, [agentSession?.status]);

  useEffect(() => {
    return () => {
      stopPointerInteraction();
    };
  }, [stopPointerInteraction]);

  useEffect(() => {
    if (fullScreen) {
      return;
    }
    const onResize = () => {
      setWindowRect((prev) => clampWindowRect(prev));
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [clampWindowRect, fullScreen]);

  useEffect(() => {
    if (fullScreen) {
      return;
    }
    if (!isOpen) {
      return;
    }
    setWindowRect((prev) => clampWindowRect(prev));
  }, [clampWindowRect, fullScreen, isOpen]);

  useEffect(() => {
    if (resetVersion === undefined) {
      return;
    }
    if (lastResetVersionRef.current === resetVersion) {
      return;
    }
    lastResetVersionRef.current = resetVersion;
    clearCurrentSession(true);
  }, [clearCurrentSession, resetVersion]);

  useEffect(() => {
    if (!projectId) {
      setChatThreads([]);
      setChatThreadId('');
      setChatThreadProjectId('');
      setMessages([{id: 'boot', role: 'assistant', content: bootMessage}]);
      setInput('');
      return;
    }
    setChatThreads([]);
    setChatThreadId('');
    setChatThreadProjectId('');
    setMessages([{id: 'boot', role: 'assistant', content: bootMessage}]);
    setInput('');
    setAllowNodeWrite(false);
    setAgentThreadId('');
    setAgentSession(null);
    setCorrectionInput('');
    setPersistDirective('');
    setProposalQueue([]);
    setSelectedProposalIds([]);
    guideKickoffRef.current = '';
  }, [projectId]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    if (!projectId) {
      setChatThreads([]);
      return;
    }
    setRestoringThread(true);
    void (async () => {
      try {
        const rows = await refreshChatThreads();
        const cleanProject = String(projectId || '').trim();
        if (!cleanProject || rows.length === 0) {
          return;
        }
        const current = String(chatThreadIdRef.current || '').trim();
        const hasCurrent = current && rows.some((item) => String(item.thread_id || '').trim() === current);
        if (hasCurrent) {
          if (!chatThreadProjectIdRef.current) {
            setChatThreadProjectId(cleanProject);
          }
          return;
        }
        const stored = getLastThreadForProject(cleanProject);
        const storedValid = stored && rows.some((item) => String(item.thread_id || '').trim() === stored);
        const fallback = storedValid ? stored : String(rows[0]?.thread_id || '').trim();
        if (!fallback) {
          return;
        }
        setChatThreadId(fallback);
        setChatThreadProjectId(cleanProject);
        setLastThreadForProject(cleanProject, fallback);
        await loadThreadMessages(fallback);
      } finally {
        setRestoringThread(false);
      }
    })();
  }, [isOpen, loadThreadMessages, projectId, refreshChatThreads]);

  useEffect(() => {
    if (!guideMode || !isOpen || !projectId) {
      return;
    }
    if (threadsBusy || restoringThread) {
      return;
    }
    if (activeChatThreadId) {
      return;
    }
    if (messages.length > 1) {
      return;
    }
    if (guideKickoffRef.current === projectId) {
      return;
    }
    guideKickoffRef.current = projectId;
    setBusy(true);
    void (async () => {
      try {
        const response = await sendAiChat({
          project_id: projectId,
          message: t('web.chat.guide_kickoff_request'),
          thread_id: activeChatThreadId || undefined,
          guide_mode: guideMode,
          token_budget: 1400,
        });
        if (response.thread_id) {
          setChatThreadId(response.thread_id);
          setChatThreadProjectId(projectId);
          setLastThreadForProject(projectId, response.thread_id);
          void refreshChatThreads(response.thread_id);
        }
        setMessages((prev) => [
          ...prev,
          {
            id: `${Date.now()}-guide-assistant`,
            role: 'assistant',
            content: response.reply || t('web.chat.empty_reply'),
          },
        ]);
        if (!guideMode && onGuideDocReply) {
          await onGuideDocReply(response.reply || '');
        }
        if (guideMode && response.guide_skip_document && onGuideSkipDocumentRequest) {
          await onGuideSkipDocumentRequest(response.guide_skip_document);
        }
        if (onRefreshProject) {
          await onRefreshProject();
        }
      } catch (error) {
        const text = errorToText(error, t, t('web.error.unknown'));
        setMessages((prev) => [
          ...prev,
          {
            id: `${Date.now()}-guide-error`,
            role: 'system',
            content: t('web.chat.request_failed', {message: text}),
          },
        ]);
        onStatus?.(text, true);
      } finally {
        setBusy(false);
      }
    })();
  }, [
    activeChatThreadId,
    guideMode,
    isOpen,
    messages.length,
    onGuideDocReply,
    onGuideSkipDocumentRequest,
    onStatus,
    projectId,
    refreshChatThreads,
    restoringThread,
    t,
    threadsBusy,
  ]);

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
        thread_id: activeChatThreadId || undefined,
        guide_mode: guideMode,
        token_budget: 1800,
      });
      if (response.thread_id) {
        setChatThreadId(response.thread_id);
        setChatThreadProjectId(projectId);
        setLastThreadForProject(projectId, response.thread_id);
        void refreshChatThreads(response.thread_id);
      }

      appendMessage({
        id: `${Date.now()}-assistant`,
        role: 'assistant',
        content: response.reply || t('web.chat.empty_reply'),
        suggestions: response.suggested_options || [],
      });

      if (!guideMode && onGuideDocReply) {
        await onGuideDocReply(response.reply || '');
      }
      if (guideMode && response.guide_skip_document && onGuideSkipDocumentRequest) {
        await onGuideSkipDocumentRequest(response.guide_skip_document);
      }

      if (response.updated_node_id) {
        onStatus?.(t('web.toast.ai_node_updated', {node: response.updated_node_id}), false);
      }
      if (onRefreshProject) {
        await onRefreshProject();
      }
    } catch (error) {
      const text = errorToText(error, t, t('web.error.unknown'));
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
      onStatus?.(t('web.chat.suggestion_create_failed', {message: errorToText(error, t, t('web.error.unknown'))}), true);
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
      onStatus?.(t('web.chat.agent.selected_node_required'), true);
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
      onStatus?.(t('web.chat.agent.session_started', {thread_id: payload.thread_id}), false);
      if (onRefreshProject) {
        await onRefreshProject();
      }
    } catch (error) {
      onStatus?.(errorToText(error, t, t('web.error.unknown')), true);
    } finally {
      setSessionBusy(false);
    }
  };

  const refreshSession = async () => {
    const threadId = agentThreadId.trim();
    if (!threadId) {
      onStatus?.(t('web.chat.agent.thread_required'), true);
      return;
    }
    setSessionBusy(true);
    try {
      const payload = await getAgentSession(threadId);
      applySessionPayload(payload);
      onStatus?.(t('web.chat.agent.session_status', {status: payload.session.status}), false);
    } catch (error) {
      onStatus?.(errorToText(error, t, t('web.error.unknown')), true);
    } finally {
      setSessionBusy(false);
    }
  };

  const submitSessionDecision = async (action: string, payload: Record<string, unknown> = {}) => {
    const threadId = agentThreadId.trim();
    if (!threadId) {
      onStatus?.(t('web.chat.agent.thread_required'), true);
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
      onStatus?.(t('web.chat.agent.decision_applied', {action, status: response.session.status}), false);
      if (response.session.status === 'AWAITING_SETTING_PROPOSAL_CONFIRM') {
        void loadProposalQueue();
      }
      if (action === 'confirm_yes' || action === 'confirm_yes_persist_rule' || action === 'satisfied') {
        if (onRefreshProject) {
          await onRefreshProject();
        }
      }
    } catch (error) {
      onStatus?.(errorToText(error, t, t('web.error.unknown')), true);
    } finally {
      setSessionBusy(false);
    }
  };

  const applyDiffReview = async (rejectAll: boolean) => {
    const threadId = agentThreadId.trim();
    if (!threadId) {
      onStatus?.(t('web.chat.agent.thread_required'), true);
      return;
    }
    if (!agentSession) {
      onStatus?.(t('web.chat.agent.session_not_loaded'), true);
      return;
    }
    const pendingMeta = asRecord(agentSession.pending_meta);
    const diffPatch = asRecord(pendingMeta.diff_patch);
    const diffId = String(diffPatch.diff_id || '').trim();
    if (!diffId) {
      onStatus?.(t('web.chat.agent.diff_patch_missing'), true);
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
        rejectAll ? t('web.chat.agent.diff_review_rejected_all') : t('web.chat.agent.diff_review_applied'),
        false,
      );
    } catch (error) {
      onStatus?.(errorToText(error, t, t('web.error.unknown')), true);
    } finally {
      setSessionBusy(false);
    }
  };

  const loadProposalQueue = async () => {
    const threadId = (agentThreadId || agentSession?.thread_id || '').trim();
    if (!threadId) {
      onStatus?.(t('web.chat.agent.thread_required'), true);
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
      onStatus?.(t('web.chat.agent.pending_proposals', {count: payload.count}), false);
    } catch (error) {
      onStatus?.(errorToText(error, t, t('web.error.unknown')), true);
    } finally {
      setProposalBusy(false);
    }
  };

  const reviewProposalBatch = async (action: 'approve' | 'reject') => {
    const threadId = (agentThreadId || agentSession?.thread_id || '').trim();
    if (!threadId) {
      onStatus?.(t('web.chat.agent.thread_required'), true);
      return;
    }
    if (selectedProposalIds.length === 0) {
      onStatus?.(t('web.chat.agent.no_proposal_selected'), true);
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
      onStatus?.(t('web.chat.agent.batch_review_done', {action, count: selectedProposalIds.length}), false);
    } catch (error) {
      onStatus?.(errorToText(error, t, t('web.error.unknown')), true);
    } finally {
      setProposalBusy(false);
    }
  };

  const deferCurrentProposal = async () => {
    const threadId = (agentThreadId || agentSession?.thread_id || '').trim();
    if (!threadId) {
      onStatus?.(t('web.chat.agent.thread_required'), true);
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

  const selectChatThread = useCallback(
    async (nextThreadId: string) => {
      const clean = String(nextThreadId || '').trim();
      if (!clean) {
        clearCurrentSession(false);
        return;
      }
      setChatThreadId(clean);
      setChatThreadProjectId(String(projectId || '').trim());
      setLastThreadForProject(projectId, clean);
      await loadThreadMessages(clean);
    },
    [clearCurrentSession, loadThreadMessages, projectId],
  );

  return (
    <div
      className={cn(
        fullScreen
          ? 'absolute inset-0 z-40 border-0 rounded-none bg-white shadow-none overflow-hidden transition-[opacity,transform] duration-200 ease-out'
          : 'fixed z-50 rounded-xl border border-slate-200 bg-white shadow-2xl overflow-hidden transition-[opacity,transform] duration-200 ease-out',
        isOpen ? 'opacity-100 translate-y-0 pointer-events-auto' : 'opacity-0 translate-y-2 pointer-events-none',
      )}
      style={
        fullScreen
          ? undefined
          : {
              left: windowRect.x,
              top: windowRect.y,
              width: windowRect.width,
              height: windowRect.height,
            }
      }
    >
      <div
        className="h-full w-full flex flex-col"
        style={
          fullScreen
            ? undefined
            : {
                transform: `scale(${contentScale})`,
                transformOrigin: 'top left',
                width: `${100 / contentScale}%`,
                height: `${100 / contentScale}%`,
              }
        }
      >
      <div
        onPointerDown={startDrag}
        className={cn(
          'h-14 border-b border-slate-200 flex items-center justify-between px-4 shrink-0 bg-white/95 backdrop-blur select-none',
          fullScreen ? 'cursor-default' : 'cursor-move',
        )}
      >
        <div className="flex items-center gap-2 text-slate-800">
          <Sparkles size={18} className="text-pink-500" />
          <span className="font-bold">{guideMode ? t('web.chat.guide_title') : t('web.chat.drawer_title')}</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            data-chat-no-drag="true"
            onClick={() => clearCurrentSession(true)}
            title={t('web.chat.clear_session')}
            className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-md transition-colors"
          >
            <Trash2 size={18} />
          </button>
          {!guideMode ? (
            <button
              data-chat-no-drag="true"
              onClick={onClose}
              className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-md transition-colors"
            >
              <X size={18} />
            </button>
          ) : null}
        </div>
      </div>

      {guideMode ? (
        <div className="px-4 py-3 border-b border-rose-100 bg-rose-50/70 text-xs text-slate-700 space-y-2">
          <div className="font-semibold text-rose-700">{t('web.chat.guide_panel_hint')}</div>
          <div className="flex flex-wrap items-center gap-2">
            {guideDocStatus.map((item) => (
              <span
                key={item.key}
                className={cn(
                  'inline-flex items-center rounded-full px-2 py-0.5 text-[11px] border',
                  item.filled
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                    : 'border-amber-200 bg-amber-50 text-amber-700',
                )}
              >
                {item.title} · {item.filled ? t('web.chat.guide_status_done') : t('web.chat.guide_status_pending')}
              </span>
            ))}
          </div>
          <div className="text-[11px] text-amber-700">{t('web.chat.guide_modify_notice')}</div>
        </div>
      ) : null}

      <div className="px-4 py-2 border-b border-slate-100 bg-slate-50 text-xs text-slate-600">
        <div className="flex items-center justify-between gap-3">
          <span className="truncate">{t('web.chat.project_label', {project: projectId || t('web.top.project_unselected')})}</span>
          {!guideMode ? (
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
          ) : (
            <span className="text-[11px] text-slate-500">{t('web.chat.guide_step_hint')}</span>
          )}
        </div>
        <div className="mt-2 flex items-center gap-2">
          <button
            type="button"
            onClick={() => clearCurrentSession(true)}
            className="h-8 px-3 rounded-md border border-slate-200 bg-white hover:bg-slate-100 text-[11px] font-medium"
          >
            {t('web.chat.new_conversation')}
          </button>
          <select
            value={chatThreadId}
            onChange={(event) => void selectChatThread(event.target.value)}
            disabled={threadsBusy || busy || !projectId}
            className="flex-1 h-8 rounded-md border border-slate-200 bg-white px-2 text-[11px] disabled:opacity-60"
          >
            <option value="">{t('web.chat.thread_current_new')}</option>
            {chatThreads.map((item) => (
              <option key={item.thread_id} value={item.thread_id}>
                {previewThreadLabel(item)}
              </option>
            ))}
          </select>
        </div>
      </div>

      {!guideMode ? (
      <div className="px-4 py-2 border-b border-slate-100 bg-slate-50/70 text-[11px] text-slate-600 space-y-2">
        <div className="flex items-center gap-2">
          <input
            value={agentThreadId}
            onChange={(event) => setAgentThreadId(event.target.value)}
            placeholder={t('web.chat.agent.placeholder_thread_id')}
            className="flex-1 h-8 rounded-md border border-slate-200 bg-white px-2 text-xs"
          />
          <button
            onClick={() => void refreshSession()}
            disabled={sessionBusy || !agentThreadId.trim()}
            className="h-8 px-2 rounded-md border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-60"
          >
            {t('web.chat.agent.refresh')}
          </button>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => void startSession()}
            disabled={sessionBusy || !projectId || !selectedNodeId}
            className="h-8 px-3 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-200 hover:bg-indigo-100 disabled:opacity-60"
          >
            {t('web.chat.agent.start_session')}
          </button>
          <button
            onClick={() => void loadProposalQueue()}
            disabled={proposalBusy || !agentThreadId.trim()}
            className="h-8 px-3 rounded-md border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-60"
          >
            {t('web.chat.agent.load_proposals')}
          </button>
        </div>

        <div className="rounded-md border border-slate-200 bg-white p-2 text-[11px]">
          {agentSession ? (
            <div className="space-y-1">
              <div>
                {t('web.chat.agent.session_status_line', {
                  status: agentSession.status,
                  version: agentSession.state_version,
                })}
              </div>
              <div>
                {t('web.chat.agent.session_pending_line', {
                  chars: String(agentSession.pending_content || '').length,
                  count: pendingStateUpdateCount,
                })}
              </div>
              <div>
                {t('web.chat.agent.session_latest_proposal', {
                  id: agentSession.latest_setting_proposal_id || '-',
                })}
              </div>
            </div>
          ) : (
            <div className="text-slate-400">{t('web.chat.agent.session_not_loaded')}</div>
          )}
        </div>

        <input
          value={correctionInput}
          onChange={(event) => setCorrectionInput(event.target.value)}
          placeholder={t('web.chat.agent.placeholder_correction')}
          className="w-full h-8 rounded-md border border-slate-200 bg-white px-2 text-xs"
        />
        <input
          value={persistDirective}
          onChange={(event) => setPersistDirective(event.target.value)}
          placeholder={t('web.chat.agent.placeholder_persist')}
          className="w-full h-8 rounded-md border border-slate-200 bg-white px-2 text-xs"
        />

        {(sessionStatus === 'AWAITING_CONFIRM' || sessionStatus === 'AWAITING_CORRECTION_CONFIRM') && (
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => void submitSessionDecision('confirm_yes')}
              disabled={sessionBusy || !agentThreadId.trim()}
              className="h-8 px-3 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 disabled:opacity-60"
            >
              {t('web.chat.agent.confirm_yes')}
            </button>
            <button
              onClick={() =>
                void submitSessionDecision('confirm_yes_persist_rule', {directive: persistDirective.trim()})
              }
              disabled={sessionBusy || !agentThreadId.trim() || !persistDirective.trim()}
              className="h-8 px-3 rounded-md bg-cyan-50 text-cyan-700 border border-cyan-200 hover:bg-cyan-100 disabled:opacity-60"
            >
              {t('web.chat.agent.confirm_persist')}
            </button>
            <button
              onClick={() =>
                void submitSessionDecision('correct', {
                  correction: correctionInput.trim() || t('web.chat.agent.default_correction_confirm'),
                })
              }
              disabled={sessionBusy || !agentThreadId.trim()}
              className="h-8 px-3 rounded-md bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100 disabled:opacity-60"
            >
              {t('web.chat.agent.correct')}
            </button>
            <button
              onClick={() => void submitSessionDecision('stop')}
              disabled={sessionBusy || !agentThreadId.trim()}
              className="h-8 px-3 rounded-md bg-rose-50 text-rose-700 border border-rose-200 hover:bg-rose-100 disabled:opacity-60"
            >
              {t('web.chat.agent.stop')}
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
              {t('web.chat.agent.chapter_satisfied')}
            </button>
            <button
              onClick={() =>
                void submitSessionDecision('unsatisfied', {
                  correction: correctionInput.trim() || t('web.chat.agent.default_correction_chapter'),
                })
              }
              disabled={sessionBusy || !agentThreadId.trim()}
              className="h-8 px-3 rounded-md bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100 disabled:opacity-60"
            >
              {t('web.chat.agent.chapter_unsatisfied')}
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
              {t('web.chat.agent.approve_proposal')}
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
              {t('web.chat.agent.reject_proposal')}
            </button>
            <button
              onClick={() => void deferCurrentProposal()}
              disabled={sessionBusy || !agentThreadId.trim() || !deferReviewEnabled}
              className="h-8 px-3 rounded-md border border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100 disabled:opacity-60"
            >
              {t('web.chat.agent.defer_current')}
            </button>
          </div>
        )}

        {sessionStatus === 'AWAITING_CORRECTION_CONFIRM' && sessionDiffHunks.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-slate-500">{t('web.chat.agent.diff_hunks', {count: sessionDiffHunks.length})}</span>
            <button
              onClick={() => void applyDiffReview(false)}
              disabled={sessionBusy || !agentThreadId.trim()}
              className="h-8 px-3 rounded-md bg-violet-50 text-violet-700 border border-violet-200 hover:bg-violet-100 disabled:opacity-60"
            >
              {t('web.chat.agent.apply_diff_hunks')}
            </button>
            <button
              onClick={() => void applyDiffReview(true)}
              disabled={sessionBusy || !agentThreadId.trim()}
              className="h-8 px-3 rounded-md bg-slate-100 text-slate-700 border border-slate-200 hover:bg-slate-200 disabled:opacity-60"
            >
              {t('web.chat.agent.reject_all_hunks')}
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
            <span>{t('web.chat.agent.defer_shortcut')}</span>
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
                    {proposalId} [{proposalType || t('web.chat.agent.proposal_unknown')} / {proposalStatus || t('web.chat.agent.proposal_pending')}]
                  </span>
                </label>
              );
            })}
          </div>
        ) : (
          <div className="text-slate-400">{t('web.chat.agent.no_pending_proposals')}</div>
        )}

        <div className="flex items-center gap-2">
          <button
            onClick={() => void reviewProposalBatch('approve')}
            disabled={proposalBusy || selectedProposalIds.length === 0}
            className="h-8 px-3 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 disabled:opacity-60"
          >
            {t('web.chat.agent.approve_selected')}
          </button>
          <button
            onClick={() => void reviewProposalBatch('reject')}
            disabled={proposalBusy || selectedProposalIds.length === 0}
            className="h-8 px-3 rounded-md bg-rose-50 text-rose-700 border border-rose-200 hover:bg-rose-100 disabled:opacity-60"
          >
            {t('web.chat.agent.reject_selected')}
          </button>
        </div>
      </div>
      ) : null}

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
      {!fullScreen ? (
        <div
          data-chat-no-drag="true"
          onPointerDown={startResize}
          className="absolute right-0 bottom-0 z-[60] h-5 w-5 cursor-nwse-resize touch-none"
        >
          <div className="absolute inset-0 bg-gradient-to-br from-transparent via-transparent to-slate-300/80" />
        </div>
      ) : null}
    </div>
  );
}
