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

export interface Task {
  id: string;
  name: string;
  description?: string;
  template_id?: string;
  model_name?: string;
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
}

export interface CreateTemplatePayload {
  name: string;
  content: string[];
  is_default?: boolean;
}

export interface AddPapersPayload {
  titles: string[];
}

export interface ConferenceSource {
  id: string;
  code: string;
  name: string;
  year: number;
  enabled: boolean;
  paper_count: number;
  created_at: string;
}

export interface ResearchJob {
  id: string;
  query: string;
  selected_conferences: string[];
  mode: string;
  status: string;
  stage: string;
  progress: number;
  model_name: string;
  summary?: string;
  opportunities: string[];
  themes: string[];
  error_message?: string;
  created_at: string;
  updated_at: string;
  candidate_count: number;
  selected_candidate_count?: number;
}

export interface ResearchCandidate {
  id: string;
  conference_paper_id?: string;
  title: string;
  abstract: string;
  conference_label: string;
  relevance_score: number;
  reason?: string;
  status: string;
  is_selected: boolean;
  created_at: string;
}

export interface CreateResearchJobPayload {
  query: string;
  conference_codes: string[];
  mode?: string;
  model_name?: string;
}

export interface ImportResearchCandidatesPayload {
  task_id?: string;
  new_task_name?: string;
  candidate_ids?: string[];
}

export interface ImportResearchCandidatesResponse {
  ok: boolean;
  task_id: string;
  task_name: string;
  imported_count: number;
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
  status: string;
  content: string;
  created_at: string;
  updated_at: string;
}
