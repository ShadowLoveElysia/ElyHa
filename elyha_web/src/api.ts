import type {
  AgentSettingProposalsResponse,
  AgentSessionResponse,
  AiChatPayload,
  AiChatResponse,
  ChatThreadMessagesResponse,
  ChatThreadsResponse,
  ClarificationQuestionPayload,
  ClarificationQuestionResponse,
  CreateNodePayload,
  GenerateChapterResponse,
  GraphEdgePayload,
  GraphNodePayload,
  LlmPresetPayload,
  ProjectInsights,
  ProjectPayload,
  ProjectSettings,
  RequestAgentClarificationPayload,
  ResumeAgentSessionPayload,
  ReviewAgentSettingProposalPayload,
  ReviewAgentSettingProposalsBatchPayload,
  RuntimeConfigPayload,
  RuntimeSettingsPayload,
  SnapshotPayload,
  StartAgentSessionPayload,
  SubmitAgentClarificationAnswerPayload,
  SubmitAgentDiffReviewPayload,
  SubmitAgentDecisionPayload,
  UpdateNodePayload,
  ValidationReport,
  WorkflowMode,
} from './types';

const DEFAULT_TIMEOUT_MS = 95_000;

export class ApiTimeoutError extends Error {
  timeoutSeconds: number;

  constructor(timeoutMs: number) {
    const timeoutSeconds = Math.max(1, Math.round(timeoutMs / 1000));
    super(`API_TIMEOUT:${timeoutSeconds}`);
    this.name = 'ApiTimeoutError';
    this.timeoutSeconds = timeoutSeconds;
  }
}

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

function resolveApiBase(): string {
  const raw = (import.meta as { env?: { VITE_API_BASE_URL?: string } }).env?.VITE_API_BASE_URL;
  if (!raw || !raw.trim()) {
    return '';
  }
  return trimTrailingSlash(raw.trim());
}

const API_BASE = resolveApiBase();

function withApiBase(path: string): string {
  if (/^https?:\/\//i.test(path)) {
    return path;
  }
  if (!API_BASE) {
    return path;
  }
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
}

function isJsonResponse(response: Response): boolean {
  const contentType = response.headers.get('content-type') || '';
  return contentType.includes('application/json');
}

function extractErrorMessage(payload: unknown, status: number): string {
  if (payload && typeof payload === 'object') {
    const maybeDetail = (payload as { detail?: unknown }).detail;
    if (typeof maybeDetail === 'string' && maybeDetail.trim()) {
      return maybeDetail.trim();
    }
    if (Array.isArray(maybeDetail)) {
      return maybeDetail.map(String).join('; ');
    }
    const maybeMessage = (payload as { message?: unknown }).message;
    if (typeof maybeMessage === 'string' && maybeMessage.trim()) {
      return maybeMessage.trim();
    }
  }
  if (typeof payload === 'string' && payload.trim()) {
    return payload.trim();
  }
  return `HTTP ${status}`;
}

