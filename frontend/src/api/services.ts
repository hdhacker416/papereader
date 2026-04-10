import api from './index';
import { 
  Task, 
  CreateTaskPayload, 
  Template, 
  CreateTemplatePayload, 
  Paper, 
  AddPapersPayload,
  ChatMessage,
  Note,
  Collection,
  ConferenceSource,
  ResearchJob,
  CreateResearchJobPayload,
  ResearchCandidate,
  ImportResearchCandidatesPayload,
  ImportResearchCandidatesResponse,
  ConferenceSearchResponse,
  DeepResearchTaskCreateResponse,
  DeepResearchReport
} from '../types';

export const templatesApi = {
  list: () => api.get<Template[]>('/templates/').then(res => res.data),
  create: (data: CreateTemplatePayload) => api.post<Template>('/templates/', data).then(res => res.data),
  delete: (id: string) => api.delete(`/templates/${id}`).then(res => res.data),
  setDefault: (id: string) => api.put<Template>(`/templates/${id}/default`).then(res => res.data),
};

export const tasksApi = {
  list: () => api.get<Task[]>('/tasks/').then(res => res.data),
  get: (id: string) => api.get<Task>(`/tasks/${id}`).then(res => res.data),
  create: (data: CreateTaskPayload) => api.post<Task>('/tasks/', data).then(res => res.data),
  updateStatus: (id: string, status: string) => api.put<Task>(`/tasks/${id}`, { status }).then(res => res.data),
  delete: (id: string) => api.delete<{ok: boolean}>(`/tasks/${id}`).then(res => res.data),
  batchDelete: (ids: string[]) => api.post<{deleted: number}>('/tasks/batch-delete', { ids }).then(res => res.data),
  addPapers: (id: string, data: AddPapersPayload) => api.post<Paper[]>(`/tasks/${id}/papers`, data).then(res => res.data),
  getPapers: (id: string) => api.get<Paper[]>(`/tasks/${id}/papers`).then(res => res.data),
  reRead: (id: string, template_id?: string, model_name?: string) => api.post<{ok: boolean, count: number}>(`/tasks/${id}/reread`, { template_id, model_name }).then(res => res.data),
};

export const papersApi = {
  get: (id: string) => api.get<Paper>(`/papers/${id}`).then(res => res.data),
  chat: (id: string, message: string) => api.post<ChatMessage>(`/papers/${id}/chat`, { message }).then(res => res.data),
  getChatHistory: (id: string) => api.get<ChatMessage[]>(`/papers/${id}/chat`).then(res => res.data),
  clearChat: (id: string) => api.delete<{ok: boolean}>(`/papers/${id}/chat`).then(res => res.data),
  updateNotes: (id: string, content: string) => api.put<{ok: boolean}>(`/papers/${id}/notes`, { content }).then(res => res.data),
  getNotes: (id: string) => api.get<Note>(`/papers/${id}/notes`).then(res => res.data),
  retry: (id: string) => api.post<{ok: boolean}>(`/papers/${id}/retry`).then(res => res.data),
  delete: (id: string) => api.delete<{ok: boolean}>(`/papers/${id}`).then(res => res.data),
};

export const collectionsApi = {
  list: () => api.get<Collection[]>('/collections/').then(res => res.data),
  create: (name: string, parent_id?: string) => api.post<Collection>('/collections/', { name, parent_id }).then(res => res.data),
  delete: (id: string) => api.delete(`/collections/${id}`).then(res => res.data),
  getPapers: (id: string) => api.get<Paper[]>(`/collections/${id}/papers`).then(res => res.data),
  addPaper: (collectionId: string, paperId: string) => api.post(`/collections/${collectionId}/papers/${paperId}`).then(res => res.data),
  removePaper: (collectionId: string, paperId: string) => api.delete(`/collections/${collectionId}/papers/${paperId}`).then(res => res.data),
  getPaperCollections: (paperId: string) => api.get<Collection[]>(`/collections/paper/${paperId}`).then(res => res.data),
  reRead: (id: string, template_id?: string, model_name?: string) => api.post<{ok: boolean, count: number}>(`/collections/${id}/reread`, { template_id, model_name }).then(res => res.data),
};

export const researchApi = {
  listConferences: () => api.get<ConferenceSource[]>('/research/conferences').then(res => res.data),
  listJobs: () => api.get<ResearchJob[]>('/research/jobs').then(res => res.data),
  getJob: (id: string) => api.get<ResearchJob>(`/research/jobs/${id}`).then(res => res.data),
  createJob: (data: CreateResearchJobPayload) => api.post<ResearchJob>('/research/jobs', data).then(res => res.data),
  getCandidates: (id: string) => api.get<ResearchCandidate[]>(`/research/jobs/${id}/candidates`).then(res => res.data),
  importToTask: (id: string, data: ImportResearchCandidatesPayload) => api.post<ImportResearchCandidatesResponse>(`/research/jobs/${id}/import-to-task`, data).then(res => res.data),
};

export const deepResearchApi = {
  search: (data: {
    query: string;
    conferences?: string[];
    years?: number[];
    top_k_per_asset?: number;
    top_k_global?: number;
  }) => api.post<ConferenceSearchResponse>('/deep-research/search', data).then(res => res.data),
  createTaskFromSelection: (data: {
    name: string;
    description?: string;
    template_id?: string;
    model_name?: string;
    selected_papers: Array<{ paper_id: string; conference: string; year: number }>;
  }) => api.post<DeepResearchTaskCreateResponse>('/deep-research/tasks/from-selection', data).then(res => res.data),
  createTaskFromAutoResearch: (data: {
    query: string;
    name?: string;
    description?: string;
    conferences?: string[];
    years?: number[];
    template_id?: string;
    model_name?: string;
    rerank_score_threshold?: number;
    min_papers?: number;
    max_papers?: number;
  }) => api.post<DeepResearchTaskCreateResponse>('/deep-research/tasks/auto-create', data).then(res => res.data),
  generateTaskReport: (taskId: string, data: { query?: string; source_type?: string; source_meta?: string }) =>
    api.post<DeepResearchReport>(`/deep-research/tasks/${taskId}/report`, data).then(res => res.data),
  getTaskReport: (taskId: string) =>
    api.get<DeepResearchReport>(`/deep-research/tasks/${taskId}/report`).then(res => res.data),
};
