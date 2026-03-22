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
  constitution_markdown: string;
  clarify_markdown: string;
  specification_markdown: string;
  plan_markdown: string;
  guide_skipped_docs: string[];
  global_directives: string;
  context_soft_min_chars: number;
  context_soft_max_chars: number;
  context_sentence_safe_expand_chars: number;
  context_soft_max_tokens: number;
  strict_json_fence_output: boolean;
  context_compaction_enabled: boolean;
  context_compaction_trigger_ratio: number;
  context_compaction_keep_recent_chunks: number;
  context_compaction_group_chunks: number;
  context_compaction_chunk_chars: number;
  agent_tool_loop_enabled: boolean;
  agent_tool_loop_max_rounds: number;
  agent_tool_loop_max_calls_per_round: number;
  agent_tool_loop_single_read_char_limit: number;
  agent_tool_loop_total_read_char_limit: number;
  agent_tool_loop_no_progress_limit: number;
  agent_tool_write_proposal_enabled: boolean;
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
  llm_transport: string;
  api_url: string;
  api_key: string;
  api_key_mask: string;
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
  llm_transport: string;
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
  thread_id?: string;
  allow_node_write?: boolean;
  guide_mode?: boolean;
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
  thread_id: string;
  route: string;
  reply: string;
  review_bypassed: boolean;
  updated_node_id: string | null;
  suggested_node_ids: string[];
  suggested_options: AiSuggestedOption[];
  guide_skip_document?: string;
  revision: number;
}

export interface ChatThreadSummary {
  thread_id: string;
  project_id: string;
  node_id: string;
  created_at: string;
  updated_at: string;
  last_role: string;
  last_content: string;
  last_message_at: string;
  message_count: number;
}

export interface ChatMessagePayload {
  role: string;
  content: string;
  created_at: string;
}

export interface ChatThreadsResponse {
  project_id: string;
  count: number;
  threads: ChatThreadSummary[];
}

export interface ChatThreadCreateResponse {
  project_id: string;
  thread_id: string;
  thread: ChatThreadSummary;
}

export interface ChatThreadMessagesResponse {
  project_id: string;
  thread_id: string;
  count: number;
  messages: ChatMessagePayload[];
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

export interface SubmitAgentDecisionPayload {
  thread_id: string;
  action: string;
  decision_id: string;
  expected_state_version?: number;
  payload?: Record<string, unknown>;
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

export interface SubmitAgentDiffReviewPayload {
  thread_id: string;
  diff_id: string;
  decision_id: string;
  accepted_hunk_ids?: string[];
  rejected_hunk_ids?: string[];
  edited_hunks?: Array<{
    hunk_id: string;
    new_text: string;
  }>;
  expected_base_revision?: number;
  expected_base_hash?: string;
  expected_state_version?: number;
}

export interface LatestProjectAgentSessionResponse {
  project_id: string;
  thread_id: string;
  session: AgentSessionPayload | null;
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
    name: string;
    count: number;
    node_ids: string[];
  }>;
  worldviews: Array<{
    name: string;
    count: number;
    node_ids: string[];
  }>;
  items: Array<{
    name: string;
    count: number;
    owner: string;
    node_ids: string[];
  }>;
  relation_graph: {
    nodes: Array<{
      id: string;
      type: string;
      label: string;
      weight: number;
      node_ids: string[];
    }>;
    edges: Array<{
      source: string;
      target: string;
      relation: string;
      weight: number;
    }>;
  };
}

export interface RelationshipStatusPayload {
  project_id: string;
  subject_character_id: string;
  object_character_id: string;
  relation_type: string;
  state_attributes: Record<string, unknown>;
  last_event_id: string;
  updated_at: string;
}

export interface CharacterStatusPayload {
  project_id: string;
  character_id: string;
  alive: boolean;
  location: string;
  faction: string;
  held_items: string[];
  state_attributes: Record<string, unknown>;
  last_event_id: string;
  updated_at: string;
}

export interface ItemStatusPayload {
  project_id: string;
  item_id: string;
  owner_character_id: string;
  location: string;
  destroyed: boolean;
  state_attributes: Record<string, unknown>;
  last_event_id: string;
  updated_at: string;
}

export interface UpsertRelationshipPayload {
  project_id: string;
  subject_character_id: string;
  object_character_id: string;
  relation_type: string;
  node_id?: string;
  source_excerpt?: string;
  confidence?: number;
  state_attributes?: Record<string, unknown>;
}
