from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import List, Optional
import models, schemas
from database import get_db
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/collections",
    tags=["collections"],
    responses={404: {"description": "Not found"}},
)

DEFAULT_USER_ID = "default_user_id"

class CollectionCreate(schemas.BaseModel):
    name: str
    parent_id: Optional[str] = None

class Collection(schemas.BaseModel):
    id: str
    name: str
    parent_id: Optional[str] = None
    
    class Config:
        from_attributes = True

@router.get("/", response_model=List[Collection])
def read_collections(db: Session = Depends(get_db)):
    collections = db.query(models.Collection).filter(models.Collection.user_id == DEFAULT_USER_ID).all()
    return collections

@router.post("/", response_model=Collection)
def create_collection(collection: CollectionCreate, db: Session = Depends(get_db)):
    if collection.parent_id:
        parent = db.query(models.Collection).filter(models.Collection.id == collection.parent_id, models.Collection.user_id == DEFAULT_USER_ID).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent collection not found")
            
    db_collection = models.Collection(
        name=collection.name,
        parent_id=collection.parent_id,
        user_id=DEFAULT_USER_ID
    )
    db.add(db_collection)
    db.commit()
    db.refresh(db_collection)
    return db_collection

@router.delete("/{collection_id}")
def delete_collection(collection_id: str, db: Session = Depends(get_db)):
    collection = db.query(models.Collection).filter(models.Collection.id == collection_id, models.Collection.user_id == DEFAULT_USER_ID).first()
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    # Recursive delete function
    def delete_recursive(col_id):
        # 1. Delete sub-collections
        children = db.query(models.Collection).filter(models.Collection.parent_id == col_id).all()
        for child in children:
            delete_recursive(child.id)
            
        # 2. Delete paper associations
        db.query(models.PaperCollection).filter(models.PaperCollection.collection_id == col_id).delete()
        
        # 3. Delete the collection itself
        db.query(models.Collection).filter(models.Collection.id == col_id).delete()

    delete_recursive(collection_id)
    db.commit()
    return {"ok": True}

@router.get("/{collection_id}/papers", response_model=List[schemas.Paper])
def get_collection_papers(collection_id: str, db: Session = Depends(get_db)):
    # Join PaperCollection and Paper
    papers = db.query(models.Paper).join(models.PaperCollection).filter(models.PaperCollection.collection_id == collection_id).all()
    return papers


@router.post("/{collection_id}/papers/{paper_id}")
def add_paper_to_collection(collection_id: str, paper_id: str, db: Session = Depends(get_db)):
    collection = db.query(models.Collection).filter(models.Collection.id == collection_id, models.Collection.user_id == DEFAULT_USER_ID).first()
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
        
    paper = db.query(models.Paper).filter(models.Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
        
    # Check if exists
    exists = db.query(models.PaperCollection).filter(models.PaperCollection.collection_id == collection_id, models.PaperCollection.paper_id == paper_id).first()
    if exists:
        return {"ok": True}
        
    pc = models.PaperCollection(collection_id=collection_id, paper_id=paper_id)
    db.add(pc)
    db.commit()
    return {"ok": True}

@router.post("/{collection_id}/reread")
def reread_collection(collection_id: str, request: schemas.ReReadRequest, db: Session = Depends(get_db)):
    collection = db.query(models.Collection).filter(models.Collection.id == collection_id).first()
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Get all papers in collection recursively
    def get_all_paper_ids(col_id):
        p_ids = set()
        # Papers in this collection
        pcs = db.query(models.PaperCollection).filter(models.PaperCollection.collection_id == col_id).all()
        for pc in pcs:
            p_ids.add(pc.paper_id)
        
        # Sub-collections
        children = db.query(models.Collection).filter(models.Collection.parent_id == col_id).all()
        for child in children:
            p_ids.update(get_all_paper_ids(child.id))
        return p_ids

    paper_ids = get_all_paper_ids(collection_id)
    
    if not paper_ids:
        return {"ok": True, "count": 0}

    papers_query = db.query(models.Paper).filter(models.Paper.id.in_(paper_ids))
    if request.only_failed:
        papers_query = papers_query.filter(models.Paper.status == "failed")
    papers = papers_query.all()
    
    for paper in papers:
        # Reset status
        paper.status = "queued"
        paper.failure_reason = None
        
        # Apply overrides
        if request.template_id:
            paper.template_id = request.template_id
        if request.model_name:
            paper.model_name = request.model_name
            
        # Ensure parent task is running
        task = db.query(models.Task).filter(models.Task.id == paper.task_id).first()
        if task and task.status != "running":
            task.status = "running"
            
    db.commit()
    return {"ok": True, "count": len(papers)}

@router.delete("/{collection_id}/papers/{paper_id}")
def remove_paper_from_collection(collection_id: str, paper_id: str, db: Session = Depends(get_db)):
    pc = db.query(models.PaperCollection).filter(models.PaperCollection.collection_id == collection_id, models.PaperCollection.paper_id == paper_id).first()
    if not pc:
        raise HTTPException(status_code=404, detail="Paper not in collection")
        
    db.delete(pc)
    db.commit()
    return {"ok": True}

@router.get("/paper/{paper_id}", response_model=List[Collection])
def get_paper_collections(paper_id: str, db: Session = Depends(get_db)):
    # Join
    collections = db.query(models.Collection).join(models.PaperCollection).filter(models.PaperCollection.paper_id == paper_id).all()
    return collections