type ApiRequestOptions = Omit<RequestInit, 'body'> & {
  body?: unknown;
  timeoutMs?: number;
};

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const timeoutMsRaw = Number(options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  const timeoutMs = Number.isFinite(timeoutMsRaw) && timeoutMsRaw > 0 ? Math.floor(timeoutMsRaw) : DEFAULT_TIMEOUT_MS;

  const init: RequestInit = {
    method: options.method || 'GET',
    headers: {
      ...(options.headers || {}),
    },
    body: undefined,
    credentials: options.credentials,
    mode: options.mode,
    cache: options.cache,
    redirect: options.redirect,
    referrer: options.referrer,
    referrerPolicy: options.referrerPolicy,
    integrity: options.integrity,
    keepalive: options.keepalive,
    signal: options.signal,
  };

  if (options.body !== undefined && options.body !== null) {
    if (
      typeof options.body === 'string' ||
      options.body instanceof FormData ||
      options.body instanceof URLSearchParams ||
      options.body instanceof Blob ||
      options.body instanceof ArrayBuffer
    ) {
      init.body = options.body as BodyInit;
    } else {
      init.headers = {
        ...(init.headers || {}),
        'Content-Type': 'application/json',
      };
      init.body = JSON.stringify(options.body);
    }
  }

  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  init.signal = controller.signal;

  try {
    const response = await fetch(withApiBase(path), init);
    const payload = isJsonResponse(response) ? await response.json() : await response.text();
    if (!response.ok) {
      throw new Error(extractErrorMessage(payload, response.status));
    }
    return payload as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiTimeoutError(timeoutMs);
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

export async function listProjects(): Promise<ProjectPayload[]> {
  return apiRequest<ProjectPayload[]>('/api/projects');
}

export async function createProject(title: string): Promise<ProjectPayload> {
  return apiRequest<ProjectPayload>('/api/projects', {
    method: 'POST',
    body: { title },
  });
}

export async function deleteProject(projectId: string): Promise<{ status: string; project_id: string }> {
  return apiRequest<{ status: string; project_id: string }>(`/api/projects/${projectId}`, {
    method: 'DELETE',
  });
}

export async function getProject(projectId: string): Promise<ProjectPayload> {
  return apiRequest<ProjectPayload>(`/api/projects/${projectId}`);
}

export async function listNodes(projectId: string): Promise<GraphNodePayload[]> {
  return apiRequest<GraphNodePayload[]>(`/api/projects/${projectId}/nodes`);
}

export async function createNode(projectId: string, payload: CreateNodePayload): Promise<GraphNodePayload> {
  return apiRequest<GraphNodePayload>(`/api/projects/${projectId}/nodes`, {
    method: 'POST',
    body: payload,
  });
}

export async function updateNode(
  projectId: string,
  nodeId: string,
  payload: UpdateNodePayload,
): Promise<GraphNodePayload> {
  return apiRequest<GraphNodePayload>(`/api/projects/${projectId}/nodes/${nodeId}`, {
    method: 'PUT',
    body: payload,
  });
}

export async function deleteNode(projectId: string, nodeId: string): Promise<{ status: string; node_id: string }> {
  return apiRequest<{ status: string; node_id: string }>(`/api/projects/${projectId}/nodes/${nodeId}`, {
    method: 'DELETE',
  });
}

export async function listEdges(projectId: string): Promise<GraphEdgePayload[]> {
  return apiRequest<GraphEdgePayload[]>(`/api/projects/${projectId}/edges`);
}

export async function createEdge(
  projectId: string,
  sourceId: string,
  targetId: string,
  label = '',
): Promise<GraphEdgePayload> {
  return apiRequest<GraphEdgePayload>(`/api/projects/${projectId}/edges`, {
    method: 'POST',
    body: {
      source_id: sourceId,
      target_id: targetId,
      label,
    },
  });
}

export async function deleteEdge(projectId: string, edgeId: string): Promise<{ status: string; edge_id: string }> {
  return apiRequest<{ status: string; edge_id: string }>(`/api/projects/${projectId}/edges/${edgeId}`, {
    method: 'DELETE',
  });
}

export async function validateProject(projectId: string): Promise<ValidationReport> {
  return apiRequest<ValidationReport>(`/api/projects/${projectId}/validate`, {
    method: 'POST',
  });
}

export async function createSnapshot(projectId: string): Promise<SnapshotPayload> {
  return apiRequest<SnapshotPayload>(`/api/projects/${projectId}/snapshots`, {
    method: 'POST',
  });
}

export async function listSnapshots(projectId: string): Promise<SnapshotPayload[]> {
  return apiRequest<SnapshotPayload[]>(`/api/projects/${projectId}/snapshots`);
}

export async function rollbackProject(projectId: string, revision: number): Promise<ProjectPayload> {
  return apiRequest<ProjectPayload>(`/api/projects/${projectId}/rollback`, {
    method: 'POST',
    body: { revision },
  });
}

export async function sendAiChat(payload: AiChatPayload): Promise<AiChatResponse> {
  return apiRequest<AiChatResponse>('/api/ai/chat', {
    method: 'POST',
    body: payload,
    timeoutMs: 180_000,
  });
}

export async function listProjectChatThreads(
  projectId: string,
  limit = 50,
): Promise<ChatThreadsResponse> {
  return apiRequest<ChatThreadsResponse>(
    `/api/projects/${projectId}/chat/threads?limit=${encodeURIComponent(String(limit))}`,
  );
}

export async function getProjectChatThreadMessages(
  projectId: string,
  threadId: string,
  limit = 80,
): Promise<ChatThreadMessagesResponse> {
  return apiRequest<ChatThreadMessagesResponse>(
    `/api/projects/${projectId}/chat/threads/${encodeURIComponent(threadId)}/messages?limit=${encodeURIComponent(
      String(limit),
    )}`,
  );
}

export async function requestClarificationQuestion(
  payload: ClarificationQuestionPayload,
): Promise<ClarificationQuestionResponse> {
  return apiRequest<ClarificationQuestionResponse>('/api/ai/clarification/question', {
    method: 'POST',
    body: payload,
    timeoutMs: 120_000,
  });
}

export async function startAgentSession(payload: StartAgentSessionPayload): Promise<AgentSessionResponse> {
  return apiRequest<AgentSessionResponse>('/api/agent/session/start', {
    method: 'POST',
    body: payload,
    timeoutMs: 240_000,
  });
}

export async function resumeAgentSession(payload: ResumeAgentSessionPayload): Promise<AgentSessionResponse> {
  return apiRequest<AgentSessionResponse>('/api/agent/session/resume', {
    method: 'POST',
    body: payload,
  });
}

export async function getAgentSession(threadId: string): Promise<AgentSessionResponse> {
  return apiRequest<AgentSessionResponse>(`/api/agent/session/${threadId}`);
}

export async function submitAgentDecision(payload: SubmitAgentDecisionPayload): Promise<AgentSessionResponse> {
  return apiRequest<AgentSessionResponse>('/api/agent/session/decision', {
    method: 'POST',
    body: payload,
    timeoutMs: 240_000,
  });
}

export async function requestAgentClarification(
  payload: RequestAgentClarificationPayload,
): Promise<AgentSessionResponse> {
  return apiRequest<AgentSessionResponse>('/api/agent/session/clarification/question', {
    method: 'POST',
    body: payload,
    timeoutMs: 180_000,
  });
}

export async function submitAgentClarificationAnswer(
  payload: SubmitAgentClarificationAnswerPayload,
): Promise<AgentSessionResponse> {
  return apiRequest<AgentSessionResponse>('/api/agent/session/clarification/answer', {
    method: 'POST',
    body: payload,
  });
}

export async function reviewAgentSettingProposal(
  payload: ReviewAgentSettingProposalPayload,
): Promise<AgentSessionResponse> {
  return apiRequest<AgentSessionResponse>('/api/agent/session/setting_proposal/review', {
    method: 'POST',
    body: payload,
    timeoutMs: 180_000,
  });
}

export async function listAgentSettingProposals(
  threadId: string,
  status = '',
): Promise<AgentSettingProposalsResponse> {
  const suffix = status ? `?status=${encodeURIComponent(status)}` : '';
  return apiRequest<AgentSettingProposalsResponse>(`/api/agent/session/${threadId}/setting_proposals${suffix}`);
}

export async function reviewAgentSettingProposalsBatch(
  payload: ReviewAgentSettingProposalsBatchPayload,
): Promise<AgentSessionResponse> {
  return apiRequest<AgentSessionResponse>('/api/agent/session/setting_proposals/review_batch', {
    method: 'POST',
    body: payload,
    timeoutMs: 180_000,
  });
}

export async function submitAgentDiffReview(
  payload: SubmitAgentDiffReviewPayload,
): Promise<AgentSessionResponse> {
  return apiRequest<AgentSessionResponse>('/api/agent/session/diff/review', {
    method: 'POST',
    body: payload,
    timeoutMs: 180_000,
  });
}

export async function cancelAgentSession(threadId: string): Promise<AgentSessionResponse> {
  return apiRequest<AgentSessionResponse>(`/api/agent/session/${threadId}/cancel`, {
    method: 'POST',
  });
}

export async function generateChapter(
  projectId: string,
  nodeId: string,
  tokenBudget = 2200,
  workflowMode: WorkflowMode = 'multi_agent',
): Promise<GenerateChapterResponse> {
  return apiRequest<GenerateChapterResponse>('/api/generate/chapter', {
    method: 'POST',
    body: {
      project_id: projectId,
      node_id: nodeId,
      token_budget: tokenBudget,
      workflow_mode: workflowMode,
    },
    timeoutMs: 240_000,
  });
}

export async function fetchProjectInsights(projectId: string): Promise<ProjectInsights> {
  return apiRequest<ProjectInsights>(`/api/projects/${projectId}/insights`);
}

export async function getRuntimeSettings(): Promise<RuntimeSettingsPayload> {
  return apiRequest<RuntimeSettingsPayload>('/api/settings/runtime');
}

export async function listLlmPresets(): Promise<LlmPresetPayload[]> {
  return apiRequest<LlmPresetPayload[]>('/api/llm/presets');
}

export async function updateRuntimeSettings(
  payload: Partial<RuntimeConfigPayload>,
): Promise<RuntimeSettingsPayload> {
  return apiRequest<RuntimeSettingsPayload>('/api/settings/runtime', {
    method: 'PUT',
    body: payload,
  });
}

export async function switchRuntimeProfile(
  profile: string,
  createIfMissing = false,
): Promise<RuntimeSettingsPayload> {
  return apiRequest<RuntimeSettingsPayload>('/api/settings/runtime/switch', {
    method: 'POST',
    body: {
      profile,
      create_if_missing: createIfMissing,
    },
  });
}

export async function createRuntimeProfile(
  profile: string,
  fromProfile = 'core',
): Promise<RuntimeSettingsPayload> {
  return apiRequest<RuntimeSettingsPayload>('/api/settings/runtime/profiles', {
    method: 'POST',
    body: {
      profile,
      from_profile: fromProfile,
    },
  });
}

export async function getProjectBundle(projectId: string): Promise<{
  project: ProjectPayload;
  nodes: GraphNodePayload[];
  edges: GraphEdgePayload[];
}> {
  const [project, nodes, edges] = await Promise.all([
    getProject(projectId),
    listNodes(projectId),
    listEdges(projectId),
  ]);
  return { project, nodes, edges };
}

export async function updateProjectSettings(
  projectId: string,
  payload: Partial<ProjectSettings>,
): Promise<ProjectPayload> {
  return apiRequest<ProjectPayload>(`/api/projects/${projectId}/settings`, {
    method: 'PUT',
    body: payload,
  });
}
