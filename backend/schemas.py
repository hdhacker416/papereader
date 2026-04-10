from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class TaskBase(BaseModel):
    name: str
    description: Optional[str] = None
    template_id: Optional[str] = None
    model_name: Optional[str] = "gemini-3-flash-preview"

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    status: Optional[str] = None

class Task(TaskBase):
    id: str
    user_id: str
    status: str
    model_name: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class PaperBase(BaseModel):
    title: str

class PaperCreate(BaseModel):
    titles: List[str]

class Interpretation(BaseModel):
    content: str
    template_used: str
    created_at: datetime

    class Config:
        from_attributes = True

class Paper(PaperBase):
    id: str
    task_id: str
    pdf_path: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    status: str
    failure_reason: Optional[str] = None
    created_at: datetime
    interpretation: Optional[Interpretation] = None

    class Config:
        from_attributes = True

class TemplateBase(BaseModel):
    name: str
    content: List[str]
    is_default: bool = False

class TemplateCreate(TemplateBase):
    pass

class Template(TemplateBase):
    id: str
    user_id: str
    created_at: datetime

    class Config:
        from_attributes = True

class TemplateUpdate(BaseModel):
    is_default: Optional[bool] = None

class TaskStatistics(BaseModel):
    total: int
    done: int
    failed: int
    skipped: int
    queued: int
    processing: int

class TaskWithStats(Task):
    statistics: TaskStatistics

class TaskBatchDelete(BaseModel):
    ids: List[str]

class ReReadRequest(BaseModel):
    template_id: Optional[str] = None
    model_name: Optional[str] = None


class DeepResearchReport(BaseModel):
    id: str
    task_id: str
    query: Optional[str] = None
    source_type: str
    source_meta: Optional[str] = None
    status: str
    content: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ConferenceSource(BaseModel):
    id: str
    code: str
    name: str
    year: int
    enabled: bool
    paper_count: int
    created_at: datetime

    class Config:
        from_attributes = True

class ResearchJobCreate(BaseModel):
    query: str
    conference_codes: List[str]
    mode: Optional[str] = "quick"
    model_name: Optional[str] = "gemini-3-flash-preview"

class ResearchPaperCandidate(BaseModel):
    id: str
    conference_paper_id: Optional[str] = None
    title: str
    abstract: str
    conference_label: str
    relevance_score: float
    reason: Optional[str] = None
    status: str
    is_selected: bool
    created_at: datetime

class ResearchJobBase(BaseModel):
    id: str
    query: str
    selected_conferences: List[str]
    mode: str
    status: str
    stage: str
    progress: int
    model_name: str
    summary: Optional[str] = None
    opportunities: List[str]
    themes: List[str]
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class ResearchJobListItem(ResearchJobBase):
    candidate_count: int

class ResearchJobDetail(ResearchJobBase):
    candidate_count: int
    selected_candidate_count: int

class ResearchImportRequest(BaseModel):
    task_id: Optional[str] = None
    new_task_name: Optional[str] = None
    candidate_ids: Optional[List[str]] = None

class ResearchImportResponse(BaseModel):
    ok: bool
    task_id: str
    task_name: str
    imported_count: int


class ConferenceSearchRequest(BaseModel):
    query: str
    conferences: Optional[List[str]] = None
    years: Optional[List[int]] = None
    top_k_per_asset: int = 10
    top_k_global: int = 30


class ConferenceSearchHit(BaseModel):
    paper_id: str
    conference: str
    year: int
    title: str
    abstract: str
    authors: List[str]
    source_url: str
    coarse_score: float


class ConferenceSearchResponse(BaseModel):
    query: str
    asset_count: int
    elapsed_sec: float
    results: List[ConferenceSearchHit]


class TaskPaperSelection(BaseModel):
    paper_id: str
    conference: str
    year: int


class TaskFromSelectionCreate(BaseModel):
    name: str
    description: Optional[str] = None
    template_id: Optional[str] = None
    model_name: Optional[str] = "gemini-3-flash-preview"
    selected_papers: List[TaskPaperSelection]


class AutoResearchTaskCreate(BaseModel):
    query: str
    name: Optional[str] = None
    description: Optional[str] = None
    conferences: Optional[List[str]] = None
    years: Optional[List[int]] = None
    template_id: Optional[str] = None
    model_name: Optional[str] = "gemini-3-flash-preview"
    rerank_score_threshold: float = 0.5
    min_papers: int = 5
    max_papers: int = 12


class DeepResearchTaskCreateResponse(BaseModel):
    ok: bool
    task_id: str
    task_name: str
    imported_count: int


class TaskReportGenerateRequest(BaseModel):
    query: Optional[str] = None
    source_type: Optional[str] = "task"
    source_meta: Optional[str] = None
