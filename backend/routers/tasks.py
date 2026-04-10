from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import models, schemas
from database import get_db

router = APIRouter(
    prefix="/api/tasks",
    tags=["tasks"],
    responses={404: {"description": "Not found"}},
)

# Dummy user ID for now
DEFAULT_USER_ID = "default_user_id"

@router.post("/", response_model=schemas.Task)
def create_task(task: schemas.TaskCreate, db: Session = Depends(get_db)):
    # Check if template exists
    if task.template_id:
        template = db.query(models.Template).filter(models.Template.id == task.template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
    else:
        # Require template_id for creation, unless we allow task without template?
        # User UI requires it, so we can enforce it here or allow it.
        # Let's enforce it for now to match previous logic, but handle missing case gracefully if needed.
        # If we made it Optional in schema, Pydantic won't block None.
        raise HTTPException(status_code=400, detail="Template ID is required")
    
    db_task = models.Task(**task.dict(), user_id=DEFAULT_USER_ID, status="running")
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task

@router.post("/{task_id}/reread")
def reread_task(task_id: str, request: schemas.ReReadRequest, db: Session = Depends(get_db)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Update Task defaults if provided
    if request.template_id:
        task.template_id = request.template_id
    if request.model_name:
        task.model_name = request.model_name
    
    # Reset all papers in task
    papers = db.query(models.Paper).filter(models.Paper.task_id == task.id).all()
    for paper in papers:
        paper.status = "queued"
        paper.failure_reason = None
        # Also update paper-specific overrides to match the request explicitly
        if request.template_id:
            paper.template_id = request.template_id
        if request.model_name:
            paper.model_name = request.model_name
            
    task.status = "running" # Ensure task is running so processor picks it up
    db.commit()
    return {"ok": True, "count": len(papers)}

@router.get("/", response_model=List[schemas.TaskWithStats])
def read_tasks(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    tasks = db.query(models.Task).filter(models.Task.user_id == DEFAULT_USER_ID).order_by(models.Task.created_at.desc()).offset(skip).limit(limit).all()
    
    result = []
    for task in tasks:
        stats = schemas.TaskStatistics(
            total=db.query(models.Paper).filter(models.Paper.task_id == task.id).count(),
            done=db.query(models.Paper).filter(models.Paper.task_id == task.id, models.Paper.status == "done").count(),
            failed=db.query(models.Paper).filter(models.Paper.task_id == task.id, models.Paper.status == "failed").count(),
            skipped=db.query(models.Paper).filter(models.Paper.task_id == task.id, models.Paper.status == "skipped").count(),
            queued=db.query(models.Paper).filter(models.Paper.task_id == task.id, models.Paper.status == "queued").count(),
            processing=db.query(models.Paper).filter(models.Paper.task_id == task.id, models.Paper.status == "processing").count(),
        )
        task_base = schemas.Task.from_orm(task)
        task_with_stats = schemas.TaskWithStats(
            **task_base.dict(),
            statistics=stats
        )
        result.append(task_with_stats)
    
    return result

@router.get("/{task_id}", response_model=schemas.TaskWithStats)
def read_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(models.Task).filter(models.Task.id == task_id, models.Task.user_id == DEFAULT_USER_ID).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    
    stats = schemas.TaskStatistics(
        total=db.query(models.Paper).filter(models.Paper.task_id == task.id).count(),
        done=db.query(models.Paper).filter(models.Paper.task_id == task.id, models.Paper.status == "done").count(),
        failed=db.query(models.Paper).filter(models.Paper.task_id == task.id, models.Paper.status == "failed").count(),
        skipped=db.query(models.Paper).filter(models.Paper.task_id == task.id, models.Paper.status == "skipped").count(),
        queued=db.query(models.Paper).filter(models.Paper.task_id == task.id, models.Paper.status == "queued").count(),
        processing=db.query(models.Paper).filter(models.Paper.task_id == task.id, models.Paper.status == "processing").count(),
    )
    
    # Create TaskWithStats manually to avoid validation error on missing statistics in ORM object
    task_base = schemas.Task.from_orm(task)
    task_with_stats = schemas.TaskWithStats(
        **task_base.dict(),
        statistics=stats
    )
    return task_with_stats

@router.put("/{task_id}", response_model=schemas.Task)
def update_task(task_id: str, task_update: schemas.TaskUpdate, db: Session = Depends(get_db)):
    db_task = db.query(models.Task).filter(models.Task.id == task_id, models.Task.user_id == DEFAULT_USER_ID).first()
    if db_task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task_update.status:
        db_task.status = task_update.status
        # If pausing, maybe we should handle logic here, but for now just updating status is enough.
        # The background processor should check task status.
    
    db.commit()
    db.refresh(db_task)
    return db_task

@router.post("/{task_id}/papers", response_model=List[schemas.Paper])
def add_papers(task_id: str, papers: schemas.PaperCreate, db: Session = Depends(get_db)):
    db_task = db.query(models.Task).filter(models.Task.id == task_id, models.Task.user_id == DEFAULT_USER_ID).first()
    if db_task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    
    created_papers = []
    for title in papers.titles:
        title = title.strip()
        if not title:
            continue
            
        # De-duplication check (Task level) based on normalized title
        normalized_title = title.lower()
        # In a real scenario we might want a better normalization
        
        existing = db.query(models.Paper).filter(
            models.Paper.task_id == task_id,
            models.Paper.title == title # Simple check for now
        ).first()
        
        if existing:
            continue
            
        db_paper = models.Paper(
            task_id=task_id,
            title=title,
            status="queued"
        )
        db.add(db_paper)
        created_papers.append(db_paper)
    
    db.commit()
    for p in created_papers:
        db.refresh(p)
    
    return created_papers

@router.get("/{task_id}/papers", response_model=List[schemas.Paper])
def read_task_papers(task_id: str, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    # Verify task exists
    task = db.query(models.Task).filter(models.Task.id == task_id, models.Task.user_id == DEFAULT_USER_ID).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
        
    papers = db.query(models.Paper).filter(models.Paper.task_id == task_id).offset(skip).limit(limit).all()
    return papers

@router.delete("/{task_id}")
def delete_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(models.Task).filter(models.Task.id == task_id, models.Task.user_id == DEFAULT_USER_ID).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Cascade delete is handled by database if configured, or we do it manually?
    # SQLAlchemy relationship cascade might not be set up for delete.
    # Let's check models.py. 
    # models.Task: papers = relationship("Paper", back_populates="task")
    # It doesn't specify cascade="all, delete".
    # So we should manually delete papers to be safe, or rely on FK constraints if ON DELETE CASCADE is set (usually not default in simple alembic/sqlalchemy setups unless specified).
    
    # Delete papers first
    db.query(models.Paper).filter(models.Paper.task_id == task_id).delete()
    db.delete(task)
    db.commit()
    return {"ok": True}

@router.post("/batch-delete")
def delete_tasks_batch(payload: schemas.TaskBatchDelete, db: Session = Depends(get_db)):
    # Filter tasks that belong to user
    tasks = db.query(models.Task).filter(
        models.Task.id.in_(payload.ids),
        models.Task.user_id == DEFAULT_USER_ID
    ).all()
    
    if not tasks:
        return {"deleted": 0}
        
    ids_to_delete = [t.id for t in tasks]
    
    # Delete papers
    db.query(models.Paper).filter(models.Paper.task_id.in_(ids_to_delete)).delete(synchronize_session=False)
    
    # Delete tasks
    db.query(models.Task).filter(models.Task.id.in_(ids_to_delete)).delete(synchronize_session=False)
    
    db.commit()
    return {"deleted": len(ids_to_delete)}
