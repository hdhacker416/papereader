export interface Template {
  id: string;
  name: string;
  content: string[];
  is_default: boolean;
  created_at: string;
}

export interface TaskStatistics {
  total: number;
  done: number;
  failed: number;
  skipped: number;
  queued: number;
  processing: number;
}

export interface AgentTrace {
  用户问题?: string;
  预算?: Record<string, number>;
  研究简报?: Record<string, unknown>;
  搜索轮次?: Array<Record<string, unknown>>;
  最终选中文章?: Array<Record<string, unknown>>;
  汇总?: Record<string, unknown>;
}

export interface Task {
  id: string;
  name: string;
  description?: string;
  template_id?: string;
  model_name?: string;
  custom_reading_prompts?: string[];
  agent_trace?: AgentTrace;
  status: string;
  created_at: string;
  updated_at: string;
  statistics?: TaskStatistics;
}

export interface Interpretation {
  content: string;
  template_used: string;
  created_at: string;
}

export interface Paper {
  id: string;
  task_id: string;
  title: string;
  pdf_path?: string;
  source?: string;
  source_url?: string;
  status: string;
  failure_reason?: string;
  created_at: string;
  interpretation?: Interpretation;
}

export interface ChatMessage {
  id?: string;
  role: 'user' | 'assistant';
  content: string;
  cost?: number;
  time_cost?: number;
  created_at?: string;
}

export interface Note {
  content: string;
}

export interface Collection {
  id: string;
  name: string;
  parent_id?: string;
}

export interface CreateTaskPayload {
  name: string;
  description?: string;
  template_id: string;
  model_name?: string;
  custom_reading_prompts?: string[];
}

export interface CreateTemplatePayload {
  name: string;
  content: string[];
  is_default?: boolean;
}

export interface AddPapersPayload {
  titles: string[];
}

export interface ConferenceSearchHit {
  paper_id: string;
  conference: string;
  year: number;
  title: string;
  abstract: string;
  authors: string[];
  source_url: string;
  coarse_score: number;
}

export interface ConferenceSearchResponse {
  query: string;
  asset_count: number;
  elapsed_sec: number;
  results: ConferenceSearchHit[];
}

export interface DeepResearchTargetYearCount {
  year: number;
  paper_count: number;
}

export interface DeepResearchTargetConference {
  code: string;
  label: string;
  years: DeepResearchTargetYearCount[];
  total_paper_count: number;
}

export interface DeepResearchTargetOptionsResponse {
  conferences: DeepResearchTargetConference[];
  years: number[];
  default_years: number[];
}

export interface SelfCheckItem {
  key: string;
  label: string;
  status: 'ok' | 'warning' | 'error';
  severity: 'required' | 'optional';
  message: string;
  hint?: string;
  details?: Record<string, unknown>;
}

export interface SelfCheckResponse {
  overall_status: 'ok' | 'warning' | 'error';
  summary: string;
  checked_at: string;
  items: SelfCheckItem[];
}

export interface DeepResearchTaskCreateResponse {
  ok: boolean;
  task_id: string;
  task_name: string;
  imported_count: number;
}

export interface DeepResearchReport {
  id: string;
  task_id: string;
  query?: string;
  source_type: string;
  source_meta?: string;
  model_name?: string;
  status: string;
  content: string;
  progress_stage?: string;
  progress_message?: string;
  progress_completed: number;
  progress_total: number;
  error?: string;
  created_at: string;
  updated_at: string;
}

export interface InstalledResearchPackInfo {
  conference: string;
  year: number;
  version: string;
  pack_name: string;
  install_dir: string;
  manifest_path: string;
  normalized_path: string;
  embedding_path: string;
}

export interface ReleaseAsset {
  id: number;
  name: string;
  size: number;
  download_count: number;
  browser_download_url: string;
  updated_at: string;
}

export interface ReleaseInfo {
  id: number;
  tag_name: string;
  name: string;
  draft: boolean;
  prerelease: boolean;
  published_at?: string;
  html_url: string;
  assets: ReleaseAsset[];
}

export interface ReleaseListResponse {
  owner: string;
  repo: string;
  releases: ReleaseInfo[];
}

export interface ReleaseInstallResult {
  release_tag: string;
  asset_name: string;
  installed: boolean;
  conference?: string;
  year?: number;
  version?: string;
  install_dir?: string;
  error?: string;
}

export interface ReleaseInstallResponse {
  ok: boolean;
  installed_count: number;
  results: ReleaseInstallResult[];
}

export interface ResearchPackInfo {
  conference: string;
  year: number;
  version: string;
  pack_name: string;
  pack_path: string;
  manifest_path: string;
  sha256_path: string;
  pack_size_bytes: number;
  exists: boolean;
}

export interface PackTargetConference {
  code: string;
  label: string;
  years: number[];
}

export interface PackTargetOptionsResponse {
  conferences: PackTargetConference[];
  years: number[];
  default_years: number[];
}

export interface PackBuildTargetState {
  conference: string;
  year: number;
  label: string;
  status: string;
  current_stage?: string;
  error?: string;
  pack_name?: string;
}

export interface PackBuildJob {
  id: string;
  status: string;
  version: string;
  requested_conferences: string[];
  requested_years: number[];
  total_targets: number;
  completed_targets: number;
  failed_targets: number;
  current_conference?: string;
  current_year?: number;
  current_stage?: string;
  current_step_completed: number;
  current_step_total: number;
  progress_percent: number;
  progress_message?: string;
  target_states: PackBuildTargetState[];
  error?: string;
  can_resume: boolean;
  created_at: string;
  updated_at: string;
  started_at?: string;
  finished_at?: string;
}

export interface ResearchPackBuildResponse {
  ok: boolean;
  results: ResearchPackInfo[];
}

export interface ResearchPackUploadResponse {
  ok: boolean;
  release_id: number;
  release_url: string;
  uploaded_assets: string[];
}
