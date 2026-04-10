from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import schemas
from database import get_db
from services import deep_research_service


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
    return deep_research_service.generate_task_report(db, task_id, payload)


@router.get("/tasks/{task_id}/report", response_model=schemas.DeepResearchReport)
def get_task_report(
    task_id: str,
    db: Session = Depends(get_db),
):
    return deep_research_service.get_task_report(db, task_id)
