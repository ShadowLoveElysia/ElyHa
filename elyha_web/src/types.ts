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
  global_directives: string;
  context_soft_min_chars: number;
  context_soft_max_chars: number;
  context_sentence_safe_expand_chars: number;
  context_soft_max_tokens: number;
  strict_json_fence_output: boolean;
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

export interface ClarificationQuestionPayload {
  project_id: string;
  node_id?: string;
  context?: string;
  token_budget?: number;
}

export interface ClarificationQuestionResponse {
  project_id: string;
  clarification_id: string;
  question_type: string;
  question: string;
  options: Array<{
    value: string;
    label: string;
    reason?: string;
  }>;
  must_answer: boolean;
  timeout_sec: number;
  setting_proposal_status: string;
  provider: string;
  prompt_tokens: number;
  completion_tokens: number;
}

export interface AgentSessionPayload {
  thread_id: string;
  project_id: string;
  node_id: string;
  mode: string;
  status: string;
  state_version: number;
  token_budget: number;
  style_hint: string;
  pending_content: string;
  pending_meta: Record<string, unknown>;
  pending_clarification: Record<string, unknown>;
  latest_clarification_id: string;
  latest_setting_proposal_id: string;
  latest_setting_proposal?: Record<string, unknown> | null;
  last_committed_revision: number;
  last_error: string;
  pending_state_update_count?: number;
  state_update_retry_summary?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface StartAgentSessionPayload {
  project_id: string;
  node_id: string;
  mode?: string;
  token_budget?: number;
  style_hint?: string;
  thread_id?: string;
}

export interface ResumeAgentSessionPayload {
  thread_id: string;
}

export interface SubmitAgentDecisionPayload {
  thread_id: string;
  action: string;
  decision_id: string;
  expected_state_version?: number;
  payload?: Record<string, unknown>;
}

export interface RequestAgentClarificationPayload {
  thread_id: string;
  context?: string;
  token_budget?: number;
}

export interface SubmitAgentClarificationAnswerPayload {
  thread_id: string;
  clarification_id: string;
  decision_id: string;
  selected_option?: string;
  answer_text?: string;
}

export interface ReviewAgentSettingProposalPayload {
  thread_id: string;
  proposal_id: string;
  action: string;
  reviewer?: string;
  note?: string;
  decision_id: string;
  expected_state_version?: number;
}

export interface ReviewAgentSettingProposalsBatchPayload {
  thread_id: string;
  action: string;
  proposal_ids?: string[];
  reviewer?: string;
  note?: string;
  decision_id: string;
  expected_state_version?: number;
}

export interface SubmitAgentDiffReviewPayload {
  thread_id: string;
  diff_id: string;
  decision_id: string;
  accepted_hunk_ids?: string[];
  rejected_hunk_ids?: string[];
  expected_base_revision?: number;
  expected_base_hash?: string;
  expected_state_version?: number;
}

export interface AgentSessionResponse {
  thread_id: string;
  session: AgentSessionPayload;
  clarification_request?: Record<string, unknown>;
  setting_proposal?: Record<string, unknown>;
  setting_proposals?: Array<Record<string, unknown>>;
  diff_review?: Record<string, unknown>;
  commit?: Record<string, unknown>;
  review_action?: string;
  review_count?: number;
}

export interface AgentSettingProposalsResponse {
  thread_id: string;
  status_filter: string;
  setting_proposals: Array<Record<string, unknown>>;
  count: number;
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
