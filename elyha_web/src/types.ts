export type NodeType = 'chapter' | 'group' | 'branch' | 'merge' | 'parallel' | 'checkpoint';

export type NodeStatus = 'draft' | 'generated' | 'reviewed' | 'approved';
export type WorkflowMode = 'single' | 'multi_agent';

export interface ProjectSettings {
  allow_cycles: boolean;
  auto_snapshot_minutes: number;
  auto_snapshot_operations: number;
  system_prompt_style: string;
  system_prompt_forbidden: string;
  system_prompt_notes: string;
}

export interface ProjectPayload {
  id: string;
  title: string;
  active_revision: number;
  created_at: string;
  updated_at: string;
  settings: ProjectSettings;
}

export interface GraphNodePayload {
  id: string;
  project_id: string;
  title: string;
  type: NodeType;
  status: NodeStatus;
  storyline_id: string | null;
  pos_x: number;
  pos_y: number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface GraphEdgePayload {
  id: string;
  project_id: string;
  source_id: string;
  target_id: string;
  label: string;
  narrative_order: number;
  created_at: string;
}

export interface CreateNodePayload {
  title: string;
  type?: NodeType;
  status?: NodeStatus;
  storyline_id?: string | null;
  pos_x?: number;
  pos_y?: number;
  metadata?: Record<string, unknown>;
}

export interface UpdateNodePayload {
  title?: string;
  type?: NodeType;
  status?: NodeStatus;
  storyline_id?: string | null;
  pos_x?: number;
  pos_y?: number;
  metadata?: Record<string, unknown>;
}

export interface RuntimeConfigPayload {
  locale: string;
  llm_provider: string;
  api_url: string;
  api_key: string;
  model_name: string;
  auto_complete: boolean;
  think_switch: boolean;
  think_depth: string;
  thinking_budget: number;
  web_search_enabled: boolean;
  web_search_context_size: string;
  web_search_max_results: number;
  llm_request_timeout: number;
  web_request_timeout_ms: number;
  default_token_budget: number;
  default_workflow_mode: WorkflowMode;
  web_host: string;
  web_port: number;
}

export interface RuntimeSettingsPayload {
  active_profile: string;
  profiles: string[];
  is_core_profile: boolean;
  config: RuntimeConfigPayload;
}

export interface LlmPresetPayload {
  tag: string;
  name: string;
  group: string;
  api_format: string;
  api_url: string;
  auto_complete: boolean;
  default_model: string;
  models: string[];
}

export interface ValidationIssue {
  severity: string;
  code: string;
  message: string;
  node_id?: string;
}

export interface ValidationReport {
  project_id: string;
  errors: number;
  warnings: number;
  infos: number;
  issues: ValidationIssue[];
}

export interface SnapshotPayload {
  id: string;
  project_id: string;
  revision: number;
  path: string;
  created_at: string;
}

export interface AiChatPayload {
  project_id: string;
  message: string;
  node_id?: string;
  token_budget?: number;
}

export interface AiSuggestedOption {
  title: string;
  summary?: string;
  description?: string;
  outline_steps?: string;
  suggested_node_id?: string;
  next_1?: string;
  next_2?: string;
}

export interface AiChatResponse {
  project_id: string;
  node_id: string | null;
  route: string;
  reply: string;
  review_bypassed: boolean;
  updated_node_id: string | null;
  suggested_node_ids: string[];
  suggested_options: AiSuggestedOption[];
  revision: number;
}

export interface GenerateChapterResponse {
  task_id: string;
  project_id: string;
  node_id: string;
  content: string;
  revision: number;
  prompt_tokens: number;
  completion_tokens: number;
  provider: string;
  workflow_mode: string;
  agent_trace: string;
}

export interface ProjectInsights {
  project_id: string;
  revision: number;
  read_only_default: boolean;
  word_frequency: Array<{
    term: string;
    count: number;
    node_ids: string[];
  }>;
  storylines: Array<{
    storyline_id: string;
    node_count: number;
    edge_count: number;
  }>;
  characters: Array<{
    id: string;
    label: string;
    count: number;
    node_ids: string[];
  }>;
  worldviews: Array<{
    id: string;
    label: string;
    count: number;
    node_ids: string[];
  }>;
  items: Array<{
    id: string;
    label: string;
    count: number;
    owner: string;
    node_ids: string[];
  }>;
  relation_graph: {
    nodes: Array<{
      id: string;
      kind: string;
      label: string;
      count: number;
    }>;
    edges: Array<{
      source: string;
      target: string;
      relation: string;
      count: number;
    }>;
  };
}
