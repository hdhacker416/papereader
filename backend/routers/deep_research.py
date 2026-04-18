from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import schemas
from database import get_db
from services import deep_research_service
from services import report_generation_service


router = APIRouter(
    prefix="/api/deep-research",
    tags=["deep-research"],
    responses={404: {"description": "Not found"}},
)


@router.post("/search", response_model=schemas.ConferenceSearchResponse)
def search_conference_papers(
    payload: schemas.ConferenceSearchRequest,
):
    return deep_research_service.search_conference_papers(payload)


@router.get("/targets", response_model=schemas.DeepResearchTargetOptionsResponse)
def list_target_options():
    return deep_research_service.list_target_options()


@router.get("/self-check", response_model=schemas.SelfCheckResponse)
def run_self_check():
    return deep_research_service.run_self_check()


@router.get("/releases", response_model=schemas.ReleaseListResponse)
def list_release_packs():
    return deep_research_service.list_release_packs()


@router.post("/releases/install", response_model=schemas.ReleaseInstallResponse)
def install_release_packs(
    payload: schemas.ReleaseInstallRequest,
):
    return deep_research_service.install_release_assets(payload)


@router.get("/packs", response_model=list[schemas.ResearchPackInfo])
def list_local_packs():
    return deep_research_service.list_local_packs()


@router.get("/packs/installed", response_model=list[schemas.InstalledResearchPackInfo])
def list_installed_packs():
    return deep_research_service.list_installed_packs()


@router.get("/pack-targets", response_model=schemas.PackTargetOptionsResponse)
def list_pack_target_options():
    return deep_research_service.list_pack_target_options()


@router.get("/packs/jobs", response_model=list[schemas.PackBuildJob])
def list_pack_build_jobs(
    db: Session = Depends(get_db),
):
    return deep_research_service.list_pack_build_jobs(db)


@router.post("/packs/jobs", response_model=schemas.PackBuildJob)
def create_pack_build_job(
    payload: schemas.ResearchPackBuildRequest,
    db: Session = Depends(get_db),
):
    return deep_research_service.create_pack_build_job(db, payload)


@router.post("/packs/jobs/{job_id}/resume", response_model=schemas.PackBuildJob)
def resume_pack_build_job(
    job_id: str,
    db: Session = Depends(get_db),
):
    return deep_research_service.resume_pack_build_job(db, job_id)


@router.post("/packs/build", response_model=schemas.ResearchPackBuildResponse)
def build_packs(
    payload: schemas.ResearchPackBuildRequest,
):
    return deep_research_service.build_packs(payload)


@router.post("/packs/upload", response_model=schemas.ResearchPackUploadResponse)
def upload_pack(
    payload: schemas.ResearchPackUploadRequest,
):
    return deep_research_service.upload_pack_to_github_release(payload)


@router.post("/tasks/from-selection", response_model=schemas.DeepResearchTaskCreateResponse)
def create_task_from_selection(
    payload: schemas.TaskFromSelectionCreate,
    db: Session = Depends(get_db),
):
    return deep_research_service.create_task_from_selection(db, payload)


@router.post("/tasks/auto-create", response_model=schemas.DeepResearchTaskCreateResponse)
def create_task_from_auto_research(
    payload: schemas.AutoResearchTaskCreate,
    db: Session = Depends(get_db),
):
    return deep_research_service.create_task_from_auto_research(db, payload)


@router.post("/tasks/{task_id}/report", response_model=schemas.DeepResearchReport)
def generate_task_report(
    task_id: str,
    payload: schemas.TaskReportGenerateRequest,
    db: Session = Depends(get_db),
):
    return report_generation_service.enqueue_task_report_generation(db, task_id, payload)


@router.get("/tasks/{task_id}/report", response_model=schemas.DeepResearchReport | None)
def get_task_report(
    task_id: str,
    db: Session = Depends(get_db),
):
    return deep_research_service.get_task_report(db, task_id)
