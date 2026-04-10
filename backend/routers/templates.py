import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import models, schemas
from database import get_db

router = APIRouter(
    prefix="/api/templates",
    tags=["templates"],
    responses={404: {"description": "Not found"}},
)

# Dummy user ID for now
DEFAULT_USER_ID = "default_user_id"

@router.get("/", response_model=List[schemas.Template])
def read_templates(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    templates = db.query(models.Template).filter(models.Template.user_id == DEFAULT_USER_ID).offset(skip).limit(limit).all()
    # Convert content from JSON string to list
    results = []
    for t in templates:
        try:
            content_list = json.loads(t.content)
        except json.JSONDecodeError:
            content_list = [t.content] # Fallback for legacy data
        
        # Create a copy or dict to modify
        t_dict = t.__dict__.copy()
        t_dict['content'] = content_list
        results.append(t_dict)
    return results

@router.post("/", response_model=schemas.Template)
def create_template(template: schemas.TemplateCreate, db: Session = Depends(get_db)):
    # Check if this is the first template, if so make it default
    count = db.query(models.Template).filter(models.Template.user_id == DEFAULT_USER_ID).count()
    is_default = template.is_default or (count == 0)
    
    if is_default:
        # Set all others to false
        db.query(models.Template).filter(models.Template.user_id == DEFAULT_USER_ID).update({"is_default": False})
    
    # Serialize content to JSON string
    content_str = json.dumps(template.content)
    
    db_template = models.Template(
        name=template.name,
        content=content_str,
        is_default=is_default,
        user_id=DEFAULT_USER_ID
    )
    db.add(db_template)
    db.commit()
    db.refresh(db_template)
    
    # Convert back for response
    db_template.content = template.content
    return db_template

@router.get("/{template_id}", response_model=schemas.Template)
def read_template(template_id: str, db: Session = Depends(get_db)):
    db_template = db.query(models.Template).filter(models.Template.id == template_id, models.Template.user_id == DEFAULT_USER_ID).first()
    if db_template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    
    try:
        content_list = json.loads(db_template.content)
    except json.JSONDecodeError:
        content_list = [db_template.content]
        
    db_template.content = content_list
    return db_template

@router.put("/{template_id}/default", response_model=schemas.Template)
def set_default_template(template_id: str, db: Session = Depends(get_db)):
    db_template = db.query(models.Template).filter(models.Template.id == template_id, models.Template.user_id == DEFAULT_USER_ID).first()
    if db_template is None:
        raise HTTPException(status_code=404, detail="Template not found")
        
    # Set all others to false
    db.query(models.Template).filter(models.Template.user_id == DEFAULT_USER_ID).update({"is_default": False})
    
    # Set this one to true
    db_template.is_default = True
    db.commit()
    db.refresh(db_template)
    
    try:
        content_list = json.loads(db_template.content)
    except json.JSONDecodeError:
        content_list = [db_template.content]
    db_template.content = content_list
    
    return db_template

@router.delete("/{template_id}")
def delete_template(template_id: str, db: Session = Depends(get_db)):
    db_template = db.query(models.Template).filter(models.Template.id == template_id, models.Template.user_id == DEFAULT_USER_ID).first()
    if db_template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    db.delete(db_template)
    db.commit()
    return {"ok": True}
