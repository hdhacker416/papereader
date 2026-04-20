from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class TaskBase(BaseModel):
    name: str
    description: Optional[str] = None
    template_id: Optional[str] = None
    model_name: Optional[str] = "gemini-3-flash-preview"
    custom_reading_prompts: Optional[List[str]] = None
    agent_trace: Optional[dict] = None

class TaskCreate(TaskBase):
    custom_reading_prompts: Optional[List[str]] = None

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
    custom_reading_prompts: Optional[List[str]] = None
    only_failed: bool = False


class DeepResearchReport(BaseModel):
    id: str
    task_id: str
    query: Optional[str] = None
    source_type: str
    source_meta: Optional[str] = None
    model_name: Optional[str] = None
    status: str
    content: str
    progress_stage: Optional[str] = None
    progress_message: Optional[str] = None
    progress_completed: int = 0
    progress_total: int = 0
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InstalledResearchPackInfo(BaseModel):
    conference: str
    year: int
    version: str
    pack_name: str
    install_dir: str
    manifest_path: str
    normalized_path: str
    embedding_path: str


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


class DeepResearchTargetYearCount(BaseModel):
    year: int
    paper_count: int


class DeepResearchTargetConference(BaseModel):
    code: str
    label: str
    years: List[DeepResearchTargetYearCount]
    total_paper_count: int


class DeepResearchTargetOptionsResponse(BaseModel):
    conferences: List[DeepResearchTargetConference]
    years: List[int]
    default_years: List[int]


class SelfCheckItem(BaseModel):
    key: str
    label: str
    status: str
    severity: str
    message: str
    hint: Optional[str] = None
    details: Optional[dict] = None


class SelfCheckResponse(BaseModel):
    overall_status: str
    summary: str
    checked_at: datetime
    items: List[SelfCheckItem]


class TaskPaperSelection(BaseModel):
    paper_id: str
    conference: str
    year: int


class TaskFromSelectionCreate(BaseModel):
    name: str
    description: Optional[str] = None
    template_id: Optional[str] = None
    model_name: Optional[str] = "gemini-3-flash-preview"
    custom_reading_prompts: Optional[List[str]] = None
    selected_papers: List[TaskPaperSelection]


class AutoResearchTaskCreate(BaseModel):
    query: str
    name: Optional[str] = None
    description: Optional[str] = None
    conferences: Optional[List[str]] = None
    years: Optional[List[int]] = None
    template_id: Optional[str] = None
    model_name: Optional[str] = "gemini-3-flash-preview"
    custom_reading_prompts: Optional[List[str]] = None
    max_search_rounds: Optional[int] = None
    max_queries_per_round: Optional[int] = None
    max_full_reads: Optional[int] = None


class DeepResearchTaskCreateResponse(BaseModel):
    ok: bool
    task_id: str
    task_name: str
    imported_count: int


class TaskReportGenerateRequest(BaseModel):
    query: Optional[str] = None
    source_type: Optional[str] = "task"
    source_meta: Optional[str] = None
    model_name: Optional[str] = "gemini-3-flash-preview"


class ReleaseAsset(BaseModel):
    id: int
    name: str
    size: int
    download_count: int
    browser_download_url: str
    updated_at: datetime


class ReleaseInfo(BaseModel):
    id: int
    tag_name: str
    name: str
    draft: bool
    prerelease: bool
    published_at: Optional[datetime] = None
    html_url: str
    assets: List[ReleaseAsset]


class ReleaseListResponse(BaseModel):
    owner: str
    repo: str
    releases: List[ReleaseInfo]


class ReleaseAssetInstallItem(BaseModel):
    release_tag: str
    asset_name: str
    download_url: str


class ReleaseInstallRequest(BaseModel):
    assets: List[ReleaseAssetInstallItem]


class ReleaseInstallResult(BaseModel):
    release_tag: str
    asset_name: str
    installed: bool
    conference: Optional[str] = None
    year: Optional[int] = None
    version: Optional[str] = None
    install_dir: Optional[str] = None
    error: Optional[str] = None


class ReleaseInstallResponse(BaseModel):
    ok: bool
    installed_count: int
    results: List[ReleaseInstallResult]


class ResearchPackInfo(BaseModel):
    conference: str
    year: int
    version: str
    pack_name: str
    pack_path: str
    manifest_path: str
    sha256_path: str
    pack_size_bytes: int
    exists: bool


class PackTargetConference(BaseModel):
    code: str
    label: str
    years: List[int]


class PackTargetOptionsResponse(BaseModel):
    conferences: List[PackTargetConference]
    years: List[int]
    default_years: List[int]


class PackBuildTargetState(BaseModel):
    conference: str
    year: int
    label: str
    status: str
    current_stage: Optional[str] = None
    error: Optional[str] = None
    pack_name: Optional[str] = None


class PackBuildJob(BaseModel):
    id: str
    status: str
    version: str
    requested_conferences: List[str]
    requested_years: List[int]
    total_targets: int
    completed_targets: int
    failed_targets: int
    current_conference: Optional[str] = None
    current_year: Optional[int] = None
    current_stage: Optional[str] = None
    current_step_completed: int
    current_step_total: int
    progress_percent: float
    progress_message: Optional[str] = None
    target_states: List[PackBuildTargetState]
    error: Optional[str] = None
    can_resume: bool = False
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class ResearchPackBuildRequest(BaseModel):
    conferences: Optional[List[str]] = None
    years: Optional[List[int]] = None
    version: Optional[str] = "v1"


class ResearchPackBuildResponse(BaseModel):
    ok: bool
    results: List[ResearchPackInfo]


class ResearchPackUploadRequest(BaseModel):
    conference: str
    year: int
    version: Optional[str] = "v1"
    owner: str
    repo: str
    tag: str
    release_name: Optional[str] = None
    release_body: Optional[str] = None
    draft: bool = False
    prerelease: bool = False


class ResearchPackUploadResponse(BaseModel):
    ok: bool
    release_id: int
    release_url: str
    uploaded_assets: List[str]
