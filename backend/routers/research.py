from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session
from typing import List
import schemas
import models
from database import get_db
from services import conference_service, research_service, research_pipeline

router = APIRouter(
    prefix="/api/research",
    tags=["research"],
    responses={404: {"description": "Not found"}},
)

@router.get("/conferences", response_model=List[schemas.ConferenceSource])
def list_conferences(db: Session = Depends(get_db)):
    return conference_service.list_enabled_conferences(db)

@router.post("/jobs", response_model=schemas.ResearchJobDetail)
def create_research_job(payload: schemas.ResearchJobCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    job = research_service.create_job(db, payload)
    background_tasks.add_task(research_pipeline.run_research_job, job.id)
    return research_service.serialize_job(job, candidate_count=0, selected_candidate_count=0)

@router.get("/jobs", response_model=List[schemas.ResearchJobListItem])
def list_research_jobs(db: Session = Depends(get_db)):
    jobs = db.query(models.ResearchJob).order_by(models.ResearchJob.created_at.desc()).all()
    results = []
    for job in jobs:
        candidate_count = db.query(models.ResearchPaperCandidate).filter(models.ResearchPaperCandidate.research_job_id == job.id).count()
        results.append(research_service.serialize_job_list_item(job, candidate_count))
    return results

@router.get("/jobs/{job_id}", response_model=schemas.ResearchJobDetail)
def get_research_job(job_id: str, db: Session = Depends(get_db)):
    job = research_service.get_job_or_404(db, job_id)
    candidate_count = db.query(models.ResearchPaperCandidate).filter(models.ResearchPaperCandidate.research_job_id == job.id).count()
    selected_candidate_count = db.query(models.ResearchPaperCandidate).filter(
        models.ResearchPaperCandidate.research_job_id == job.id,
        models.ResearchPaperCandidate.is_selected == True,
    ).count()
    return research_service.serialize_job(job, candidate_count, selected_candidate_count)

@router.get("/jobs/{job_id}/candidates", response_model=List[schemas.ResearchPaperCandidate])
def get_research_candidates(job_id: str, db: Session = Depends(get_db)):
    job = research_service.get_job_or_404(db, job_id)
    candidates = db.query(models.ResearchPaperCandidate).filter(
        models.ResearchPaperCandidate.research_job_id == job.id
    ).order_by(
        models.ResearchPaperCandidate.relevance_score.desc(),
        models.ResearchPaperCandidate.created_at.asc(),
    ).all()
    return [research_service.serialize_candidate(candidate) for candidate in candidates]

@router.post("/jobs/{job_id}/import-to-task", response_model=schemas.ResearchImportResponse)
def import_to_task(job_id: str, payload: schemas.ResearchImportRequest, db: Session = Depends(get_db)):
    return research_service.import_candidates_to_task(db, job_id, payload)
