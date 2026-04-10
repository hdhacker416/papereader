import json
from fastapi import HTTPException
from sqlalchemy.orm import Session
import models
import schemas
from services import conference_service
from routers.tasks import DEFAULT_USER_ID

DEFAULT_RESEARCH_TEMPLATE = [
    "Summarize the paper's main contribution, technical method, experimental evidence, limitations, and the most important safety implications."
]

def ensure_default_template(db: Session):
    template = db.query(models.Template).filter(models.Template.user_id == DEFAULT_USER_ID, models.Template.is_default == True).first()
    if template:
        return template

    template = db.query(models.Template).filter(models.Template.user_id == DEFAULT_USER_ID).first()
    if template:
        template.is_default = True
        db.commit()
        db.refresh(template)
        return template

    template = models.Template(
        user_id=DEFAULT_USER_ID,
        name="Default Paper Summary",
        content=json.dumps(DEFAULT_RESEARCH_TEMPLATE),
        is_default=True,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template

def serialize_job(job: models.ResearchJob, candidate_count: int, selected_candidate_count: int = 0):
    return schemas.ResearchJobDetail(
        id=job.id,
        query=job.query,
        selected_conferences=json.loads(job.selected_conferences_json or "[]"),
        mode=job.mode,
        status=job.status,
        stage=job.stage,
        progress=job.progress or 0,
        model_name=job.model_name or "gemini-3-flash-preview",
        summary=job.summary,
        opportunities=json.loads(job.opportunities or "[]"),
        themes=json.loads(job.themes or "[]"),
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
        candidate_count=candidate_count,
        selected_candidate_count=selected_candidate_count,
    )

def serialize_job_list_item(job: models.ResearchJob, candidate_count: int):
    return schemas.ResearchJobListItem(
        id=job.id,
        query=job.query,
        selected_conferences=json.loads(job.selected_conferences_json or "[]"),
        mode=job.mode,
        status=job.status,
        stage=job.stage,
        progress=job.progress or 0,
        model_name=job.model_name or "gemini-3-flash-preview",
        summary=job.summary,
        opportunities=json.loads(job.opportunities or "[]"),
        themes=json.loads(job.themes or "[]"),
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
        candidate_count=candidate_count,
    )

def create_job(db: Session, payload: schemas.ResearchJobCreate):
    conference_map = conference_service.get_conference_map(db, payload.conference_codes)
    if len(conference_map) != len(payload.conference_codes):
        raise HTTPException(status_code=404, detail="One or more conferences were not found")

    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    job = models.ResearchJob(
        user_id=DEFAULT_USER_ID,
        query=query,
        selected_conferences_json=json.dumps(payload.conference_codes),
        mode=payload.mode or "quick",
        status="created",
        stage="created",
        progress=0,
        model_name=payload.model_name or "gemini-3-flash-preview",
        opportunities=json.dumps([]),
        themes=json.dumps([]),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job

def get_job_or_404(db: Session, job_id: str):
    job = db.query(models.ResearchJob).filter(models.ResearchJob.id == job_id, models.ResearchJob.user_id == DEFAULT_USER_ID).first()
    if not job:
        raise HTTPException(status_code=404, detail="Research job not found")
    return job

def serialize_candidate(candidate: models.ResearchPaperCandidate):
    return schemas.ResearchPaperCandidate(
        id=candidate.id,
        conference_paper_id=candidate.conference_paper_id,
        title=candidate.title,
        abstract=candidate.abstract,
        conference_label=candidate.conference_label,
        relevance_score=candidate.relevance_score or 0.0,
        reason=candidate.reason,
        status=candidate.status,
        is_selected=bool(candidate.is_selected),
        created_at=candidate.created_at,
    )

def import_candidates_to_task(db: Session, job_id: str, payload: schemas.ResearchImportRequest):
    job = get_job_or_404(db, job_id)
    candidate_query = db.query(models.ResearchPaperCandidate).filter(models.ResearchPaperCandidate.research_job_id == job.id)
    if payload.candidate_ids:
        candidate_query = candidate_query.filter(models.ResearchPaperCandidate.id.in_(payload.candidate_ids))
    candidates = candidate_query.all()

    if not candidates:
        raise HTTPException(status_code=400, detail="No candidates selected for import")

    task = None
    if payload.task_id:
        task = db.query(models.Task).filter(models.Task.id == payload.task_id, models.Task.user_id == DEFAULT_USER_ID).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
    else:
        template = ensure_default_template(db)
        task_name = (payload.new_task_name or f"Research: {job.query[:40]}").strip()
        task = models.Task(
            user_id=DEFAULT_USER_ID,
            name=task_name,
            description=f"Imported from Deep Research job {job.id}",
            template_id=template.id,
            model_name=job.model_name or "gemini-3-flash-preview",
            status="running",
        )
        db.add(task)
        db.commit()
        db.refresh(task)

    existing_titles = {
        paper.title
        for paper in db.query(models.Paper).filter(models.Paper.task_id == task.id).all()
    }

    imported_count = 0
    for candidate in candidates:
        if candidate.title in existing_titles:
            continue
        db.add(models.Paper(task_id=task.id, title=candidate.title, status="queued"))
        existing_titles.add(candidate.title)
        imported_count += 1

    db.commit()
    return schemas.ResearchImportResponse(
        ok=True,
        task_id=task.id,
        task_name=task.name,
        imported_count=imported_count,
    )
