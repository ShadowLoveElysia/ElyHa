import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {Sidebar} from './components/Sidebar';
import {Header} from './components/Header';
import {Workspace} from './components/Workspace';
import {AIChat} from './components/AIChat';
import {KnowledgeGraph} from './components/KnowledgeGraph';
import {WindowDialog, type WindowDialogState} from './components/window';
import {SUPPORTED_LOCALES, loadLocaleDict, tFrom, type TranslationVars} from './i18n';
import {
  ApiTimeoutError,
  createLlmPreset,
  createRuntimeProfile,
  createEdge,
  createNode,
  createProject,
  createSnapshot,
  deleteLlmPreset,
  deleteEdge,
  deleteNode,
  deleteProject,
  fetchProjectInsights,
  generateChapter,
  getProjectBundle,
  getRuntimeSettings,
  listLlmPresets,
  listProjectCharacterStates,
  listProjectItemStates,
  listProjectRelationships,
  listProjects,
  listSnapshots,
  rollbackProject,
  renameLlmPreset,
  switchRuntimeProfile,
  updateNode,
  upsertProjectRelationship,
  updateProjectSettings,
  updateRuntimeSettings,
  validateProject,
} from './api';
import type {
  AiSuggestedOption,
  CharacterStatusPayload,
  CreateNodePayload,
  GraphEdgePayload,
  GraphNodePayload,
  ItemStatusPayload,
  LlmPresetPayload,
  ProjectInsights,
  ProjectPayload,
  RelationshipStatusPayload,
  RuntimeConfigPayload,
  RuntimeSettingsPayload,
  UpdateNodePayload,
  WorkflowMode,
} from './types';

const CORE_PROFILE_NAME = 'core';

function errorToText(
  error: unknown,
  translate: (key: string, vars?: TranslationVars) => string,
  fallback: string,
): string {
  if (error instanceof ApiTimeoutError) {
    return translate('web.error.request_timeout', {seconds: error.timeoutSeconds});
  }
  if (error instanceof Error) {
    return error.message;
  }
  return String(error || fallback);
}

function nodeMainText(metadata: unknown, emptyText: string): string {
  if (!metadata || typeof metadata !== 'object' || Array.isArray(metadata)) {
    return emptyText;
  }
  const record = metadata as Record<string, unknown>;
  const outline = typeof record.outline_markdown === 'string' ? record.outline_markdown : '';
  if (outline.trim()) {
    return outline;
  }
  const content = typeof record.content === 'string' ? record.content : '';
  if (content.trim()) {
    return content;
  }
  const summary = typeof record.summary === 'string' ? record.summary : '';
  if (summary.trim()) {
    return summary;
  }
  return emptyText;
}

interface NoticeState {
  text: string;
  error: boolean;
}

interface DialogResolve {
  confirmed: boolean;
  value: string;
}

interface RuntimeDraft {
  locale: string;
  llm_provider: string;
  preset_tag: string;
  llm_transport: 'httpx' | 'openai' | 'anthropic';
  api_url: string;
  api_key: string;
  api_key_mask: string;
  api_key_slot_masks: Record<string, string>;
  model_name: string;
  web_search_enabled: boolean;
  default_workflow_mode: WorkflowMode;
}

function toRuntimeDraft(config: RuntimeConfigPayload): RuntimeDraft {
  const workflowMode: WorkflowMode = config.default_workflow_mode === 'single' ? 'single' : 'multi_agent';
  const llmTransport = config.llm_transport === 'openai' || config.llm_transport === 'anthropic'
    ? config.llm_transport
    : 'httpx';
  const dynamicMask = typeof config.api_key_mask === 'string'
    ? config.api_key_mask
    : '';
  const slotMasks = config.api_key_slot_masks && typeof config.api_key_slot_masks === 'object'
    ? config.api_key_slot_masks
    : {};
  return {
    locale: config.locale,
    llm_provider: 'llmrequester',
    preset_tag: String(config.preset_tag || '').trim().toLowerCase(),
    llm_transport: llmTransport,
    api_url: config.api_url,
    api_key: '',
    api_key_mask: dynamicMask,
    api_key_slot_masks: slotMasks,
    model_name: config.model_name,
    web_search_enabled: config.web_search_enabled,
    default_workflow_mode: workflowMode,
  };
}

type GuideDocKey = 'clarify' | 'constitution' | 'plan' | 'specification';
type GuideDocSettingField =
  | 'clarify_markdown'
  | 'constitution_markdown'
  | 'plan_markdown'
  | 'specification_markdown';

const GUIDE_DOC_ORDER: GuideDocKey[] = ['clarify', 'constitution', 'plan', 'specification'];

const GUIDE_DOC_TITLES: Record<GuideDocKey, string> = {
  clarify: 'clarify.md',
  constitution: 'constitution.md',
  plan: 'plan.md',
  specification: 'specification.md',
};

const GUIDE_DOC_SETTING_FIELDS: Record<GuideDocKey, GuideDocSettingField> = {
  clarify: 'clarify_markdown',
  constitution: 'constitution_markdown',
  plan: 'plan_markdown',
  specification: 'specification_markdown',
};

const GUIDE_DOC_TITLE_SET = new Set(Object.values(GUIDE_DOC_TITLES).map((item) => item.toLowerCase()));

function normalizeGuideSkippedDocs(value: unknown): GuideDocSettingField[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const next: GuideDocSettingField[] = [];
  for (const item of value) {
    const raw = String(item || '').trim().toLowerCase();
    let normalized = '';
    if (raw === 'clarify' || raw === 'clarify_markdown') {
      normalized = 'clarify_markdown';
    } else if (raw === 'constitution' || raw === 'constitution_markdown') {
      normalized = 'constitution_markdown';
    } else if (raw === 'plan' || raw === 'plan_markdown') {
      normalized = 'plan_markdown';
    } else if (raw === 'specification' || raw === 'specification_markdown') {
      normalized = 'specification_markdown';
    }
    if (!normalized) {
      continue;
    }
    if (!next.includes(normalized as GuideDocSettingField)) {
      next.push(normalized as GuideDocSettingField);
    }
  }
  return next;
}

function normalizeGuideDocType(rawDocType: string): GuideDocSettingField | '' {
  const raw = String(rawDocType || '').trim().toLowerCase();
  if (raw === 'clarify' || raw === 'clarify_markdown') {
    return 'clarify_markdown';
  }
  if (raw === 'constitution' || raw === 'constitution_markdown') {
    return 'constitution_markdown';
  }
  if (raw === 'plan' || raw === 'plan_markdown') {
    return 'plan_markdown';
  }
  if (raw === 'specification' || raw === 'specification_markdown') {
    return 'specification_markdown';
  }
  return '';
}

function normalizeText(value: unknown): string {
  if (typeof value === 'string') {
    return value.trim();
  }
  return '';
}

function shortenText(text: string, max = 140): string {
  const normalized = String(text || '').trim();
  if (!normalized) {
    return '';
  }
  if (normalized.length <= max) {
    return normalized;
  }
  return `${normalized.slice(0, max)}...`;
}

function parseGuideDocsFromReply(rawReply: string): Record<GuideDocKey, string> | null {
  const raw = String(rawReply || '').trim();
  if (!raw) {
    return null;
  }

  const candidates: string[] = [];
  const jsonFence = raw.match(/```json\s*([\s\S]*?)```/i);
  const anyFence = raw.match(/```\s*([\s\S]*?)```/i);
  if (jsonFence?.[1]) {
    candidates.push(jsonFence[1].trim());
  }
  if (anyFence?.[1]) {
    candidates.push(anyFence[1].trim());
  }
  candidates.push(raw);
  const firstBrace = raw.indexOf('{');
  const lastBrace = raw.lastIndexOf('}');
  if (firstBrace >= 0 && lastBrace > firstBrace) {
    candidates.push(raw.slice(firstBrace, lastBrace + 1).trim());
  }

  for (const candidate of candidates) {
    try {
      const parsed = JSON.parse(candidate) as unknown;
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        continue;
      }
      const record = parsed as Record<string, unknown>;
      const clarify = normalizeText(record.clarify ?? record['clarify.md']);
      const constitution = normalizeText(record.constitution ?? record['constitution.md']);
      const plan = normalizeText(record.plan ?? record['plan.md']);
      const specification = normalizeText(record.specification ?? record['specification.md']);
      if (!clarify && !constitution && !plan && !specification) {
        continue;
      }
      return {clarify, constitution, plan, specification};
    } catch {
      continue;
    }
  }
  return null;
}

