import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {Send, Bot, User, X, Sparkles, PlusCircle, ShieldCheck, Trash2, Square, ChevronDown, ChevronUp} from 'lucide-react';
import {cn} from '../utils';
import {
  ApiAbortError,
  ApiTimeoutError,
  cancelAgentSession,
  createProjectChatThread,
  getAgentSession,
  getLatestProjectAgentSession,
  getProjectChatThreadMessages,
  listAgentSettingProposals,
  listProjectChatThreads,
  reviewAgentSettingProposal,
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

type ResizeAnchor = 'se' | 'sw' | 'ne' | 'nw';

interface ResizeState {
  startX: number;
  startY: number;
  anchor: ResizeAnchor;
  originX: number;
  originY: number;
  originWidth: number;
  originHeight: number;
}

interface MarkdownBlock {
  key: string;
  type: 'paragraph' | 'heading' | 'list' | 'code';
  level?: number;
  lines?: string[];
  items?: string[];
  code?: string;
  language?: string;
}

const CHAT_MIN_WIDTH = 360;
const CHAT_MIN_HEIGHT = 420;
const CHAT_MARGIN = 12;
const CHAT_MIN_TOP = 56;
const CHAT_ZOOM_MIN = 0.72;
const CHAT_ZOOM_MAX = 1.45;
const CHAT_ZOOM_STEP = 0.06;
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

function parseInlineMarkdown(text: string): React.ReactNode[] {
  const source = String(text || '');
  const tokens: React.ReactNode[] = [];
  const tokenPattern = /(`[^`\n]+`|\*\*[^*\n]+\*\*|\*[^*\n]+\*|\[[^\]]+\]\((https?:\/\/[^\s)]+)\))/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null = tokenPattern.exec(source);
  while (match) {
    if (match.index > lastIndex) {
      tokens.push(source.slice(lastIndex, match.index));
    }
    const raw = match[0];
    const key = `${match.index}-${raw}`;
    if (raw.startsWith('`') && raw.endsWith('`')) {
      tokens.push(
        <code key={key} className="rounded bg-slate-200/70 px-1 py-0.5 text-[0.92em] text-slate-800">
          {raw.slice(1, -1)}
        </code>,
      );
    } else if (raw.startsWith('**') && raw.endsWith('**')) {
      tokens.push(
        <strong key={key} className="font-semibold">
          {raw.slice(2, -2)}
        </strong>,
      );
    } else if (raw.startsWith('*') && raw.endsWith('*')) {
      tokens.push(
        <em key={key} className="italic">
          {raw.slice(1, -1)}
        </em>,
      );
    } else if (raw.startsWith('[')) {
      const linkMatch = raw.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/);
      if (linkMatch) {
        tokens.push(
          <a
            key={key}
            href={linkMatch[2]}
            target="_blank"
            rel="noreferrer"
            className="underline decoration-dotted underline-offset-2 text-sky-700 hover:text-sky-800"
          >
            {linkMatch[1]}
          </a>,
        );
      } else {
        tokens.push(raw);
      }
    } else {
      tokens.push(raw);
    }
    lastIndex = tokenPattern.lastIndex;
    match = tokenPattern.exec(source);
  }
  if (lastIndex < source.length) {
    tokens.push(source.slice(lastIndex));
  }
  return tokens;
}

function parseMarkdownBlocks(content: string): MarkdownBlock[] {
  const lines = String(content || '')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .split('\n');
  const blocks: MarkdownBlock[] = [];
  let paragraphLines: string[] = [];
  let listItems: string[] = [];
  let codeLines: string[] = [];
  let codeLanguage = '';
  let inCode = false;
  let serial = 0;

  const nextKey = (prefix: string): string => {
    serial += 1;
    return `${prefix}-${serial}`;
  };

  const flushParagraph = () => {
    if (paragraphLines.length === 0) {
      return;
    }
    blocks.push({
      key: nextKey('p'),
      type: 'paragraph',
      lines: paragraphLines,
    });
    paragraphLines = [];
  };

  const flushList = () => {
    if (listItems.length === 0) {
      return;
    }
    blocks.push({
      key: nextKey('ul'),
      type: 'list',
      items: listItems,
    });
    listItems = [];
  };

  const flushCode = () => {
    blocks.push({
      key: nextKey('code'),
      type: 'code',
      code: codeLines.join('\n'),
      language: codeLanguage,
    });
    codeLines = [];
    codeLanguage = '';
  };

  for (const line of lines) {
    const fenceMatch = line.match(/^```([\w-]+)?\s*$/);
    if (fenceMatch) {
      flushParagraph();
      flushList();
      if (inCode) {
        flushCode();
        inCode = false;
      } else {
        inCode = true;
        codeLanguage = String(fenceMatch[1] || '').trim();
        codeLines = [];
      }
      continue;
    }
    if (inCode) {
      codeLines.push(line);
      continue;
    }

    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      blocks.push({
        key: nextKey('h'),
        type: 'heading',
        level: headingMatch[1].length,
        lines: [headingMatch[2]],
      });
      continue;
    }

    const listMatch = line.match(/^\s*[-*+]\s+(.+)$/);
    if (listMatch) {
      flushParagraph();
      listItems.push(listMatch[1]);
      continue;
    }

    if (!line.trim()) {
      flushParagraph();
      flushList();
      continue;
    }
    paragraphLines.push(line);
  }

  flushParagraph();
  flushList();
  if (inCode) {
    flushCode();
  }
  return blocks;
}

