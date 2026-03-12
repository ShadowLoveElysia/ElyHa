import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {Sidebar} from './components/Sidebar';
import {Header} from './components/Header';
import {Workspace} from './components/Workspace';
import {AIChat} from './components/AIChat';
import {KnowledgeGraph} from './components/KnowledgeGraph';
import {WindowDialog, type WindowDialogState} from './components/window';
import {SUPPORTED_LOCALES, loadLocaleDict, tFrom, type TranslationVars} from './i18n';
import {
  createRuntimeProfile,
  createEdge,
  createNode,
  createProject,
  createSnapshot,
  deleteEdge,
  deleteNode,
  deleteProject,
  fetchProjectInsights,
  generateChapter,
  getProjectBundle,
  getRuntimeSettings,
  listLlmPresets,
  listProjects,
  listSnapshots,
  rollbackProject,
  switchRuntimeProfile,
  updateNode,
  updateRuntimeSettings,
  validateProject,
} from './api';
import type {
  AiSuggestedOption,
  CreateNodePayload,
  GraphEdgePayload,
  GraphNodePayload,
  LlmPresetPayload,
  ProjectInsights,
  ProjectPayload,
  RuntimeConfigPayload,
  RuntimeSettingsPayload,
  UpdateNodePayload,
  WorkflowMode,
} from './types';

function errorToText(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error || '未知错误');
}

function nodeMainText(metadata: unknown): string {
  if (!metadata || typeof metadata !== 'object' || Array.isArray(metadata)) {
    return '该节点暂无正文。';
  }
  const record = metadata as Record<string, unknown>;
  const content = typeof record.content === 'string' ? record.content : '';
  if (content.trim()) {
    return content;
  }
  const summary = typeof record.summary === 'string' ? record.summary : '';
  if (summary.trim()) {
    return summary;
  }
  return '该节点暂无正文。';
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
  api_url: string;
  api_key: string;
  model_name: string;
  web_search_enabled: boolean;
  default_workflow_mode: WorkflowMode;
}

function toRuntimeDraft(config: RuntimeConfigPayload): RuntimeDraft {
  const workflowMode: WorkflowMode = config.default_workflow_mode === 'single' ? 'single' : 'multi_agent';
  return {
    locale: config.locale,
    llm_provider: 'llmrequester',
    api_url: config.api_url,
    api_key: config.api_key,
    model_name: config.model_name,
    web_search_enabled: config.web_search_enabled,
    default_workflow_mode: workflowMode,
  };
}