export default function App() {
  const [activeTab, setActiveTab] = useState('workspace');
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [chatResetVersion, setChatResetVersion] = useState(0);

  const [projects, setProjects] = useState<ProjectPayload[]>([]);
  const [projectId, setProjectId] = useState('');
  const [project, setProject] = useState<ProjectPayload | null>(null);
  const [nodes, setNodes] = useState<GraphNodePayload[]>([]);
  const [edges, setEdges] = useState<GraphEdgePayload[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState('');
  const [outlinePreviewTarget, setOutlinePreviewTarget] = useState<'selected' | 'global' | GuideDocKey>('global');
  const [linkMode, setLinkMode] = useState(false);
  const [linkSourceNodeId, setLinkSourceNodeId] = useState('');

  const [busyCount, setBusyCount] = useState(0);
  const [notice, setNotice] = useState<NoticeState | null>(null);
  const [dialog, setDialog] = useState<WindowDialogState | null>(null);
  const dialogResolverRef = useRef<((result: DialogResolve) => void) | null>(null);

  const [insights, setInsights] = useState<ProjectInsights | null>(null);
  const [relationshipRows, setRelationshipRows] = useState<RelationshipStatusPayload[]>([]);
  const [characterStateRows, setCharacterStateRows] = useState<CharacterStatusPayload[]>([]);
  const [itemStateRows, setItemStateRows] = useState<ItemStatusPayload[]>([]);
  const [insightsLoading, setInsightsLoading] = useState(false);

  const [runtimeSettings, setRuntimeSettings] = useState<RuntimeSettingsPayload | null>(null);
  const [settingsDraft, setSettingsDraft] = useState<RuntimeDraft>({
    locale: 'zh',
    llm_provider: 'llmrequester',
    preset_tag: '',
    llm_transport: 'httpx',
    api_url: '',
    api_key: '',
    api_key_mask: '',
    api_key_slot_masks: {},
    model_name: '',
    web_search_enabled: false,
    default_workflow_mode: 'multi_agent',
  });
  const [llmPresets, setLlmPresets] = useState<LlmPresetPayload[]>([]);
  const [selectedPresetScheme, setSelectedPresetScheme] = useState('custom');
  const [locale, setLocale] = useState('zh');
  const [dict, setDict] = useState<Record<string, string>>({});

  const busy = busyCount > 0;

  const t = useCallback(
    (key: string, vars?: TranslationVars) => {
      return tFrom(dict, key, vars);
    },
    [dict],
  );

  const localeLabel = useMemo(() => {
    return SUPPORTED_LOCALES.find((item) => item.value === locale)?.label || locale;
  }, [locale]);

  const workflowModeOptions = useMemo<Array<{value: WorkflowMode; label: string}>>(
    () => [
      {value: 'single', label: t('web.option.workflow_mode.single')},
      {value: 'multi_agent', label: t('web.option.workflow_mode.multi_agent')},
    ],
    [t],
  );

  const setStatus = useCallback((text: string, error = false) => {
    setNotice({text, error});
  }, []);

  const resolveDialog = useCallback((result: DialogResolve) => {
    const resolver = dialogResolverRef.current;
    dialogResolverRef.current = null;
    setDialog(null);
    if (resolver) {
      resolver(result);
    }
  }, []);

  const askConfirm = useCallback(
    async (title: string, message: string, danger = false): Promise<boolean> => {
      return new Promise<boolean>((resolve) => {
        if (dialogResolverRef.current) {
          dialogResolverRef.current({confirmed: false, value: ''});
        }
        dialogResolverRef.current = (result) => resolve(result.confirmed);
        setDialog({
          type: 'confirm',
          title,
          message,
          danger,
          confirmText: danger ? t('web.modal.confirm_delete') : t('web.modal.confirm'),
          cancelText: t('web.modal.cancel'),
        });
      });
    },
    [t],
  );

  const handleWorkflowModeDraftChange = useCallback(
    async (nextMode: WorkflowMode) => {
      const currentMode = settingsDraft.default_workflow_mode;
      if (nextMode === currentMode) {
        return;
      }
      const currentLabel = workflowModeOptions.find((item) => item.value === currentMode)?.label || currentMode;
      const nextLabel = workflowModeOptions.find((item) => item.value === nextMode)?.label || nextMode;
      const confirmed = await askConfirm(
        t('web.modal.workflow_mode_switch_title'),
        t('web.modal.workflow_mode_switch_body', {from: currentLabel, to: nextLabel}),
      );
      if (!confirmed) {
        return;
      }
      setSettingsDraft((prev) => ({
        ...prev,
        default_workflow_mode: nextMode,
      }));
      setChatResetVersion((value) => value + 1);
    },
    [askConfirm, settingsDraft.default_workflow_mode, t, workflowModeOptions],
  );

  const askPrompt = useCallback(
    async (options: {
      title: string;
      message?: string;
      defaultValue?: string;
      placeholder?: string;
      multiline?: boolean;
    }): Promise<string | null> => {
      return new Promise<string | null>((resolve) => {
        if (dialogResolverRef.current) {
          dialogResolverRef.current({confirmed: false, value: ''});
        }
        dialogResolverRef.current = (result) => resolve(result.confirmed ? result.value : null);
        setDialog({
          type: 'prompt',
          title: options.title,
          message: options.message,
          defaultValue: options.defaultValue || '',
          placeholder: options.placeholder || '',
          multiline: options.multiline,
          confirmText: t('web.modal.confirm'),
          cancelText: t('web.modal.cancel'),
        });
      });
    },
    [t],
  );

  const askSelect = useCallback(
    async (options: {
      title: string;
      message?: string;
      defaultValue?: string;
      choices: Array<{value: string; label: string}>;
    }): Promise<string | null> => {
      return new Promise<string | null>((resolve) => {
        if (dialogResolverRef.current) {
          dialogResolverRef.current({confirmed: false, value: ''});
        }
        const fallback = options.defaultValue || options.choices[0]?.value || '';
        dialogResolverRef.current = (result) => resolve(result.confirmed ? result.value : null);
        setDialog({
          type: 'select',
          title: options.title,
          message: options.message,
          defaultValue: fallback,
          options: options.choices,
          confirmText: t('web.modal.confirm'),
          cancelText: t('web.modal.cancel'),
        });
      });
    },
    [t],
  );

  useEffect(() => {
    if (!notice) {
      return;
    }
    const timer = window.setTimeout(() => {
      setNotice((current) => (current === notice ? null : current));
    }, 5200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const execute = useCallback(
    async (task: () => Promise<void>, failPrefix: string) => {
      setBusyCount((value) => value + 1);
      try {
        await task();
      } catch (error) {
        setStatus(`${failPrefix}: ${errorToText(error, t, t('web.error.unknown'))}`, true);
      } finally {
        setBusyCount((value) => Math.max(0, value - 1));
      }
    },
    [setStatus, t],
  );

  const applyLocale = useCallback(async (targetLocale: string) => {
    const normalized = (targetLocale || '').trim() || 'zh';
    const loaded = await loadLocaleDict(normalized);
    setDict(loaded);
    setLocale(normalized);
  }, []);

  const applyRuntimeSettings = useCallback((payload: RuntimeSettingsPayload) => {
    setRuntimeSettings(payload);
    setSettingsDraft(toRuntimeDraft(payload.config));
    const presetTag = String(payload.config.preset_tag || '').trim().toLowerCase();
    setSelectedPresetScheme(presetTag ? `preset:${presetTag}` : 'custom');
  }, []);

  const loadLlmPresetList = useCallback(async () => {
    const presets = await listLlmPresets();
    setLlmPresets(presets);
  }, []);

  useEffect(() => {
    void applyLocale('zh');
  }, [applyLocale]);

  const refreshProjects = useCallback(async (preferredId?: string) => {
    const list = await listProjects();
    setProjects(list);
    setProjectId((current) => {
      if (preferredId && list.some((item) => item.id === preferredId)) {
        return preferredId;
      }
      if (current && list.some((item) => item.id === current)) {
        return current;
      }
      return list[0]?.id || '';
    });
  }, []);

  const loadProjectBundle = useCallback(async (targetProjectId: string) => {
    const bundle = await getProjectBundle(targetProjectId);
    setProject(bundle.project);
    setNodes(bundle.nodes);
    setEdges(bundle.edges);
  }, []);

  const refreshCurrentProject = useCallback(async () => {
    if (!projectId) {
      return;
    }
    await execute(async () => {
      await loadProjectBundle(projectId);
      setStatus(t('web.toast.workspace_refreshed'));
    }, t('web.error.workspace_refresh_failed'));
  }, [execute, loadProjectBundle, projectId, setStatus]);

  useEffect(() => {
    void execute(async () => {
      await refreshProjects();
    }, t('web.error.project_list_load_failed'));
  }, [execute, refreshProjects]);

  useEffect(() => {
    if (!projectId) {
      setProject(null);
      setNodes([]);
      setEdges([]);
      setSelectedNodeId('');
      setLinkSourceNodeId('');
      return;
    }
    void execute(async () => {
      await loadProjectBundle(projectId);
    }, t('web.error.project_load_failed'));
  }, [execute, loadProjectBundle, projectId]);

  useEffect(() => {
    if (!selectedNodeId) {
      return;
    }
    if (!nodes.some((item) => item.id === selectedNodeId)) {
      setSelectedNodeId('');
    }
  }, [nodes, selectedNodeId]);

  useEffect(() => {
    if (!linkSourceNodeId) {
      return;
    }
    if (!nodes.some((item) => item.id === linkSourceNodeId)) {
      setLinkSourceNodeId('');
    }
  }, [linkSourceNodeId, nodes]);

  const selectedNode = useMemo(() => {
    return nodes.find((item) => item.id === selectedNodeId) || null;
  }, [nodes, selectedNodeId]);

  const linkSourceNodeTitle = useMemo(() => {
    if (!linkSourceNodeId) {
      return '';
    }
    return nodes.find((item) => item.id === linkSourceNodeId)?.title || '';
  }, [linkSourceNodeId, nodes]);

  const guideDocStatus = useMemo(
    () => {
      const skipped = new Set<GuideDocSettingField>(
        normalizeGuideSkippedDocs(project?.settings?.guide_skipped_docs),
      );
      return GUIDE_DOC_ORDER.map((key) => {
        const field = GUIDE_DOC_SETTING_FIELDS[key];
        const content = normalizeText(project?.settings?.[field]);
        return {
          key,
          title: GUIDE_DOC_TITLES[key],
          filled: Boolean(content) || skipped.has(field),
        };
      });
    },
    [project],
  );

  const guideOutlineCards = useMemo(
    () => {
      const skipped = new Set<GuideDocSettingField>(
        normalizeGuideSkippedDocs(project?.settings?.guide_skipped_docs),
      );
      return GUIDE_DOC_ORDER.map((key) => {
        const field = GUIDE_DOC_SETTING_FIELDS[key];
        const content = normalizeText(project?.settings?.[field]);
        return {
          key,
          title: GUIDE_DOC_TITLES[key],
          content,
          filled: Boolean(content) || skipped.has(field),
        };
      });
    },
    [project],
  );

  const globalOutlineText = useMemo(() => normalizeText(project?.settings?.global_directives), [project]);

  const outlinePreviewContent = useMemo(() => {
    if (outlinePreviewTarget === 'global') {
      return {
        title: t('web.chat.context_global'),
        content: globalOutlineText || t('web.outline.node_empty'),
      };
    }
    if (outlinePreviewTarget === 'selected') {
      return {
        title: selectedNode ? selectedNode.title : t('web.outline.select_node_hint'),
        content: selectedNode ? nodeMainText(selectedNode.metadata, t('web.outline.node_empty')) : t('web.outline.select_node_hint'),
      };
    }
    const card = guideOutlineCards.find((item) => item.key === outlinePreviewTarget);
    if (!card) {
      return {
        title: t('web.outline.select_node_hint'),
        content: t('web.outline.select_node_hint'),
      };
    }
    return {
      title: card.title,
      content: card.content || t('web.guide.docs_empty_fallback', {name: card.title}),
    };
  }, [globalOutlineText, guideOutlineCards, outlinePreviewTarget, selectedNode, t]);

  useEffect(() => {
    if (outlinePreviewTarget === 'selected' && !selectedNode) {
      setOutlinePreviewTarget('global');
    }
  }, [outlinePreviewTarget, selectedNode]);

  const guideDocsComplete = useMemo(() => guideDocStatus.every((item) => item.filled), [guideDocStatus]);

  const hasStoryProgress = useMemo(() => {
    if (edges.length > 0) {
      return true;
    }
    return nodes.some((node) => {
      const lowered = String(node.title || '').trim().toLowerCase();
      if (!GUIDE_DOC_TITLE_SET.has(lowered)) {
        return true;
      }
      return false;
    });
  }, [edges.length, nodes]);

  const shouldShowGuideWorkspace = useMemo(() => {
    if (activeTab !== 'workspace') {
      return false;
    }
    if (!projectId) {
      return false;
    }
    return !guideDocsComplete;
  }, [activeTab, guideDocsComplete, projectId]);

  useEffect(() => {
    if (!shouldShowGuideWorkspace) {
      return;
    }
    setIsChatOpen(true);
  }, [shouldShowGuideWorkspace]);

  const handleCreateProject = useCallback(
    async (title: string) => {
      await execute(async () => {
        const created = await createProject(title.trim());
        await refreshProjects(created.id);
        await loadProjectBundle(created.id);
        setStatus(t('web.toast.project_created', {title: created.title}));
      }, t('web.error.project_create_failed'));
    },
    [execute, loadProjectBundle, refreshProjects, setStatus, t],
  );

  const handleDeleteProject = useCallback(
    async (targetProjectId: string) => {
      await execute(async () => {
        await deleteProject(targetProjectId);
        await refreshProjects();
        setStatus(t('web.toast.project_deleted'));
      }, t('web.error.project_delete_failed'));
    },
    [execute, refreshProjects, setStatus, t],
  );

  const handleQuickCreateNode = useCallback(async () => {
    if (!projectId) {
      setStatus(t('web.toast.project_required'), true);
      return;
    }
    await execute(async () => {
      const created = await createNode(projectId, {
        title: t('web.node.quick_create_title'),
        type: 'chapter',
        metadata: {
          content: '',
          summary: '',
        },
      });
      await loadProjectBundle(projectId);
      setSelectedNodeId(created.id);
      setStatus(t('web.toast.node_created'));
    }, t('web.error.node_create_failed'));
  }, [execute, loadProjectBundle, projectId, setStatus, t]);

  const handleCreateNode = useCallback(
    async (payload: CreateNodePayload) => {
      if (!projectId) {
        setStatus(t('web.toast.project_required'), true);
        return;
      }
      await execute(async () => {
        const created = await createNode(projectId, payload);
        await loadProjectBundle(projectId);
        setSelectedNodeId(created.id);
      }, t('web.error.node_create_failed'));
    },
    [execute, loadProjectBundle, projectId, setStatus, t],
  );

  const handleUpdateNode = useCallback(
    async (nodeId: string, payload: UpdateNodePayload) => {
      if (!projectId) {
        setStatus(t('web.toast.project_required'), true);
        return;
      }
      await execute(async () => {
        const updated = await updateNode(projectId, nodeId, payload);
        setNodes((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      }, t('web.error.node_update_failed'));
    },
    [execute, projectId, setStatus, t],
  );

  const handleDeleteNode = useCallback(
    async (nodeId: string) => {
      if (!projectId) {
        setStatus(t('web.toast.project_required'), true);
        return;
      }
      await execute(async () => {
        await deleteNode(projectId, nodeId);
        setNodes((prev) => prev.filter((item) => item.id !== nodeId));
        setEdges((prev) => prev.filter((item) => item.source_id !== nodeId && item.target_id !== nodeId));
      }, t('web.error.node_delete_failed'));
    },
    [execute, projectId, setStatus, t],
  );

  const handleCreateEdge = useCallback(
    async (sourceId: string, targetId: string, label = '') => {
      if (!projectId) {
        setStatus(t('web.toast.project_required'), true);
        return;
      }
      await execute(async () => {
        const created = await createEdge(projectId, sourceId, targetId, label);
        setEdges((prev) => [...prev, created]);
      }, t('web.error.edge_create_failed'));
    },
    [execute, projectId, setStatus, t],
  );

  const handleDeleteEdge = useCallback(
    async (edgeId: string) => {
      if (!projectId) {
        setStatus(t('web.toast.project_required'), true);
        return;
      }
      await execute(async () => {
        await deleteEdge(projectId, edgeId);
        setEdges((prev) => prev.filter((item) => item.id !== edgeId));
      }, t('web.error.edge_delete_failed'));
    },
    [execute, projectId, setStatus, t],
  );

  const handleDeleteEdgeBetween = useCallback(
    async (leftNodeId: string, rightNodeId: string) => {
      if (!projectId) {
        setStatus(t('web.toast.project_required'), true);
        return;
      }
      await execute(async () => {
        const candidates = edges.filter(
          (edge) =>
            (edge.source_id === leftNodeId && edge.target_id === rightNodeId) ||
            (edge.source_id === rightNodeId && edge.target_id === leftNodeId),
        );
        if (candidates.length === 0) {
          setStatus(t('web.toast.link_pair_not_found'));
          return;
        }
        for (const edge of candidates) {
          await deleteEdge(projectId, edge.id);
        }
        const removedIds = new Set(candidates.map((item) => item.id));
        setEdges((prev) => prev.filter((item) => !removedIds.has(item.id)));
        const fromTitle = nodes.find((item) => item.id === leftNodeId)?.title || leftNodeId;
        const toTitle = nodes.find((item) => item.id === rightNodeId)?.title || rightNodeId;
        setStatus(t('web.toast.link_pair_removed', {from: fromTitle, to: toTitle}));
      }, t('web.toast.link_remove_failed'));
    },
    [edges, execute, nodes, projectId, setStatus, t],
  );

  const toggleLinkMode = useCallback(() => {
    setLinkMode((prev) => {
      const next = !prev;
      if (!next) {
        setLinkSourceNodeId('');
        setStatus(t('web.toast.link_mode_disabled'));
      } else {
        setStatus(t('web.toast.link_mode_enabled'));
      }
      return next;
    });
  }, [setStatus, t]);

  const handleWorkspaceSelect = useCallback((nodeId: string) => {
    setSelectedNodeId(nodeId || '');
  }, []);

  const handleLinkNodeLeftClick = useCallback(
    async (nodeId: string) => {
      if (!nodeId) {
        return;
      }

      setSelectedNodeId(nodeId);
      if (!linkMode || !projectId) {
        return;
      }

      if (!linkSourceNodeId || linkSourceNodeId === nodeId) {
        setLinkSourceNodeId(nodeId);
        const title = nodes.find((item) => item.id === nodeId)?.title || nodeId;
        setStatus(t('web.toast.link_source_selected', {node: title}));
        return;
      }

      const duplicated = edges.some((edge) => edge.source_id === linkSourceNodeId && edge.target_id === nodeId);
      if (duplicated) {
        setStatus(t('web.toast.link_exists'));
        setLinkSourceNodeId(nodeId);
        return;
      }

      await handleCreateEdge(linkSourceNodeId, nodeId);
      setLinkSourceNodeId(nodeId);
      const fromTitle = nodes.find((item) => item.id === linkSourceNodeId)?.title || linkSourceNodeId;
      const toTitle = nodes.find((item) => item.id === nodeId)?.title || nodeId;
      setStatus(t('web.toast.link_created', {from: fromTitle, to: toTitle}));
    },
    [edges, handleCreateEdge, linkMode, linkSourceNodeId, nodes, projectId, setStatus, t],
  );

  const handleLinkNodeRightClick = useCallback(
    async (nodeId: string) => {
      if (!nodeId) {
        return;
      }

      setSelectedNodeId(nodeId);
      if (!linkMode || !projectId) {
        return;
      }

      if (!linkSourceNodeId || linkSourceNodeId === nodeId) {
        setLinkSourceNodeId(nodeId);
        const title = nodes.find((item) => item.id === nodeId)?.title || nodeId;
        setStatus(t('web.toast.unlink_source_selected', {node: title}));
        return;
      }

      await handleDeleteEdgeBetween(linkSourceNodeId, nodeId);
      setLinkSourceNodeId(nodeId);
    },
    [handleDeleteEdgeBetween, linkMode, linkSourceNodeId, nodes, projectId, setStatus, t],
  );

  const handleSnapshot = useCallback(async () => {
    if (!projectId) {
      setStatus(t('web.toast.project_required'), true);
      return;
    }
    await execute(async () => {
      const snap = await createSnapshot(projectId);
      setStatus(t('web.toast.snapshot', {revision: snap.revision}));
      await loadProjectBundle(projectId);
    }, t('web.error.snapshot_save_failed'));
  }, [execute, loadProjectBundle, projectId, setStatus, t]);

  const handleRollback = useCallback(async () => {
    if (!projectId || !project) {
      setStatus(t('web.toast.project_required'), true);
      return;
    }
    await execute(async () => {
      const snapshots = await listSnapshots(projectId);
      const activeRevision = project.active_revision;
      const target = snapshots
        .filter((item) => item.revision < activeRevision)
        .sort((a, b) => b.revision - a.revision)[0];
      if (!target) {
        setStatus(t('web.toast.rollback_snapshot_missing'));
        return;
      }
      await rollbackProject(projectId, target.revision);
      await loadProjectBundle(projectId);
      setStatus(t('web.toast.rolled_back', {revision: target.revision}));
    }, t('web.error.rollback_failed'));
  }, [execute, loadProjectBundle, project, projectId, setStatus, t]);

  const handleValidate = useCallback(async () => {
    if (!projectId) {
      setStatus(t('web.toast.project_required'), true);
      return;
    }
    await execute(async () => {
      const report = await validateProject(projectId);
      setStatus(
        t('web.toast.validation_done', {
          errors: report.errors,
          warnings: report.warnings,
          infos: report.infos,
        }),
      );
    }, t('web.error.validation_failed'));
  }, [execute, projectId, setStatus, t]);

  const generateNodeById = useCallback(
    async (nodeId: string) => {
      if (!projectId || !nodeId) {
        setStatus(t('web.toast.node_required'), true);
        return;
      }
      await execute(async () => {
        const result = await generateChapter(
          projectId,
          nodeId,
          2200,
          settingsDraft.default_workflow_mode,
        );
        await loadProjectBundle(projectId);
        setStatus(
          t('web.toast.generate_done', {
            provider: result.provider,
            revision: result.revision,
          }),
        );
      }, t('web.error.generate_node_failed'));
    },
    [execute, loadProjectBundle, projectId, setStatus, settingsDraft.default_workflow_mode, t],
  );

  const handleGenerateSelected = useCallback(async () => {
    if (!selectedNodeId) {
      setStatus(t('web.toast.node_required'), true);
      return;
    }
    await generateNodeById(selectedNodeId);
  }, [generateNodeById, selectedNodeId, setStatus, t]);

  const handleCreateSuggestionNode = useCallback(
    async (option: AiSuggestedOption) => {
      if (!projectId) {
        setStatus(t('web.toast.project_required'), true);
        return;
      }
      await execute(async () => {
        if (option.suggested_node_id) {
          await loadProjectBundle(projectId);
          setSelectedNodeId(option.suggested_node_id);
          return;
        }
        const content = option.description || option.summary || '';
        const metadata: Record<string, unknown> = {
          content,
          summary: (option.summary || content).slice(0, 200),
        };
        if (option.outline_steps) {
          metadata.outline_markdown = option.outline_steps;
        }
        const created = await createNode(projectId, {
          title: option.title || t('web.chat.suggestion_node_default_title'),
          type: 'chapter',
          metadata,
        });
        setNodes((prev) => [...prev, created]);
        setSelectedNodeId(created.id);
      }, t('web.error.suggestion_create_failed'));
    },
    [execute, loadProjectBundle, projectId, setStatus, t],
  );

  const handleGuideDocReply = useCallback(
    async (reply: string) => {
      if (!projectId) {
        return;
      }
      try {
        const parsed = parseGuideDocsFromReply(reply);
        if (!parsed) {
          return;
        }

        let changedCount = 0;
        const patch: Partial<Record<GuideDocSettingField, string>> = {};
        for (const key of GUIDE_DOC_ORDER) {
          const title = GUIDE_DOC_TITLES[key];
          const field = GUIDE_DOC_SETTING_FIELDS[key];
          const nextContent = (parsed[key] || '').trim();
          if (!nextContent) {
            continue;
          }

          const currentContent = normalizeText(project?.settings?.[field]);
          if (currentContent === nextContent) {
            continue;
          }

          const preview = nextContent.slice(0, 600);
          const warning = hasStoryProgress ? t('web.guide.modify_after_progress_inline_warning') : '';
          const confirmed = await askConfirm(
            t('web.guide.doc_update_confirm_title', {name: title}),
            t('web.guide.doc_update_confirm_body', {name: title, preview, warning}),
          );
          if (!confirmed) {
            continue;
          }

          patch[field] = nextContent;
          changedCount += 1;
        }

        if (changedCount > 0) {
          await updateProjectSettings(projectId, patch);
          await loadProjectBundle(projectId);
          setStatus(t('web.guide.docs_written_count', {count: changedCount}));
        }
      } catch (error) {
        setStatus(`${t('web.error.guide_docs_write_failed')}: ${errorToText(error, t, t('web.error.unknown'))}`, true);
      }
    },
    [askConfirm, hasStoryProgress, loadProjectBundle, project, projectId, setStatus, t],
  );

  const handleGuideSkipDocumentRequest = useCallback(
    async (docType: string): Promise<boolean> => {
      if (!projectId) {
        return false;
      }
      const field = normalizeGuideDocType(docType);
      if (!field) {
        return false;
      }
      const key = GUIDE_DOC_ORDER.find((item) => GUIDE_DOC_SETTING_FIELDS[item] === field);
      if (!key) {
        return false;
      }
      const title = GUIDE_DOC_TITLES[key];
      const confirmed = await askConfirm(
        t('web.guide.skip_confirm_title'),
        t('web.guide.skip_confirm_body', {name: title}),
      );
      if (!confirmed) {
        return false;
      }
      const nextSkipped = normalizeGuideSkippedDocs(project?.settings?.guide_skipped_docs);
      if (!nextSkipped.includes(field)) {
        nextSkipped.push(field);
      }
      await updateProjectSettings(projectId, {
        guide_skipped_docs: nextSkipped,
      });
      await loadProjectBundle(projectId);
      setStatus(t('web.guide.skip_confirmed', {name: title}));
      return true;
    },
    [askConfirm, loadProjectBundle, project, projectId, setStatus, t],
  );

  const refreshInsights = useCallback(async () => {
    if (!projectId) {
      setInsights(null);
      setRelationshipRows([]);
      setCharacterStateRows([]);
      setItemStateRows([]);
      return;
    }
    setInsightsLoading(true);
    try {
      const [insightPayload, relationshipPayload, characterPayload, itemPayload] = await Promise.all([
        fetchProjectInsights(projectId),
        listProjectRelationships(projectId),
        listProjectCharacterStates(projectId),
        listProjectItemStates(projectId),
      ]);
      setInsights(insightPayload);
      setRelationshipRows(relationshipPayload.relationships || []);
      setCharacterStateRows(characterPayload.characters || []);
      setItemStateRows(itemPayload.items || []);
    } catch (error) {
      setStatus(`${t('web.error.graph_load_failed')}: ${errorToText(error, t, t('web.error.unknown'))}`, true);
    } finally {
      setInsightsLoading(false);
    }
  }, [projectId, setStatus, t]);

  const handleUpsertRelationship = useCallback(
    async (payload: {
      subject_character_id: string;
      object_character_id: string;
      relation_type: string;
      source_excerpt?: string;
    }): Promise<boolean> => {
      if (!projectId) {
        setStatus(t('web.toast.project_required'), true);
        return false;
      }
      const subject = String(payload.subject_character_id || '').trim();
      const object_ = String(payload.object_character_id || '').trim();
      const relation = String(payload.relation_type || '').trim();
      if (!subject || !object_ || !relation) {
        setStatus(t('web.insight.relationship_edit_invalid'), true);
        return false;
      }
      const confirmed = await askConfirm(
        t('web.insight.relationship_edit_confirm_title'),
        t('web.insight.relationship_edit_confirm_body', {subject, object: object_, relation}),
      );
      if (!confirmed) {
        return false;
      }
      try {
        await upsertProjectRelationship({
          project_id: projectId,
          subject_character_id: subject,
          object_character_id: object_,
          relation_type: relation,
          node_id: selectedNodeId || undefined,
          source_excerpt: payload.source_excerpt || '',
          confidence: 1.0,
        });
        await refreshInsights();
        setStatus(t('web.insight.relationship_edit_saved', {subject, object: object_}));
        return true;
      } catch (error) {
        setStatus(
          `${t('web.insight.relationship_edit_failed')}: ${errorToText(error, t, t('web.error.unknown'))}`,
          true,
        );
        return false;
      }
    },
    [askConfirm, projectId, refreshInsights, selectedNodeId, setStatus, t],
  );

  useEffect(() => {
    if (activeTab !== 'graph' || !projectId) {
      return;
    }
    void refreshInsights();
  }, [activeTab, projectId, refreshInsights]);

  const loadRuntimeSettings = useCallback(async () => {
    const payload = await getRuntimeSettings();
    applyRuntimeSettings(payload);
    return payload;
  }, [applyRuntimeSettings]);

  const buildRuntimePatch = useCallback((): Partial<RuntimeConfigPayload> => {
    const payload: Partial<RuntimeConfigPayload> = {
      locale: settingsDraft.locale,
      llm_provider: 'llmrequester',
      preset_tag: settingsDraft.preset_tag,
      llm_transport: settingsDraft.llm_transport,
      api_url: settingsDraft.api_url,
      model_name: settingsDraft.model_name,
      web_search_enabled: settingsDraft.web_search_enabled,
      default_workflow_mode: settingsDraft.default_workflow_mode,
    };
    const nextApiKey = settingsDraft.api_key.trim();
    if (nextApiKey) {
      payload.api_key = nextApiKey;
    }
    return payload;
  }, [settingsDraft]);

  useEffect(() => {
    void execute(async () => {
      const payload = await loadRuntimeSettings();
      await applyLocale(payload.config.locale);
      await loadLlmPresetList();
    }, t('web.error.runtime_load_failed'));
  }, [applyLocale, execute, loadLlmPresetList, loadRuntimeSettings]);

  useEffect(() => {
    if (activeTab !== 'settings' || runtimeSettings) {
      return;
    }
    void execute(async () => {
      await loadRuntimeSettings();
    }, t('web.error.runtime_load_failed'));
  }, [activeTab, execute, loadRuntimeSettings, runtimeSettings]);

  const saveRuntime = useCallback(async () => {
    await execute(async () => {
      const payload = await updateRuntimeSettings(buildRuntimePatch());
      applyRuntimeSettings(payload);
      await applyLocale(payload.config.locale);
      setStatus(t('web.toast.runtime_saved'));
    }, t('web.error.runtime_save_failed'));
  }, [applyLocale, applyRuntimeSettings, buildRuntimePatch, execute, setStatus, t]);

  const profileOptions = useMemo(
    () =>
      (runtimeSettings?.profiles || [])
        .map((item) => String(item || '').trim())
        .filter((profile) => profile && profile !== CORE_PROFILE_NAME)
        .map((profile) => ({
          value: profile,
          label:
            profile === runtimeSettings?.active_profile
              ? `${t('web.runtime.profile_prefix')}: ${profile} (${t('web.runtime.profile_active')})`
              : `${t('web.runtime.profile_prefix')}: ${profile}`,
        })),
    [runtimeSettings, t],
  );

  const presetOptions = useMemo(
    () =>
      llmPresets.map((preset) => ({
        value: `preset:${preset.tag}`,
        label: `${preset.name} (${preset.group})`,
      })),
    [llmPresets],
  );

  const selectedProfileValue = useMemo(() => {
    const activeProfile = String(runtimeSettings?.active_profile || '').trim();
    if (!activeProfile || activeProfile === CORE_PROFILE_NAME) {
      return '';
    }
    return profileOptions.some((item) => item.value === activeProfile) ? activeProfile : '';
  }, [profileOptions, runtimeSettings?.active_profile]);

  const selectedPresetTag = useMemo(() => {
    const current = String(selectedPresetScheme || '').trim();
    if (!current.startsWith('preset:')) {
      return '';
    }
    return current.slice('preset:'.length).trim().toLowerCase();
  }, [selectedPresetScheme]);

  const selectedPreset = useMemo(() => {
    if (!selectedPresetTag) {
      return null;
    }
    return llmPresets.find((item) => item.tag === selectedPresetTag) || null;
  }, [llmPresets, selectedPresetTag]);

  const canManageSelectedPreset = Boolean(selectedPreset?.is_user);

  const applyLlmPreset = useCallback(
    (tag: string) => {
      const preset = llmPresets.find((item) => item.tag === tag);
      if (!preset) {
        return;
      }
      const nextModel = preset.default_model || preset.models[0] || '';
      const nextTransport = preset.llm_transport === 'openai' || preset.llm_transport === 'anthropic'
        ? preset.llm_transport
        : 'httpx';
      setSettingsDraft((prev) => ({
        ...prev,
        preset_tag: tag,
        llm_provider: 'llmrequester',
        llm_transport: nextTransport,
        api_url: preset.api_url || prev.api_url,
        api_key: '',
        api_key_mask: prev.api_key_slot_masks[tag] || prev.api_key_slot_masks.default || '',
        model_name: nextModel || prev.model_name,
      }));
      setSelectedPresetScheme(`preset:${tag}`);
      setStatus(t('web.toast.preset_applied', {preset: preset.name}));
    },
    [llmPresets, setStatus, t],
  );

  const handleProfileChange = useCallback(
    async (profile: string) => {
      const clean = String(profile || '').trim();
      if (!clean || clean === runtimeSettings?.active_profile) {
        return;
      }
      await execute(async () => {
        const payload = await switchRuntimeProfile(clean, false);
        applyRuntimeSettings(payload);
        await applyLocale(payload.config.locale);
        setStatus(t('web.toast.runtime_profile_switched', {profile: clean}));
      }, t('web.error.runtime_profile_switch_failed'));
    },
    [applyLocale, applyRuntimeSettings, execute, runtimeSettings?.active_profile, setStatus, t],
  );

  const handlePresetChange = useCallback(
    (nextValue: string) => {
      const clean = String(nextValue || '').trim();
      if (!clean || clean === 'custom') {
        setSelectedPresetScheme('custom');
        setSettingsDraft((prev) => ({
          ...prev,
          preset_tag: '',
          api_key: '',
          api_key_mask: prev.api_key_slot_masks.default || '',
        }));
        return;
      }
      if (clean.startsWith('preset:')) {
        applyLlmPreset(clean.slice('preset:'.length));
        return;
      }
      setSelectedPresetScheme(clean);
    },
    [applyLlmPreset],
  );

  const handleCreatePreset = useCallback(async () => {
    const presetNameRaw = await askPrompt({
      title: t('web.runtime.create_preset_title'),
      message: t('web.runtime.create_preset_body'),
      placeholder: t('web.runtime.new_profile_placeholder'),
    });
    const presetName = (presetNameRaw || '').trim();
    if (!presetName) {
      return;
    }
    await execute(async () => {
      const model = settingsDraft.model_name.trim();
      const created = await createLlmPreset({
        name: presetName,
        llm_transport: settingsDraft.llm_transport,
        api_url: settingsDraft.api_url.trim(),
        default_model: model,
        models: model ? [model] : [],
        auto_complete: true,
      });
      setLlmPresets((prev) => {
        const next = prev.filter((item) => item.tag !== created.tag);
        next.push(created);
        next.sort((left, right) => `${left.group}:${left.name}`.localeCompare(`${right.group}:${right.name}`));
        return next;
      });
      setSettingsDraft((prev) => ({
        ...prev,
        preset_tag: created.tag,
        api_key: '',
        api_key_mask: prev.api_key_slot_masks[created.tag] || prev.api_key_slot_masks.default || '',
      }));
      setSelectedPresetScheme(`preset:${created.tag}`);
      setStatus(t('web.toast.preset_created', {preset: created.name}));
    }, t('web.error.runtime_preset_create_failed'));
  }, [askPrompt, execute, setStatus, settingsDraft.api_url, settingsDraft.llm_transport, settingsDraft.model_name, t]);

  const handleRenamePreset = useCallback(async () => {
    if (!selectedPreset || !selectedPreset.is_user) {
      return;
    }
    const renamedRaw = await askPrompt({
      title: t('web.runtime.rename_preset_title'),
      message: t('web.runtime.rename_preset_body', {preset: selectedPreset.name}),
      defaultValue: selectedPreset.name,
      placeholder: selectedPreset.name,
    });
    const renamed = (renamedRaw || '').trim();
    if (!renamed || renamed === selectedPreset.name) {
      return;
    }
    await execute(async () => {
      const updated = await renameLlmPreset(selectedPreset.tag, renamed);
      setLlmPresets((prev) => {
        const next = prev.map((item) => (item.tag === updated.tag ? updated : item));
        next.sort((left, right) => `${left.group}:${left.name}`.localeCompare(`${right.group}:${right.name}`));
        return next;
      });
      setStatus(t('web.toast.preset_renamed', {preset: updated.name}));
    }, t('web.error.runtime_preset_rename_failed'));
  }, [askPrompt, execute, selectedPreset, setStatus, t]);

  const handleDeletePreset = useCallback(async () => {
    if (!selectedPreset || !selectedPreset.is_user) {
      return;
    }
    const confirmed = await askConfirm(
      t('web.runtime.delete_preset_title'),
      t('web.runtime.delete_preset_body', {preset: selectedPreset.name}),
      true,
    );
    if (!confirmed) {
      return;
    }
    await execute(async () => {
      await deleteLlmPreset(selectedPreset.tag);
      await loadLlmPresetList();
      const payload = await getRuntimeSettings();
      applyRuntimeSettings(payload);
      await applyLocale(payload.config.locale);
      setStatus(t('web.toast.preset_deleted', {preset: selectedPreset.name}));
    }, t('web.error.runtime_preset_delete_failed'));
  }, [applyLocale, applyRuntimeSettings, askConfirm, execute, loadLlmPresetList, selectedPreset, setStatus, t]);

  const handleCreateProfile = useCallback(async () => {
    const profileNameRaw = await askPrompt({
      title: t('web.runtime.create_profile_title'),
      message: t('web.runtime.create_profile_body'),
      placeholder: t('web.runtime.new_profile_placeholder'),
    });
    const profileName = (profileNameRaw || '').trim();
    if (!profileName) {
      return;
    }
    await execute(async () => {
      await createRuntimeProfile(profileName, CORE_PROFILE_NAME);
      await switchRuntimeProfile(profileName, false);
      const saved = await updateRuntimeSettings(buildRuntimePatch());
      applyRuntimeSettings(saved);
      await applyLocale(saved.config.locale);
      setStatus(t('web.toast.runtime_profile_created', {profile: profileName}));
    }, t('web.error.runtime_profile_create_failed'));
  }, [applyLocale, applyRuntimeSettings, askPrompt, buildRuntimePatch, execute, setStatus, t]);

  const handleSwitchLanguage = useCallback(async () => {
    const selected = await askSelect({
      title: t('web.modal.language_title'),
      message: t('web.modal.language_body'),
      defaultValue: locale,
      choices: SUPPORTED_LOCALES.map((item) => ({value: item.value, label: item.label})),
    });
    if (!selected || selected === locale) {
      return;
    }

    await execute(async () => {
      const payload = await updateRuntimeSettings({locale: selected});
      applyRuntimeSettings(payload);
      await applyLocale(selected);
      const nextLabel = SUPPORTED_LOCALES.find((item) => item.value === selected)?.label || selected;
      setStatus(t('web.toast.language_switched', {locale: nextLabel}));
    }, t('web.error.language_switch_failed'));
  }, [applyLocale, applyRuntimeSettings, askSelect, execute, locale, setStatus, t]);

  return (
    <div className="flex h-screen w-full bg-slate-50 text-slate-900 overflow-hidden font-sans">
      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        projects={projects}
        currentProjectId={projectId}
        onSelectProject={setProjectId}
        onCreateProject={handleCreateProject}
        onDeleteProject={handleDeleteProject}
        onQuickCreateNode={handleQuickCreateNode}
        onConfirm={askConfirm}
        t={t}
      />

      <div className="flex-1 flex flex-col relative overflow-hidden">
        <Header
          isChatOpen={isChatOpen}
          setIsChatOpen={setIsChatOpen}
          projectTitle={project?.title || ''}
          selectedNodeTitle={selectedNode?.title || ''}
          busy={busy}
          onRollback={handleRollback}
          onRefresh={refreshCurrentProject}
          onSnapshot={handleSnapshot}
          onValidate={handleValidate}
          onGenerateSelected={handleGenerateSelected}
          linkMode={linkMode}
          linkSourceNodeTitle={linkSourceNodeTitle}
          onToggleLinkMode={toggleLinkMode}
          localeLabel={localeLabel}
          onOpenLanguageSwitcher={handleSwitchLanguage}
          t={t}
        />

        <main className="flex-1 min-h-0 relative">
          {activeTab === 'workspace' && (
            <Workspace
              projectId={projectId}
              nodes={nodes}
              edges={edges}
              selectedNodeId={selectedNodeId}
              linkMode={linkMode}
              busy={busy}
              onSelectNode={handleWorkspaceSelect}
              onLinkNodeLeftClick={handleLinkNodeLeftClick}
              onLinkNodeRightClick={handleLinkNodeRightClick}
              onCreateNode={handleCreateNode}
              onUpdateNode={handleUpdateNode}
              onDeleteNode={handleDeleteNode}
              onCreateEdge={handleCreateEdge}
              onDeleteEdge={handleDeleteEdge}
              onGenerateNode={generateNodeById}
              onConfirm={askConfirm}
              onPrompt={askPrompt}
              onSelectOption={askSelect}
              t={t}
            />
          )}

          {activeTab === 'outline' && (
            <div className="h-full min-h-0 overflow-y-auto p-6">
              <div className="max-w-5xl mx-auto bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
                <h2 className="text-xl font-bold text-slate-800">{t('web.outline.view_title')}</h2>
                <p className="text-sm text-slate-500 mt-1">{t('web.outline.view_description')}</p>
                <div className="mt-5 grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
                  <div className="space-y-4">
                    <button
                      type="button"
                      onClick={() => setOutlinePreviewTarget('global')}
                      className={[
                        'w-full text-left rounded-xl border p-4 transition-colors',
                        outlinePreviewTarget === 'global'
                          ? 'border-pink-300 bg-pink-50/70'
                          : 'border-slate-200 bg-slate-50 hover:border-slate-300',
                      ].join(' ')}
                    >
                      <h3 className="text-sm font-semibold text-slate-800">{t('web.chat.context_global')}</h3>
                      <div className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
                        {shortenText(globalOutlineText) || t('web.outline.node_empty')}
                      </div>
                    </button>

                    <div className="space-y-3">
                      {guideOutlineCards.map((item) => (
                        <button
                          key={item.key}
                          type="button"
                          onClick={() => setOutlinePreviewTarget(item.key)}
                          className={[
                            'w-full text-left rounded-xl border p-4 transition-colors',
                            outlinePreviewTarget === item.key
                              ? 'border-pink-300 bg-pink-50/70'
                              : 'border-slate-200 bg-white hover:border-slate-300',
                          ].join(' ')}
                        >
                          <div className="flex items-center justify-between gap-3">
                            <h4 className="text-sm font-semibold text-slate-800">{item.title}</h4>
                            <span
                              className={
                                item.filled
                                  ? 'inline-flex items-center rounded-full px-2 py-0.5 text-[11px] border border-emerald-200 bg-emerald-50 text-emerald-700'
                                  : 'inline-flex items-center rounded-full px-2 py-0.5 text-[11px] border border-amber-200 bg-amber-50 text-amber-700'
                              }
                            >
                              {item.filled ? t('web.chat.guide_status_done') : t('web.chat.guide_status_pending')}
                            </span>
                          </div>
                          <div className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
                            {shortenText(item.content) || t('web.guide.docs_empty_fallback', {name: item.title})}
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>

                  <section className="rounded-xl bg-slate-50 border border-slate-200 p-4 min-h-[320px]">
                    <div className="flex items-center justify-between gap-3">
                      <h3 className="text-sm font-semibold text-slate-800">{outlinePreviewContent.title}</h3>
                      {selectedNode ? (
                        <button
                          type="button"
                          onClick={() => setOutlinePreviewTarget('selected')}
                          className={[
                            'text-xs px-2 py-1 rounded-md border transition-colors',
                            outlinePreviewTarget === 'selected'
                              ? 'border-pink-300 bg-pink-50 text-pink-700'
                              : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-100',
                          ].join(' ')}
                        >
                          {selectedNode.title}
                        </button>
                      ) : null}
                    </div>
                    <div className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
                      {outlinePreviewContent.content}
                    </div>
                  </section>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'graph' && (
            <KnowledgeGraph
              projectId={projectId}
              insights={insights}
              relationships={relationshipRows}
              characterStates={characterStateRows}
              itemStates={itemStateRows}
              loading={insightsLoading}
              onRefresh={refreshInsights}
              onUpsertRelationship={handleUpsertRelationship}
              t={t}
            />
          )}

          {activeTab === 'settings' && (
            <div className="h-full min-h-0 overflow-y-auto p-6">
              <div className="max-w-4xl mx-auto bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
                <h2 className="text-xl font-bold text-slate-800">{t('web.section.runtime')}</h2>
                <p className="text-sm text-slate-500 mt-1">{t('web.runtime.panel_hint')}</p>
                <div className="mt-4 rounded-xl border border-rose-300 bg-rose-50 px-4 py-3">
                  <p className="text-sm font-semibold text-rose-700">{t('web.runtime.security_warning_title')}</p>
                  <p className="mt-1 text-sm leading-relaxed text-rose-700">{t('web.runtime.security_warning_body_1')}</p>
                  <p className="mt-1 text-sm leading-relaxed text-rose-700">{t('web.runtime.security_warning_body_2')}</p>
                </div>

                {!runtimeSettings ? (
                  <div className="mt-5 text-slate-500">{t('web.runtime.loading')}</div>
                ) : (
                  <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
                    {runtimeSettings.active_profile !== CORE_PROFILE_NAME ? (
                      <FormRow label={t('web.runtime.active_profile')}>
                        <input
                          value={runtimeSettings.active_profile}
                          readOnly
                          className="w-full h-10 rounded-lg border border-slate-200 px-3 text-sm bg-slate-100 text-slate-700"
                        />
                      </FormRow>
                    ) : null}

                    <FormRow label={t('web.runtime.profile_prefix')}>
                      <div className="flex items-center gap-2">
                        <select
                          value={selectedProfileValue}
                          onChange={(event) => void handleProfileChange(event.target.value)}
                          className="flex-1 h-10 rounded-lg border border-slate-200 px-3 text-sm bg-white"
                        >
                          <option value="" disabled>
                            {t('web.runtime.profile_select_placeholder')}
                          </option>
                          {profileOptions.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                        <button
                          onClick={() => void handleCreateProfile()}
                          className="h-10 px-3 rounded-lg border border-pink-200 text-pink-600 text-sm font-semibold hover:bg-pink-50"
                        >
                          {t('web.runtime.create_profile')}
                        </button>
                      </div>
                    </FormRow>

                    <FormRow label={t('web.runtime.preset')}>
                      <div className="flex flex-wrap items-center gap-2">
                        <select
                          value={selectedPresetScheme}
                          onChange={(event) => handlePresetChange(event.target.value)}
                          className="min-w-[180px] flex-1 h-10 rounded-lg border border-slate-200 px-3 text-sm bg-white"
                        >
                          <option value="custom">{t('web.runtime.preset_none')}</option>
                          {presetOptions.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                        <button
                          onClick={() => void handleCreatePreset()}
                          className="h-10 px-3 rounded-lg border border-pink-200 text-pink-600 text-sm font-semibold hover:bg-pink-50"
                        >
                          {t('web.runtime.create_preset')}
                        </button>
                        <button
                          onClick={() => void handleRenamePreset()}
                          disabled={!canManageSelectedPreset}
                          className="h-10 px-3 rounded-lg border border-slate-200 text-slate-600 text-sm font-semibold enabled:hover:bg-slate-100 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {t('web.runtime.rename_preset')}
                        </button>
                        <button
                          onClick={() => void handleDeletePreset()}
                          disabled={!canManageSelectedPreset}
                          className="h-10 px-3 rounded-lg border border-rose-200 text-rose-600 text-sm font-semibold enabled:hover:bg-rose-50 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {t('web.runtime.delete_preset')}
                        </button>
                      </div>
                    </FormRow>

                    <FormRow label={t('web.runtime.api_url')}>
                      <input
                        value={settingsDraft.api_url}
                        onChange={(event) => setSettingsDraft((prev) => ({...prev, api_url: event.target.value}))}
                        className="w-full h-10 rounded-lg border border-slate-200 px-3 text-sm"
                      />
                    </FormRow>

                    <FormRow label={t('web.runtime.llm_transport')}>
                      <select
                        value={settingsDraft.llm_transport}
                        onChange={(event) =>
                          setSettingsDraft((prev) => ({
                            ...prev,
                            llm_transport: event.target.value as RuntimeDraft['llm_transport'],
                          }))
                        }
                        className="w-full h-10 rounded-lg border border-slate-200 px-3 text-sm bg-white"
                      >
                        <option value="httpx">{t('web.runtime.transport.httpx')}</option>
                        <option value="openai">{t('web.runtime.transport.openai')}</option>
                        <option value="anthropic">{t('web.runtime.transport.anthropic')}</option>
                      </select>
                    </FormRow>

                    <FormRow label={t('web.runtime.model_name')}>
                      <input
                        value={settingsDraft.model_name}
                        onChange={(event) => setSettingsDraft((prev) => ({...prev, model_name: event.target.value}))}
                        className="w-full h-10 rounded-lg border border-slate-200 px-3 text-sm"
                      />
                    </FormRow>

                    <FormRow label={t('web.runtime.api_key')}>
                      <input
                        type="password"
                        value={settingsDraft.api_key}
                        onChange={(event) => setSettingsDraft((prev) => ({...prev, api_key: event.target.value}))}
                        placeholder={settingsDraft.api_key_mask}
                        autoComplete="new-password"
                        className="w-full h-10 rounded-lg border border-slate-200 px-3 text-sm"
                      />
                    </FormRow>

                    <FormRow label={t('web.ai.workflow_mode')}>
                      <select
                        value={settingsDraft.default_workflow_mode}
                        onChange={(event) => void handleWorkflowModeDraftChange(event.target.value as WorkflowMode)}
                        className="w-full h-10 rounded-lg border border-slate-200 px-3 text-sm bg-white"
                      >
                        {workflowModeOptions.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </FormRow>

                    <div className="md:col-span-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        {t('web.runtime.workflow_mode_guide_title')}
                      </p>
                      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-relaxed text-slate-700">
                        <li>{t('web.runtime.workflow_mode_guide_multi')}</li>
                        <li>{t('web.runtime.workflow_mode_guide_single')}</li>
                        <li>{t('web.runtime.workflow_mode_guide_node_auto')}</li>
                        <li>{t('web.runtime.workflow_mode_guide_control')}</li>
                      </ul>
                    </div>

                    <div className="md:col-span-2 flex items-center gap-2 mt-1">
                      <input
                        id="web_search_enabled"
                        type="checkbox"
                        checked={settingsDraft.web_search_enabled}
                        onChange={(event) =>
                          setSettingsDraft((prev) => ({
                            ...prev,
                            web_search_enabled: event.target.checked,
                          }))
                        }
                      />
                      <label htmlFor="web_search_enabled" className="text-sm text-slate-700">{t('web.runtime.web_search_enabled')}</label>
                    </div>

                    <div className="md:col-span-2 pt-2">
                      <button
                        onClick={() => void saveRuntime()}
                        className="h-10 px-5 rounded-lg bg-pink-500 text-white text-sm font-semibold hover:bg-pink-600"
                      >
                        {t('web.runtime.save')}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          <AIChat
            isOpen={isChatOpen}
            onClose={() => setIsChatOpen(false)}
            projectId={projectId}
            selectedNodeId={selectedNodeId}
            resetVersion={chatResetVersion}
            fullScreen={shouldShowGuideWorkspace}
            guideMode={shouldShowGuideWorkspace}
            guideDocStatus={guideDocStatus}
            onGuideDocReply={handleGuideDocReply}
            onGuideSkipDocumentRequest={handleGuideSkipDocumentRequest}
            onCreateSuggestionNode={handleCreateSuggestionNode}
            onRefreshProject={refreshCurrentProject}
            onStatus={setStatus}
            t={t}
          />
        </main>

        <WindowDialog
          dialog={dialog}
          onConfirm={(value) => resolveDialog({confirmed: true, value: value || ''})}
          onCancel={() => resolveDialog({confirmed: false, value: ''})}
          t={t}
        />

        {notice ? (
          <div className="absolute left-4 bottom-4 z-50 max-w-[65ch]">
            <div
              className={[
                'px-3 py-2 rounded-xl text-sm shadow-lg border backdrop-blur',
                notice.error
                  ? 'bg-red-50/95 text-red-700 border-red-200'
                  : 'bg-emerald-50/95 text-emerald-700 border-emerald-200',
              ].join(' ')}
            >
              {notice.text}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function FormRow({label, children}: {label: string; children: React.ReactNode}) {
  return (
    <label className="block">
      <span className="block text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1">{label}</span>
      {children}
    </label>
  );
}