function MarkdownMessage({content}: {content: string}) {
  const blocks = useMemo(() => parseMarkdownBlocks(content), [content]);
  return (
    <div className="space-y-1.5 break-words">
      {blocks.map((block) => {
        if (block.type === 'heading') {
          const level = Math.max(1, Math.min(6, Number(block.level || 1)));
          const headingClass = level <= 2 ? 'font-semibold text-[1.02em]' : 'font-semibold';
          return (
            <div key={block.key} className={headingClass}>
              {parseInlineMarkdown(String(block.lines?.[0] || ''))}
            </div>
          );
        }
        if (block.type === 'list') {
          return (
            <ul key={block.key} className="list-disc pl-5 space-y-1">
              {(block.items || []).map((item, index) => (
                <li key={`${block.key}-${index}`}>{parseInlineMarkdown(item)}</li>
              ))}
            </ul>
          );
        }
        if (block.type === 'code') {
          return (
            <pre key={block.key} className="rounded-md border border-slate-300/70 bg-slate-900 text-slate-100 px-3 py-2 text-xs overflow-x-auto">
              {block.language ? <div className="mb-1 text-[10px] text-slate-400">{block.language}</div> : null}
              <code>{String(block.code || '')}</code>
            </pre>
          );
        }
        return (
          <p key={block.key} className="whitespace-pre-wrap">
            {(block.lines || []).map((line, index) => (
              <React.Fragment key={`${block.key}-line-${index}`}>
                {index > 0 ? <br /> : null}
                {parseInlineMarkdown(line)}
              </React.Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
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
  const [agentSession, setAgentSession] = useState<AgentSessionPayload | null>(null);
  const [sessionBusy, setSessionBusy] = useState(false);
  const [proposalBusy, setProposalBusy] = useState(false);
  const [proposalQueue, setProposalQueue] = useState<Array<Record<string, unknown>>>([]);
  const [queuedInputCount, setQueuedInputCount] = useState(0);
  const [toolBubbleCollapsed, setToolBubbleCollapsed] = useState(true);
  const [requestNote, setRequestNote] = useState('');
  const [diffDecisions, setDiffDecisions] = useState<Record<string, 'accept' | 'reject'>>({});
  const [diffEditedTexts, setDiffEditedTexts] = useState<Record<string, string>>({});
  const [windowRect, setWindowRect] = useState<ChatWindowRect>(() => getDefaultChatRect());
  const [chatZoom, setChatZoom] = useState(1);

  const dragStateRef = useRef<DragState | null>(null);
  const resizeStateRef = useRef<ResizeState | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatThreadIdRef = useRef('');
  const chatThreadProjectIdRef = useRef('');
  const queuedInputRef = useRef<string[]>([]);
  const processingQueueRef = useRef(false);
  const stopRequestedRef = useRef(false);
  const activeChatAbortRef = useRef<AbortController | null>(null);

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
    const autoScale = fullScreen
      ? 1
      : clampNumber(Math.min(windowRect.width / 460, windowRect.height / 760), 0.82, 1.08);
    return clampNumber(autoScale * chatZoom, CHAT_ZOOM_MIN, CHAT_ZOOM_MAX);
  }, [chatZoom, fullScreen, windowRect.height, windowRect.width]);

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
        const dx = event.clientX - resize.startX;
        const dy = event.clientY - resize.startY;
        let nextX = resize.originX;
        let nextY = resize.originY;
        let nextWidth = resize.originWidth;
        let nextHeight = resize.originHeight;
        if (resize.anchor === 'se') {
          nextWidth = resize.originWidth + dx;
          nextHeight = resize.originHeight + dy;
        } else if (resize.anchor === 'sw') {
          nextX = resize.originX + dx;
          nextWidth = resize.originWidth - dx;
          nextHeight = resize.originHeight + dy;
        } else if (resize.anchor === 'ne') {
          nextY = resize.originY + dy;
          nextWidth = resize.originWidth + dx;
          nextHeight = resize.originHeight - dy;
        } else {
          nextX = resize.originX + dx;
          nextY = resize.originY + dy;
          nextWidth = resize.originWidth - dx;
          nextHeight = resize.originHeight - dy;
        }
        setWindowRect((prev) =>
          clampWindowRect({
            ...prev,
            x: nextX,
            y: nextY,
            width: nextWidth,
            height: nextHeight,
          }),
        );
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
    (anchor: ResizeAnchor) => (event: React.PointerEvent<HTMLDivElement>) => {
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
        anchor,
        originX: windowRect.x,
        originY: windowRect.y,
        originWidth: windowRect.width,
        originHeight: windowRect.height,
      };
      beginPointerInteraction();
    },
    [
      beginPointerInteraction,
      fullScreen,
      stopPointerInteraction,
      windowRect.height,
      windowRect.width,
      windowRect.x,
      windowRect.y,
    ],
  );

  const handleAltWheelZoom = useCallback((event: React.WheelEvent<HTMLDivElement>) => {
    if (!event.altKey) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    const delta = event.deltaY < 0 ? CHAT_ZOOM_STEP : -CHAT_ZOOM_STEP;
    setChatZoom((prev) => clampNumber(prev + delta, CHAT_ZOOM_MIN, CHAT_ZOOM_MAX));
  }, []);

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

  const activeAgentThreadId = useMemo(() => {
    const sessionThread = String(agentSession?.thread_id || '').trim();
    if (sessionThread) {
      return sessionThread;
    }
    return String(activeChatThreadId || '').trim();
  }, [activeChatThreadId, agentSession?.thread_id]);

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
      stopRequestedRef.current = false;
      queuedInputRef.current = [];
      processingQueueRef.current = false;
      activeChatAbortRef.current?.abort();
      activeChatAbortRef.current = null;
      setMessages([{id: 'boot', role: 'assistant', content: bootMessage}]);
      setInput('');
      setQueuedInputCount(0);
      setBusy(false);
      setChatThreadId('');
      setChatThreadProjectId('');
      setAllowNodeWrite(false);
      setAgentSession(null);
      setSessionBusy(false);
      setProposalBusy(false);
      setProposalQueue([]);
      setDiffDecisions({});
      setDiffEditedTexts({});
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
    stopRequestedRef.current = false;
    queuedInputRef.current = [];
    processingQueueRef.current = false;
    activeChatAbortRef.current?.abort();
    activeChatAbortRef.current = null;
    if (!projectId) {
      setChatThreads([]);
      setChatThreadId('');
      setChatThreadProjectId('');
      setMessages([{id: 'boot', role: 'assistant', content: bootMessage}]);
      setInput('');
      setQueuedInputCount(0);
      return;
    }
    setChatThreads([]);
    setChatThreadId('');
    setChatThreadProjectId('');
    setMessages([{id: 'boot', role: 'assistant', content: bootMessage}]);
    setInput('');
    setQueuedInputCount(0);
    setAllowNodeWrite(false);
    setChatZoom(1);
    setAgentSession(null);
    setProposalQueue([]);
    setDiffDecisions({});
    setDiffEditedTexts({});
    guideKickoffRef.current = '';
  }, [bootMessage, projectId]);

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
        const cleanProject = String(projectId || '').trim();
        let rows = await refreshChatThreads();
        if (cleanProject && rows.length === 0) {
          const created = await createProjectChatThread(cleanProject);
          const createdThread = String(created.thread_id || '').trim();
          rows = await refreshChatThreads(createdThread);
          if (createdThread) {
            setChatThreadId(createdThread);
            setChatThreadProjectId(cleanProject);
            setLastThreadForProject(cleanProject, createdThread);
            await loadThreadMessages(createdThread);
          }
        }
        if (cleanProject && rows.length > 0) {
          const current = String(chatThreadIdRef.current || '').trim();
          const hasCurrent = current && rows.some((item) => String(item.thread_id || '').trim() === current);
          if (hasCurrent) {
            if (!chatThreadProjectIdRef.current) {
              setChatThreadProjectId(cleanProject);
            }
          } else {
            const stored = getLastThreadForProject(cleanProject);
            const storedValid = stored && rows.some((item) => String(item.thread_id || '').trim() === stored);
            const fallback = storedValid ? stored : String(rows[0]?.thread_id || '').trim();
            if (fallback) {
              setChatThreadId(fallback);
              setChatThreadProjectId(cleanProject);
              setLastThreadForProject(cleanProject, fallback);
              await loadThreadMessages(fallback);
            }
          }
        }
        if (!cleanProject) {
          return;
        }
        const latestSession = await getLatestProjectAgentSession(cleanProject);
        if (latestSession.session && typeof latestSession.session === 'object') {
          setAgentSession(latestSession.session);
          const latestThread = String(latestSession.thread_id || '').trim();
          if (latestThread) {
            setChatThreadId((prev) => prev || latestThread);
            setChatThreadProjectId(cleanProject);
            setLastThreadForProject(cleanProject, latestThread);
          }
        } else {
          setAgentSession(null);
        }
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
          allow_node_write: allowNodeWrite,
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
    allowNodeWrite,
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

  const appendMessage = useCallback((message: ChatMessage) => {
    setMessages((prev) => [...prev, message]);
  }, []);

  const sessionPendingMeta = asRecord(agentSession?.pending_meta);
  const sessionDiffPatch = asRecord(sessionPendingMeta.diff_patch);
  const sessionStatus = String(agentSession?.status || '').trim();
  const pendingStateUpdateCount = Number(agentSession?.pending_state_update_count || 0);
  const isAgentRunning = sessionStatus === 'RUNNING_GENERATION' || sessionStatus === 'RUNNING_CORRECTION';

  const sessionStatusLabel = useMemo(() => {
    const mapping: Record<string, string> = {
      RUNNING_GENERATION: '生成中',
      AWAITING_CONFIRM: '等待确认',
      AWAITING_CLARIFICATION: '等待澄清',
      AWAITING_SETTING_PROPOSAL_CONFIRM: '等待设定提案确认',
      AWAITING_CHAPTER_REVIEW: '等待章节审阅',
      RUNNING_CORRECTION: '修订中',
      AWAITING_CORRECTION_CONFIRM: '等待修订确认',
      PAUSED_BY_USER: '已暂停',
      COMPLETED: '已完成',
      FAILED: '失败',
    };
    return mapping[sessionStatus] || sessionStatus || '-';
  }, [sessionStatus]);

  const sessionDiffHunks = useMemo(() => {
    const raw = sessionDiffPatch.hunks;
    if (!Array.isArray(raw)) {
      return [] as Array<Record<string, unknown>>;
    }
    return raw.map((item) => asRecord(item)).filter((item) => String(item.hunk_id || '').trim());
  }, [sessionDiffPatch.hunks]);

  const toolCallPreview = useMemo(() => {
    const raw = sessionPendingMeta.agent_tool_calls_preview;
    if (!Array.isArray(raw)) {
      return [] as Array<Record<string, unknown>>;
    }
    return raw
      .map((item) => asRecord(item))
      .filter((item) => String(item.tool_name || '').trim());
  }, [sessionPendingMeta.agent_tool_calls_preview]);

  const agentPlanSteps = useMemo(() => {
    return toolCallPreview.map((item, index) => {
      const isCurrent = isAgentRunning && index === toolCallPreview.length - 1;
      const done = !isAgentRunning || index < toolCallPreview.length - 1;
      return {
        id: `${index}-${String(item.tool_name || 'tool')}`,
        title: String(item.tool_name || 'tool'),
        current: isCurrent,
        done,
      };
    });
  }, [isAgentRunning, toolCallPreview]);

  const canProcessQueue = !busy && !sessionBusy && !proposalBusy && !restoringThread && !isAgentRunning;

  const applySessionPayload = useCallback(
    (payload: {thread_id: string; session: AgentSessionPayload}) => {
      const cleanThreadId = String(payload.thread_id || '').trim();
      if (cleanThreadId && projectId) {
        setChatThreadId(cleanThreadId);
        setChatThreadProjectId(projectId);
        setLastThreadForProject(projectId, cleanThreadId);
        void refreshChatThreads(cleanThreadId);
      }
      setAgentSession(payload.session || null);
    },
    [projectId, refreshChatThreads],
  );

  const runChatTurn = useCallback(
    async (message: string) => {
      if (!projectId) {
        return;
      }
      stopRequestedRef.current = false;
      const controller = new AbortController();
      activeChatAbortRef.current = controller;
      setBusy(true);
      try {
        const cleanProject = String(projectId || '').trim();
        const liveThread = String(chatThreadIdRef.current || '').trim();
        const liveThreadProject = String(chatThreadProjectIdRef.current || '').trim();
        const threadForSend = liveThread && liveThreadProject === cleanProject ? liveThread : '';
        const response = await sendAiChat(
          {
            project_id: projectId,
            message,
            node_id: selectedNodeId || undefined,
            thread_id: threadForSend || undefined,
            allow_node_write: allowNodeWrite,
            guide_mode: guideMode,
            token_budget: 1800,
          },
          {signal: controller.signal},
        );
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
        if (error instanceof ApiAbortError) {
          onStatus?.('已中断当前任务', false);
          return;
        }
        const text = errorToText(error, t, t('web.error.unknown'));
        appendMessage({
          id: `${Date.now()}-error`,
          role: 'system',
          content: t('web.chat.request_failed', {message: text}),
        });
        onStatus?.(text, true);
      } finally {
        if (activeChatAbortRef.current === controller) {
          activeChatAbortRef.current = null;
        }
        setBusy(false);
      }
    },
    [
      allowNodeWrite,
      appendMessage,
      guideMode,
      onGuideDocReply,
      onGuideSkipDocumentRequest,
      onRefreshProject,
      onStatus,
      projectId,
      refreshChatThreads,
      selectedNodeId,
      t,
    ],
  );

  const processQueuedInputs = useCallback(async () => {
    if (processingQueueRef.current) {
      return;
    }
    processingQueueRef.current = true;
    try {
      while (!stopRequestedRef.current) {
        if (busy || sessionBusy || proposalBusy || restoringThread || isAgentRunning) {
          break;
        }
        const next = queuedInputRef.current.shift();
        setQueuedInputCount(queuedInputRef.current.length);
        if (!next) {
          break;
        }
        await runChatTurn(next);
      }
    } finally {
      processingQueueRef.current = false;
      setQueuedInputCount(queuedInputRef.current.length);
    }
  }, [busy, isAgentRunning, proposalBusy, restoringThread, runChatTurn, sessionBusy]);

  const enqueueInput = useCallback(
    (message: string) => {
      const clean = String(message || '').trim();
      if (!clean) {
        return;
      }
      queuedInputRef.current.push(clean);
      const nextCount = queuedInputRef.current.length;
      setQueuedInputCount(nextCount);
      onStatus?.(`已加入队列（${nextCount}）`, false);
    },
    [onStatus],
  );

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    const message = input.trim();
    if (!message) {
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
    if (!canProcessQueue || processingQueueRef.current || queuedInputRef.current.length > 0) {
      enqueueInput(message);
      return;
    }
    await runChatTurn(message);
    if (queuedInputRef.current.length > 0) {
      void processQueuedInputs();
    }
  };

  const stopGeneration = useCallback(async () => {
    stopRequestedRef.current = true;
    queuedInputRef.current = [];
    processingQueueRef.current = false;
    setQueuedInputCount(0);
    activeChatAbortRef.current?.abort();
    activeChatAbortRef.current = null;
    const threadId = String(activeAgentThreadId || '').trim();
    if (!threadId) {
      setBusy(false);
      return;
    }
    setSessionBusy(true);
    try {
      const payload = await cancelAgentSession(threadId);
      applySessionPayload(payload);
      onStatus?.('已停止当前任务', false);
    } catch (error) {
      if (!(error instanceof ApiAbortError)) {
        onStatus?.(errorToText(error, t, t('web.error.unknown')), true);
      }
    } finally {
      setBusy(false);
      setSessionBusy(false);
    }
  }, [activeAgentThreadId, applySessionPayload, onStatus, t]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    if (!canProcessQueue) {
      return;
    }
    if (queuedInputRef.current.length === 0) {
      return;
    }
    void processQueuedInputs();
  }, [canProcessQueue, isOpen, processQueuedInputs]);

  const createNewConversation = useCallback(async () => {
    if (!projectId) {
      onStatus?.(t('web.chat.project_required'), true);
      return;
    }
    stopRequestedRef.current = false;
    queuedInputRef.current = [];
    processingQueueRef.current = false;
    setQueuedInputCount(0);
    activeChatAbortRef.current?.abort();
    activeChatAbortRef.current = null;
    setBusy(true);
    try {
      const created = await createProjectChatThread(projectId);
      const nextThreadId = String(created.thread_id || '').trim();
      if (!nextThreadId) {
        throw new Error('thread_id missing');
      }
      setChatThreadId(nextThreadId);
      setChatThreadProjectId(projectId);
      setLastThreadForProject(projectId, nextThreadId);
      setMessages([{id: 'boot', role: 'assistant', content: bootMessage}]);
      setAgentSession(null);
      setProposalQueue([]);
      setRequestNote('');
      setDiffDecisions({});
      setDiffEditedTexts({});
      await refreshChatThreads(nextThreadId);
      await loadThreadMessages(nextThreadId);
    } catch (error) {
      onStatus?.(errorToText(error, t, t('web.error.unknown')), true);
    } finally {
      setBusy(false);
    }
  }, [bootMessage, loadThreadMessages, onStatus, projectId, refreshChatThreads, t]);

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
        thread_id: activeAgentThreadId || undefined,
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
    const threadId = String(activeAgentThreadId || '').trim();
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
    const threadId = String(activeAgentThreadId || '').trim();
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
      if (action === 'confirm_yes' || action === 'satisfied') {
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

  const loadProposalQueue = useCallback(async () => {
    const threadId = String(activeAgentThreadId || agentSession?.thread_id || '').trim();
    if (!threadId) {
      return;
    }
    setProposalBusy(true);
    try {
      const payload = await listAgentSettingProposals(threadId, 'pending_review');
      setProposalQueue(payload.setting_proposals || []);
    } catch (error) {
      onStatus?.(errorToText(error, t, t('web.error.unknown')), true);
    } finally {
      setProposalBusy(false);
    }
  }, [activeAgentThreadId, agentSession?.thread_id, onStatus, t]);

  const reviewProposal = async (proposalId: string, action: 'approve' | 'reject') => {
    const threadId = String(activeAgentThreadId || '').trim();
    const cleanProposal = String(proposalId || '').trim();
    if (!threadId || !cleanProposal) {
      onStatus?.(t('web.chat.agent.thread_required'), true);
      return;
    }
    setProposalBusy(true);
    try {
      const payload = await reviewAgentSettingProposal({
        thread_id: threadId,
        proposal_id: cleanProposal,
        action,
        decision_id: makeDecisionId('d-proposal'),
        expected_state_version: agentSession?.state_version,
      });
      applySessionPayload(payload);
      await loadProposalQueue();
    } catch (error) {
      onStatus?.(errorToText(error, t, t('web.error.unknown')), true);
    } finally {
      setProposalBusy(false);
    }
  };

  const deferCurrentProposal = async () => {
    await submitSessionDecision('defer_setting_update');
    void loadProposalQueue();
  };

  useEffect(() => {
    if (sessionStatus === 'AWAITING_SETTING_PROPOSAL_CONFIRM') {
      void loadProposalQueue();
      return;
    }
    setProposalQueue([]);
  }, [loadProposalQueue, sessionStatus]);

  const setAllDiffDecision = useCallback(
    (decision: 'accept' | 'reject') => {
      const next: Record<string, 'accept' | 'reject'> = {};
      for (const hunk of sessionDiffHunks) {
        const hunkId = String(hunk.hunk_id || '').trim();
        if (!hunkId) {
          continue;
        }
        next[hunkId] = decision;
      }
      setDiffDecisions(next);
    },
    [sessionDiffHunks],
  );

  useEffect(() => {
    if (sessionDiffHunks.length === 0) {
      setDiffDecisions({});
      setDiffEditedTexts({});
      return;
    }
    setDiffDecisions((prev) => {
      const next: Record<string, 'accept' | 'reject'> = {};
      for (const hunk of sessionDiffHunks) {
        const hunkId = String(hunk.hunk_id || '').trim();
        if (!hunkId) {
          continue;
        }
        next[hunkId] = prev[hunkId] || 'accept';
      }
      return next;
    });
    setDiffEditedTexts((prev) => {
      const next: Record<string, string> = {};
      for (const hunk of sessionDiffHunks) {
        const hunkId = String(hunk.hunk_id || '').trim();
        if (!hunkId) {
          continue;
        }
        if (Object.prototype.hasOwnProperty.call(prev, hunkId)) {
          next[hunkId] = prev[hunkId];
        } else {
          next[hunkId] = String(hunk.new_text || '');
        }
      }
      return next;
    });
  }, [sessionDiffHunks, sessionDiffPatch.diff_id]);

  const applyDiffReview = async () => {
    const threadId = String(activeAgentThreadId || '').trim();
    if (!threadId || !agentSession) {
      onStatus?.(t('web.chat.agent.thread_required'), true);
      return;
    }
    const diffId = String(sessionDiffPatch.diff_id || '').trim();
    if (!diffId) {
      onStatus?.(t('web.chat.agent.diff_patch_missing'), true);
      return;
    }

    const acceptedHunkIds: string[] = [];
    const rejectedHunkIds: string[] = [];
    const editedHunks: Array<{hunk_id: string; new_text: string}> = [];
    for (const hunk of sessionDiffHunks) {
      const hunkId = String(hunk.hunk_id || '').trim();
      if (!hunkId) {
        continue;
      }
      const decision = diffDecisions[hunkId] || 'accept';
      if (decision === 'reject') {
        rejectedHunkIds.push(hunkId);
        continue;
      }
      acceptedHunkIds.push(hunkId);
      const originalNewText = String(hunk.new_text || '');
      const editedText = Object.prototype.hasOwnProperty.call(diffEditedTexts, hunkId)
        ? diffEditedTexts[hunkId]
        : originalNewText;
      if (editedText !== originalNewText) {
        editedHunks.push({hunk_id: hunkId, new_text: editedText});
      }
    }

    setSessionBusy(true);
    try {
      const payload = await submitAgentDiffReview({
        thread_id: threadId,
        diff_id: diffId,
        decision_id: makeDecisionId('d-diff'),
        expected_base_revision: Number(sessionDiffPatch.base_revision || 0),
        expected_base_hash: String(sessionDiffPatch.base_content_hash || ''),
        expected_state_version: agentSession.state_version,
        accepted_hunk_ids: acceptedHunkIds,
        rejected_hunk_ids: rejectedHunkIds,
        edited_hunks: editedHunks,
      });
      applySessionPayload(payload);
      onStatus?.(
        acceptedHunkIds.length === 0
          ? t('web.chat.agent.diff_review_rejected_all')
          : t('web.chat.agent.diff_review_applied'),
        false,
      );
    } catch (error) {
      onStatus?.(errorToText(error, t, t('web.error.unknown')), true);
    } finally {
      setSessionBusy(false);
    }
  };

  const diffAcceptedCount = sessionDiffHunks.filter(
    (item) => (diffDecisions[String(item.hunk_id || '').trim()] || 'accept') === 'accept',
  ).length;
  const diffRejectedCount = Math.max(0, sessionDiffHunks.length - diffAcceptedCount);

  const selectChatThread = useCallback(
    async (nextThreadId: string) => {
      const clean = String(nextThreadId || '').trim();
      if (!clean) {
        await createNewConversation();
        return;
      }
      setChatThreadId(clean);
      setChatThreadProjectId(String(projectId || '').trim());
      setLastThreadForProject(projectId, clean);
      setRequestNote('');
      await loadThreadMessages(clean);
      try {
        const payload = await getAgentSession(clean);
        setAgentSession(payload.session);
      } catch {
        setAgentSession(null);
      }
    },
    [createNewConversation, loadThreadMessages, projectId],
  );

  return (
    <div
      onWheelCapture={handleAltWheelZoom}
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
            onClick={() => void createNewConversation()}
            title={t('web.chat.new_conversation')}
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
            onClick={() => void createNewConversation()}
            disabled={!projectId || threadsBusy}
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
        <div className="rounded-md border border-slate-200 bg-white p-2">
          <div className="flex items-center justify-between gap-2">
            <div className="font-semibold text-slate-700">Agent Session</div>
            <span className="rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 text-[10px] text-slate-600">
              {sessionStatusLabel}
            </span>
          </div>
          <div className="mt-1 text-[11px] text-slate-600">
            {t('web.chat.agent.session_pending_line', {
              chars: String(agentSession?.pending_content || '').length,
              count: pendingStateUpdateCount,
            })}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button
              onClick={() => void startSession()}
              disabled={sessionBusy || !projectId || !selectedNodeId}
              className="h-8 px-3 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-200 hover:bg-indigo-100 disabled:opacity-60"
            >
              {t('web.chat.agent.start_session')}
            </button>
            <button
              onClick={() => void refreshSession()}
              disabled={sessionBusy || !activeAgentThreadId}
              className="h-8 px-3 rounded-md border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-60"
            >
              {t('web.chat.agent.refresh')}
            </button>
            <button
              onClick={() => void stopGeneration()}
              disabled={sessionBusy || (!activeAgentThreadId && !busy && queuedInputCount === 0)}
              className="h-8 px-3 rounded-md border border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100 disabled:opacity-60 inline-flex items-center gap-1"
            >
              <Square size={12} />
              {t('web.chat.agent.stop')}
            </button>
          </div>
        </div>

        {toolCallPreview.length > 0 ? (
          <div className="rounded-md border border-slate-200 bg-slate-100/70 p-2">
            <button
              type="button"
              onClick={() => setToolBubbleCollapsed((prev) => !prev)}
              className="w-full flex items-center justify-between text-left text-slate-700"
            >
              <span className="truncate">LLM 正在调用 {String(toolCallPreview[toolCallPreview.length - 1]?.tool_name || 'tool')} 工具</span>
              {toolBubbleCollapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
            </button>
            <div className="mt-2 rounded border border-slate-200 bg-white p-2">
              <div className="font-semibold text-slate-700">执行计划</div>
              <div className="mt-1 space-y-1">
                {agentPlanSteps.map((step, index) => (
                  <div key={step.id} className="flex items-center justify-between gap-2 text-[10px] text-slate-600">
                    <span className="truncate">步骤 {index + 1}/{Math.max(1, agentPlanSteps.length)}：{step.title}</span>
                    <span className={cn(step.current ? 'text-amber-600' : step.done ? 'text-emerald-600' : 'text-slate-400')}>
                      {step.current ? '进行中' : step.done ? '已完成' : '待执行'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
            {!toolBubbleCollapsed ? (
              <pre className="mt-2 max-h-36 overflow-auto rounded border border-slate-200 bg-white p-2 text-[10px] leading-relaxed text-slate-600">
                {JSON.stringify(toolCallPreview, null, 2)}
              </pre>
            ) : null}
          </div>
        ) : null}

        {sessionStatus === 'AWAITING_CORRECTION_CONFIRM' && sessionDiffHunks.length > 0 ? (
          <div className="rounded-md border border-violet-200 bg-violet-50/40 p-2 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold text-violet-700">{t('web.chat.agent.diff_hunks', {count: sessionDiffHunks.length})}</span>
              <div className="text-[10px] text-violet-700">
                批准 {diffAcceptedCount} / 拒绝 {diffRejectedCount}
              </div>
            </div>
            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {sessionDiffHunks.map((hunk) => {
                const hunkId = String(hunk.hunk_id || '').trim();
                const decision = diffDecisions[hunkId] || 'accept';
                const oldText = String(hunk.old_text || '');
                const defaultNewText = String(hunk.new_text || '');
                const newText = Object.prototype.hasOwnProperty.call(diffEditedTexts, hunkId)
                  ? diffEditedTexts[hunkId]
                  : defaultNewText;
                const op = String(hunk.op || '').toUpperCase();
                const startLine = String(hunk.start_line || '');
                const endLine = String(hunk.end_line || '');
                return (
                  <div
                    key={hunkId}
                    className={cn(
                      'relative rounded-md border bg-white p-2',
                      decision === 'accept' ? 'border-emerald-200' : 'border-rose-200',
                    )}
                  >
                    <div className="absolute right-2 top-2 flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => setDiffDecisions((prev) => ({...prev, [hunkId]: 'accept'}))}
                        className={cn(
                          'h-5 px-1.5 rounded text-[10px] border',
                          decision === 'accept'
                            ? 'border-emerald-300 bg-emerald-50 text-emerald-700'
                            : 'border-slate-200 bg-white text-slate-500',
                        )}
                      >
                        ✓
                      </button>
                      <button
                        type="button"
                        onClick={() => setDiffDecisions((prev) => ({...prev, [hunkId]: 'reject'}))}
                        className={cn(
                          'h-5 px-1.5 rounded text-[10px] border',
                          decision === 'reject'
                            ? 'border-rose-300 bg-rose-50 text-rose-700'
                            : 'border-slate-200 bg-white text-slate-500',
                        )}
                      >
                        ✕
                      </button>
                    </div>
                    <div className="pr-16 space-y-1">
                      <div className="text-[10px] text-slate-500">{op} · L{startLine}-{endLine} · {hunkId.slice(-8)}</div>
                      {oldText ? (
                        <pre className="rounded border border-rose-100 bg-rose-50 px-2 py-1 text-[10px] leading-relaxed text-rose-700 whitespace-pre-wrap">
                          {oldText}
                        </pre>
                      ) : null}
                      <textarea
                        value={newText}
                        onChange={(event) =>
                          setDiffEditedTexts((prev) => ({...prev, [hunkId]: event.target.value}))
                        }
                        disabled={decision === 'reject'}
                        className="w-full min-h-[58px] rounded border border-emerald-100 bg-emerald-50 px-2 py-1 text-[10px] leading-relaxed text-emerald-800 resize-y disabled:opacity-60"
                      />
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setAllDiffDecision('accept')}
                className="h-7 px-2 rounded border border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
              >
                全部批准
              </button>
              <button
                type="button"
                onClick={() => setAllDiffDecision('reject')}
                className="h-7 px-2 rounded border border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100"
              >
                全部拒绝
              </button>
              <button
                type="button"
                onClick={() => void applyDiffReview()}
                disabled={sessionBusy || !activeAgentThreadId}
                className="h-7 px-3 rounded border border-violet-200 bg-violet-50 text-violet-700 hover:bg-violet-100 disabled:opacity-60"
              >
                {t('web.chat.agent.apply_diff_hunks')}
              </button>
            </div>
          </div>
        ) : null}

        {sessionStatus === 'AWAITING_SETTING_PROPOSAL_CONFIRM' ? (
          <div className="rounded-md border border-amber-200 bg-amber-50/50 p-2 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold text-amber-700">LLM 请求卡片：设定提案确认</span>
              <button
                type="button"
                onClick={() => void loadProposalQueue()}
                disabled={proposalBusy}
                className="h-7 px-2 rounded border border-amber-200 bg-white text-amber-700 hover:bg-amber-100 disabled:opacity-60"
              >
                {t('web.chat.agent.load_proposals')}
              </button>
            </div>
            {proposalQueue.length > 0 ? (
              <div className="space-y-1 max-h-40 overflow-y-auto pr-1">
                {proposalQueue.map((proposal) => {
                  const proposalId = String(proposal.id || '').trim();
                  const proposalType = String(proposal.proposal_type || t('web.chat.agent.proposal_unknown'));
                  const proposalStatus = String(proposal.status || t('web.chat.agent.proposal_pending'));
                  const proposalSummary = String(
                    proposal.summary || proposal.note || proposal.reason || proposal.delta || '',
                  ).trim();
                  return (
                    <div key={proposalId} className="rounded border border-amber-200 bg-white p-2 space-y-1">
                      <div className="text-[10px] text-slate-600">
                        {proposalId} [{proposalType} / {proposalStatus}]
                      </div>
                      {proposalSummary ? (
                        <div className="text-[11px] text-slate-700 whitespace-pre-wrap">{proposalSummary}</div>
                      ) : null}
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => void reviewProposal(proposalId, 'approve')}
                          disabled={proposalBusy}
                          className="h-7 px-2 rounded border border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 disabled:opacity-60"
                        >
                          {t('web.chat.agent.approve_proposal')}
                        </button>
                        <button
                          type="button"
                          onClick={() => void reviewProposal(proposalId, 'reject')}
                          disabled={proposalBusy}
                          className="h-7 px-2 rounded border border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100 disabled:opacity-60"
                        >
                          {t('web.chat.agent.reject_proposal')}
                        </button>
                        <button
                          type="button"
                          onClick={() => void deferCurrentProposal()}
                          disabled={proposalBusy || sessionBusy}
                          className="h-7 px-2 rounded border border-amber-200 bg-amber-100 text-amber-800 hover:bg-amber-200 disabled:opacity-60"
                        >
                          {t('web.chat.agent.defer_current')}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-slate-500">{t('web.chat.agent.no_pending_proposals')}</div>
            )}
          </div>
        ) : null}

        {(sessionStatus === 'AWAITING_CONFIRM' ||
          sessionStatus === 'AWAITING_CHAPTER_REVIEW' ||
          (sessionStatus === 'AWAITING_CORRECTION_CONFIRM' && sessionDiffHunks.length === 0)) ? (
          <div className="rounded-md border border-sky-200 bg-sky-50/40 p-2 space-y-2">
            <div className="font-semibold text-sky-700">LLM 请求卡片：确认交互</div>
            <textarea
              value={requestNote}
              onChange={(event) => setRequestNote(event.target.value)}
              placeholder={
                sessionStatus === 'AWAITING_CHAPTER_REVIEW'
                  ? t('web.chat.agent.placeholder_correction')
                  : t('web.chat.agent.placeholder_correction')
              }
              className="w-full min-h-[58px] rounded border border-sky-200 bg-white px-2 py-1 text-[11px] resize-y"
            />
            <div className="flex flex-wrap items-center gap-2">
              {sessionStatus === 'AWAITING_CHAPTER_REVIEW' ? (
                <>
                  <button
                    type="button"
                    onClick={() => void submitSessionDecision('satisfied')}
                    disabled={sessionBusy || !activeAgentThreadId}
                    className="h-8 px-3 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 disabled:opacity-60"
                  >
                    {t('web.chat.agent.chapter_satisfied')}
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      void submitSessionDecision('unsatisfied', {
                        correction: requestNote.trim() || t('web.chat.agent.default_correction_chapter'),
                      })
                    }
                    disabled={sessionBusy || !activeAgentThreadId}
                    className="h-8 px-3 rounded-md bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100 disabled:opacity-60"
                  >
                    {t('web.chat.agent.chapter_unsatisfied')}
                  </button>
                </>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => void submitSessionDecision('confirm_yes')}
                    disabled={sessionBusy || !activeAgentThreadId}
                    className="h-8 px-3 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 disabled:opacity-60"
                  >
                    {t('web.chat.agent.confirm_yes')}
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      void submitSessionDecision('correct', {
                        correction: requestNote.trim() || t('web.chat.agent.default_correction_confirm'),
                      })
                    }
                    disabled={sessionBusy || !activeAgentThreadId}
                    className="h-8 px-3 rounded-md bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100 disabled:opacity-60"
                  >
                    {t('web.chat.agent.correct')}
                  </button>
                </>
              )}
            </div>
          </div>
        ) : null}
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
                <MarkdownMessage content={msg.content} />
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
              disabled={!projectId}
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
              disabled={!input.trim() || !projectId}
              className="absolute right-2 bottom-2 p-1.5 bg-pink-500 text-white rounded-lg hover:bg-pink-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
            >
              <Send size={16} />
            </button>
          </div>
          <button
            type="button"
            onClick={() => void stopGeneration()}
            disabled={!busy && !isAgentRunning && queuedInputCount === 0 && !sessionBusy}
            className="h-11 px-3 rounded-xl border border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100 disabled:opacity-50 inline-flex items-center gap-1"
          >
            <Square size={14} />
            <span className="text-xs">⏹</span>
          </button>
        </form>
        <div className="mt-2 flex items-center justify-between text-[10px] text-slate-400 font-medium">
          <span>
            {queuedInputCount > 0 ? `队列中 ${queuedInputCount} 条` : t('web.chat.shift_enter_hint')}
            {' · '}
            {`Alt+Wheel ${Math.round(contentScale * 100)}%`}
          </span>
          <span>{busy || isAgentRunning ? t('web.chat.processing') : t('web.chat.endpoint_hint')}</span>
        </div>
      </div>
      </div>
      {!fullScreen ? (
        <>
          <div
            data-chat-no-drag="true"
            onPointerDown={startResize('nw')}
            className="absolute left-0 top-0 z-[60] h-5 w-5 cursor-nwse-resize touch-none"
          >
            <div className="absolute left-0 top-0 h-3 w-3 border-l border-t border-slate-300/80" />
          </div>
          <div
            data-chat-no-drag="true"
            onPointerDown={startResize('ne')}
            className="absolute right-0 top-0 z-[60] h-5 w-5 cursor-nesw-resize touch-none"
          >
            <div className="absolute right-0 top-0 h-3 w-3 border-r border-t border-slate-300/80" />
          </div>
          <div
            data-chat-no-drag="true"
            onPointerDown={startResize('sw')}
            className="absolute left-0 bottom-0 z-[60] h-5 w-5 cursor-nesw-resize touch-none"
          >
            <div className="absolute left-0 bottom-0 h-3 w-3 border-l border-b border-slate-300/80" />
          </div>
          <div
            data-chat-no-drag="true"
            onPointerDown={startResize('se')}
            className="absolute right-0 bottom-0 z-[60] h-5 w-5 cursor-nwse-resize touch-none"
          >
            <div className="absolute right-0 bottom-0 h-3 w-3 border-r border-b border-slate-300/80" />
          </div>
        </>
      ) : null}
    </div>
  );
}