export default function App() {
  const [activeTab, setActiveTab] = useState('workspace');
  const [isChatOpen, setIsChatOpen] = useState(false);

  const [projects, setProjects] = useState<ProjectPayload[]>([]);
  const [projectId, setProjectId] = useState('');
  const [project, setProject] = useState<ProjectPayload | null>(null);
  const [nodes, setNodes] = useState<GraphNodePayload[]>([]);
  const [edges, setEdges] = useState<GraphEdgePayload[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState('');
  const [linkMode, setLinkMode] = useState(false);
  const [linkSourceNodeId, setLinkSourceNodeId] = useState('');

  const [busyCount, setBusyCount] = useState(0);
  const [notice, setNotice] = useState<NoticeState | null>(null);
  const [dialog, setDialog] = useState<WindowDialogState | null>(null);
  const dialogResolverRef = useRef<((result: DialogResolve) => void) | null>(null);

  const [insights, setInsights] = useState<ProjectInsights | null>(null);
  const [insightsLoading, setInsightsLoading] = useState(false);

  const [runtimeSettings, setRuntimeSettings] = useState<RuntimeSettingsPayload | null>(null);
  const [settingsDraft, setSettingsDraft] = useState<RuntimeDraft>({
    locale: 'zh',
    llm_provider: 'llmrequester',
    api_url: '',
    api_key: '',
    model_name: '',
    web_search_enabled: false,
    default_workflow_mode: 'multi_agent',
  });
  const [llmPresets, setLlmPresets] = useState<LlmPresetPayload[]>([]);
  const [selectedLlmScheme, setSelectedLlmScheme] = useState('custom');
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
        setStatus(`${failPrefix}: ${errorToText(error)}`, true);
      } finally {
        setBusyCount((value) => Math.max(0, value - 1));
      }
    },
    [setStatus],
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
    setSelectedLlmScheme(`profile:${payload.active_profile}`);
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
      setStatus('工作区已刷新');
    }, '刷新工作区失败');
  }, [execute, loadProjectBundle, projectId, setStatus]);

  useEffect(() => {
    void execute(async () => {
      await refreshProjects();
    }, '加载项目列表失败');
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
    }, '加载项目数据失败');
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

  const handleCreateProject = useCallback(
    async (title: string) => {
      await execute(async () => {
        const created = await createProject(title.trim());
        await refreshProjects(created.id);
        await loadProjectBundle(created.id);
        setStatus(`已创建项目：${created.title}`);
      }, '创建项目失败');
    },
    [execute, loadProjectBundle, refreshProjects, setStatus],
  );

  const handleDeleteProject = useCallback(
    async (targetProjectId: string) => {
      await execute(async () => {
        await deleteProject(targetProjectId);
        await refreshProjects();
        setStatus('项目已删除');
      }, '删除项目失败');
    },
    [execute, refreshProjects, setStatus],
  );

  const handleQuickCreateNode = useCallback(async () => {
    if (!projectId) {
      setStatus('请先选择项目', true);
      return;
    }
    await execute(async () => {
      const created = await createNode(projectId, {
        title: '新建章节节点',
        type: 'chapter',
        metadata: {
          content: '',
          summary: '',
        },
      });
      await loadProjectBundle(projectId);
      setSelectedNodeId(created.id);
      setStatus('节点已创建');
    }, '创建节点失败');
  }, [execute, loadProjectBundle, projectId, setStatus]);

  const handleCreateNode = useCallback(
    async (payload: CreateNodePayload) => {
      if (!projectId) {
        setStatus('请先选择项目', true);
        return;
      }
      await execute(async () => {
        const created = await createNode(projectId, payload);
        await loadProjectBundle(projectId);
        setSelectedNodeId(created.id);
      }, '创建节点失败');
    },
    [execute, loadProjectBundle, projectId, setStatus],
  );

  const handleUpdateNode = useCallback(
    async (nodeId: string, payload: UpdateNodePayload) => {
      if (!projectId) {
        setStatus('请先选择项目', true);
        return;
      }
      await execute(async () => {
        const updated = await updateNode(projectId, nodeId, payload);
        setNodes((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      }, '更新节点失败');
    },
    [execute, projectId, setStatus],
  );

  const handleDeleteNode = useCallback(
    async (nodeId: string) => {
      if (!projectId) {
        setStatus('请先选择项目', true);
        return;
      }
      await execute(async () => {
        await deleteNode(projectId, nodeId);
        setNodes((prev) => prev.filter((item) => item.id !== nodeId));
        setEdges((prev) => prev.filter((item) => item.source_id !== nodeId && item.target_id !== nodeId));
      }, '删除节点失败');
    },
    [execute, projectId, setStatus],
  );

  const handleCreateEdge = useCallback(
    async (sourceId: string, targetId: string, label = '') => {
      if (!projectId) {
        setStatus('请先选择项目', true);
        return;
      }
      await execute(async () => {
        const created = await createEdge(projectId, sourceId, targetId, label);
        setEdges((prev) => [...prev, created]);
      }, '创建连线失败');
    },
    [execute, projectId, setStatus],
  );

  const handleDeleteEdge = useCallback(
    async (edgeId: string) => {
      if (!projectId) {
        setStatus('请先选择项目', true);
        return;
      }
      await execute(async () => {
        await deleteEdge(projectId, edgeId);
        setEdges((prev) => prev.filter((item) => item.id !== edgeId));
      }, '删除连线失败');
    },
    [execute, projectId, setStatus],
  );

  const handleDeleteEdgeBetween = useCallback(
    async (leftNodeId: string, rightNodeId: string) => {
      if (!projectId) {
        setStatus('请先选择项目', true);
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
      setStatus('请先选择项目', true);
      return;
    }
    await execute(async () => {
      const snap = await createSnapshot(projectId);
      setStatus(`快照已保存 revision=${snap.revision}`);
      await loadProjectBundle(projectId);
    }, '保存快照失败');
  }, [execute, loadProjectBundle, projectId, setStatus]);

  const handleRollback = useCallback(async () => {
    if (!projectId || !project) {
      setStatus('请先选择项目', true);
      return;
    }
    await execute(async () => {
      const snapshots = await listSnapshots(projectId);
      const activeRevision = project.active_revision;
      const target = snapshots
        .filter((item) => item.revision < activeRevision)
        .sort((a, b) => b.revision - a.revision)[0];
      if (!target) {
        setStatus('没有可回滚的更早快照');
        return;
      }
      await rollbackProject(projectId, target.revision);
      await loadProjectBundle(projectId);
      setStatus(`已回滚到 revision=${target.revision}`);
    }, '回滚失败');
  }, [execute, loadProjectBundle, project, projectId, setStatus]);

  const handleValidate = useCallback(async () => {
    if (!projectId) {
      setStatus('请先选择项目', true);
      return;
    }
    await execute(async () => {
      const report = await validateProject(projectId);
      setStatus(`校验完成：错误 ${report.errors}，警告 ${report.warnings}，信息 ${report.infos}`);
    }, '校验失败');
  }, [execute, projectId, setStatus]);

  const generateNodeById = useCallback(
    async (nodeId: string) => {
      if (!projectId || !nodeId) {
        setStatus('请先选择一个节点', true);
        return;
      }
      await execute(async () => {
        const result = await generateChapter(projectId, nodeId);
        await loadProjectBundle(projectId);
        setStatus(`生成完成：${result.provider} / revision ${result.revision}`);
      }, '节点生成失败');
    },
    [execute, loadProjectBundle, projectId, setStatus],
  );

  const handleGenerateSelected = useCallback(async () => {
    if (!selectedNodeId) {
      setStatus('请先选择一个节点', true);
      return;
    }
    await generateNodeById(selectedNodeId);
  }, [generateNodeById, selectedNodeId, setStatus]);

  const handleCreateSuggestionNode = useCallback(
    async (option: AiSuggestedOption) => {
      if (!projectId) {
        setStatus('请先选择项目', true);
        return;
      }
      await execute(async () => {
        const content = option.description || option.summary || '';
        const metadata: Record<string, unknown> = {
          content,
          summary: (option.summary || content).slice(0, 200),
        };
        if (option.outline_steps) {
          metadata.outline_markdown = option.outline_steps;
        }
        const created = await createNode(projectId, {
          title: option.title || 'AI 建议节点',
          type: 'chapter',
          metadata,
        });
        setNodes((prev) => [...prev, created]);
        setSelectedNodeId(created.id);
      }, '创建建议节点失败');
    },
    [execute, projectId, setStatus],
  );

  const refreshInsights = useCallback(async () => {
    if (!projectId) {
      setInsights(null);
      return;
    }
    setInsightsLoading(true);
    try {
      const payload = await fetchProjectInsights(projectId);
      setInsights(payload);
    } catch (error) {
      setStatus(`加载图谱失败: ${errorToText(error)}`, true);
    } finally {
      setInsightsLoading(false);
    }
  }, [projectId, setStatus]);

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

  useEffect(() => {
    void execute(async () => {
      const payload = await loadRuntimeSettings();
      await applyLocale(payload.config.locale);
      await loadLlmPresetList();
    }, '加载运行设置失败');
  }, [applyLocale, execute, loadLlmPresetList, loadRuntimeSettings]);

  useEffect(() => {
    if (activeTab !== 'settings' || runtimeSettings) {
      return;
    }
    void execute(async () => {
      await loadRuntimeSettings();
    }, '加载运行设置失败');
  }, [activeTab, execute, loadRuntimeSettings, runtimeSettings]);

  const saveRuntime = useCallback(async () => {
    await execute(async () => {
      const payload = await updateRuntimeSettings({
        locale: settingsDraft.locale,
        llm_provider: 'llmrequester',
        api_url: settingsDraft.api_url,
        api_key: settingsDraft.api_key,
        model_name: settingsDraft.model_name,
        web_search_enabled: settingsDraft.web_search_enabled,
        default_workflow_mode: settingsDraft.default_workflow_mode,
      });
      applyRuntimeSettings(payload);
      await applyLocale(payload.config.locale);
      setStatus(t('web.toast.runtime_saved'));
    }, '保存运行设置失败');
  }, [applyLocale, applyRuntimeSettings, execute, setStatus, settingsDraft, t]);

  const llmSchemeOptions = useMemo(() => {
    const options: Array<{value: string; label: string}> = [];
    const profileOptions = (runtimeSettings?.profiles || []).map((profile) => ({
      value: `profile:${profile}`,
      label:
        profile === runtimeSettings?.active_profile
          ? `${t('web.runtime.profile_prefix')}: ${profile} (${t('web.runtime.profile_active')})`
          : `${t('web.runtime.profile_prefix')}: ${profile}`,
    }));
    const presetOptions = llmPresets.map((preset) => ({
      value: `preset:${preset.tag}`,
      label: `${preset.name} (${preset.group})`,
    }));
    options.push(...profileOptions);
    options.push(...presetOptions);
    options.push({value: 'custom', label: t('web.runtime.preset_none')});
    return options;
  }, [llmPresets, runtimeSettings, t]);

  const applyLlmPreset = useCallback(
    (tag: string) => {
      const preset = llmPresets.find((item) => item.tag === tag);
      if (!preset) {
        return;
      }
      const nextModel = preset.default_model || preset.models[0] || '';
      setSettingsDraft((prev) => ({
        ...prev,
        llm_provider: 'llmrequester',
        api_url: preset.api_url || prev.api_url,
        model_name: nextModel || prev.model_name,
      }));
      setSelectedLlmScheme(`preset:${tag}`);
      setStatus(t('web.toast.preset_applied', {preset: preset.name}));
    },
    [llmPresets, setStatus, t],
  );

  const handleLlmSchemeChange = useCallback(
    async (nextValue: string) => {
      if (!nextValue) {
        return;
      }
      if (nextValue === 'custom') {
        setSelectedLlmScheme(nextValue);
        return;
      }
      if (nextValue.startsWith('preset:')) {
        applyLlmPreset(nextValue.slice('preset:'.length));
        return;
      }
      if (nextValue.startsWith('profile:')) {
        const profile = nextValue.slice('profile:'.length);
        await execute(async () => {
          const payload = await switchRuntimeProfile(profile, false);
          applyRuntimeSettings(payload);
          await applyLocale(payload.config.locale);
          setStatus(t('web.toast.runtime_profile_switched', {profile}));
        }, '切换预设失败');
        return;
      }
      setSelectedLlmScheme(nextValue);
    },
    [applyLlmPreset, applyLocale, applyRuntimeSettings, execute, setStatus, t],
  );

  const handleCreateLlmPreset = useCallback(async () => {
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
      await createRuntimeProfile(profileName, runtimeSettings?.active_profile || 'core');
      await switchRuntimeProfile(profileName, false);
      const saved = await updateRuntimeSettings({
        locale: settingsDraft.locale,
        llm_provider: 'llmrequester',
        api_url: settingsDraft.api_url,
        api_key: settingsDraft.api_key,
        model_name: settingsDraft.model_name,
        web_search_enabled: settingsDraft.web_search_enabled,
        default_workflow_mode: settingsDraft.default_workflow_mode,
      });
      applyRuntimeSettings(saved);
      await applyLocale(saved.config.locale);
      setSelectedLlmScheme(`profile:${profileName}`);
      setStatus(t('web.toast.runtime_profile_created', {profile: profileName}));
    }, '创建预设失败');
  }, [applyLocale, applyRuntimeSettings, askPrompt, execute, runtimeSettings?.active_profile, setStatus, settingsDraft, t]);

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
    }, '切换语言失败');
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

        <main className="flex-1 relative">
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
            <div className="h-full overflow-y-auto p-6">
              <div className="max-w-5xl mx-auto bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
                <h2 className="text-xl font-bold text-slate-800">大纲视图</h2>
                <p className="text-sm text-slate-500 mt-1">当前阶段先展示选中节点正文，下一阶段会接入完整大纲拆解流程。</p>
                <div className="mt-5 rounded-xl bg-slate-50 border border-slate-200 p-4 min-h-[320px] whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
                  {selectedNode
                    ? nodeMainText(selectedNode.metadata)
                    : '请先在工作区选择一个节点。'}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'graph' && (
            <KnowledgeGraph projectId={projectId} insights={insights} loading={insightsLoading} onRefresh={refreshInsights} />
          )}

          {activeTab === 'settings' && (
            <div className="h-full overflow-y-auto p-6">
              <div className="max-w-4xl mx-auto bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
                <h2 className="text-xl font-bold text-slate-800">运行设置</h2>
                <p className="text-sm text-slate-500 mt-1">此面板直接读写后端 `/api/settings/runtime`。</p>

                {!runtimeSettings ? (
                  <div className="mt-5 text-slate-500">加载设置中...</div>
                ) : (
                  <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
                    <FormRow label={t('web.runtime.active_profile')}>
                      <input
                        value={runtimeSettings.active_profile}
                        readOnly
                        className="w-full h-10 rounded-lg border border-slate-200 px-3 text-sm bg-slate-100 text-slate-700"
                      />
                    </FormRow>

                    <FormRow label={t('web.runtime.preset')}>
                      <div className="flex items-center gap-2">
                        <select
                          value={selectedLlmScheme}
                          onChange={(event) => void handleLlmSchemeChange(event.target.value)}
                          className="flex-1 h-10 rounded-lg border border-slate-200 px-3 text-sm bg-white"
                        >
                          {llmSchemeOptions.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                        <button
                          onClick={() => void handleCreateLlmPreset()}
                          className="h-10 px-3 rounded-lg border border-pink-200 text-pink-600 text-sm font-semibold hover:bg-pink-50"
                        >
                          {t('web.runtime.create_profile')}
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
                        placeholder="****************"
                        autoComplete="new-password"
                        className="w-full h-10 rounded-lg border border-slate-200 px-3 text-sm"
                      />
                    </FormRow>

                    <FormRow label={t('web.ai.workflow_mode')}>
                      <select
                        value={settingsDraft.default_workflow_mode}
                        onChange={(event) =>
                          setSettingsDraft((prev) => ({
                            ...prev,
                            default_workflow_mode: event.target.value as WorkflowMode,
                          }))
                        }
                        className="w-full h-10 rounded-lg border border-slate-200 px-3 text-sm bg-white"
                      >
                        {workflowModeOptions.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </FormRow>

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
                        保存设置
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </main>

        <AIChat
          isOpen={isChatOpen}
          onClose={() => setIsChatOpen(false)}
          projectId={projectId}
          selectedNodeId={selectedNodeId}
          onCreateSuggestionNode={handleCreateSuggestionNode}
          onRefreshProject={refreshCurrentProject}
          onStatus={setStatus}
        />

        <WindowDialog
          dialog={dialog}
          onConfirm={(value) => resolveDialog({confirmed: true, value: value || ''})}
          onCancel={() => resolveDialog({confirmed: false, value: ''})}
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
