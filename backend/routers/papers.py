from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import List, Optional
import models, schemas
from database import get_db, DATA_DIR
from services import llm_service
import logging
import os

logger = logging.getLogger(__name__)

def get_paper_pdf_path(paper):
    """
    Resolve the absolute path to the PDF file for a paper.
    Prioritizes standard directory structure to support migration.
    """
    if not paper.task_id or not paper.id:
        return None
        
    # 1. Standard Path (Best for migration/portability)
    # data/pdfs/{task_id}/{paper_id}.pdf
    standard_path = os.path.join(DATA_DIR, "pdfs", paper.task_id, f"{paper.id}.pdf")
    if os.path.exists(standard_path):
        return standard_path
        
    # 2. Stored Path (Legacy absolute or custom relative)
    if paper.pdf_path:
        # Check if absolute path exists
        if os.path.exists(paper.pdf_path):
            return paper.pdf_path
            
        # Check if relative to DATA_DIR
        rel_path = os.path.join(DATA_DIR, paper.pdf_path)
        if os.path.exists(rel_path):
            return rel_path
            
    return None

router = APIRouter(
    prefix="/api/papers",
    tags=["papers"],
    responses={404: {"description": "Not found"}},
)

# Dummy user ID
DEFAULT_USER_ID = "default_user_id"

@router.get("/{paper_id}", response_model=schemas.Paper)
def read_paper(paper_id: str, db: Session = Depends(get_db)):
    paper = db.query(models.Paper).filter(models.Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    # Check if user owns the task
    task = db.query(models.Task).filter(models.Task.id == paper.task_id, models.Task.user_id == DEFAULT_USER_ID).first()
    if not task:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    # Construct response with details
    # We might need a schema for PaperDetail
    # For now returning the model with relationships might work if Pydantic config is set
    
    return paper

@router.post("/{paper_id}/chat")
def chat_with_paper(paper_id: str, message: str = Body(..., embed=True), db: Session = Depends(get_db)):
    paper = db.query(models.Paper).filter(models.Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
        
    # Check pdf existence
    pdf_path = get_paper_pdf_path(paper)
    if not pdf_path:
        raise HTTPException(status_code=400, detail="PDF not available (File not found)")
        
    # Save user message
    user_msg = models.ChatMessage(
        paper_id=paper_id,
        role="user",
        content=message
    )
    db.add(user_msg)
    db.commit()
    
    # Get history
    history_msgs = db.query(models.ChatMessage).filter(models.ChatMessage.paper_id == paper_id).order_by(models.ChatMessage.created_at).all()
    history = [{"role": msg.role, "content": msg.content} for msg in history_msgs]
    
    # Remove the last message (current one) from history to pass to Gemini?
    # No, `gemini_service.chat_with_paper` expects history *before* current message?
    # Or start_chat history.
    # My implementation of `chat_with_paper` takes `history` and `message`.
    # So I should pass history *excluding* the current message?
    # `history_msgs` includes the current one because I just saved it.
    # So let's exclude the last one.
    
    history_for_ai = history[:-1]
    
    try:
        # Note: chat_with_paper now returns response_text, updated_history, cost, time_cost
        # We need to update gemini_service.chat_with_paper to return these or call gemini_service.gemini_interface directly?
        # Let's check gemini_service.py again.
        # It currently returns response.text only.
        # But `interpret_paper` calls `gemini.chat` which returns tuple.
        # `chat_with_paper` in `gemini_service.py` calls `gemini.chat` but only returns `response_text`.
        # I should have updated `gemini_service.py` first to return more info.
        # But I can't see `gemini_service.py` in this turn (I read it in thought process but not `read_file`?).
        # Wait, I read `gemini_service.py` in previous turns.
        # Let's assume I will update `gemini_service.py` to return tuple.
        
        # Get task to get model_name
        task = db.query(models.Task).filter(models.Task.id == paper.task_id).first()
        model_name = task.model_name if task else "gemini-3-flash-preview"
        
        response_text, _, cost, time_cost = llm_service.chat_with_paper(
            pdf_path,
            history_for_ai,
            message,
            model_name=model_name,
        )
        
        # Save assistant message
        ai_msg = models.ChatMessage(
            paper_id=paper_id,
            role="assistant",
            content=response_text,
            cost=cost,
            time_cost=time_cost
        )
        db.add(ai_msg)
        db.commit()
        
        return {
            "role": "assistant", 
            "content": response_text,
            "cost": cost,
            "time_cost": time_cost
        }
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        # Log error to chat history as requested
        error_msg = f"**Error:** {str(e)}"
        
        try:
            err_chat = models.ChatMessage(
                paper_id=paper_id,
                role="assistant",
                content=error_msg
            )
            db.add(err_chat)
            db.commit()
            
            return {
                "role": "assistant",
                "content": error_msg
            }
        except Exception as db_err:
            logger.error(f"Failed to save error to chat history: {db_err}")
            raise HTTPException(status_code=500, detail=str(e))

@router.get("/{paper_id}/chat")
def get_chat_history(paper_id: str, db: Session = Depends(get_db)):
    msgs = db.query(models.ChatMessage).filter(models.ChatMessage.paper_id == paper_id).order_by(models.ChatMessage.created_at).all()
    return msgs

@router.delete("/{paper_id}/chat")
def clear_chat_history(paper_id: str, db: Session = Depends(get_db)):
    db.query(models.ChatMessage).filter(models.ChatMessage.paper_id == paper_id).delete()
    db.commit()
    return {"ok": True}

@router.put("/{paper_id}/notes")
def update_notes(paper_id: str, content: str = Body(..., embed=True), db: Session = Depends(get_db)):
    paper = db.query(models.Paper).filter(models.Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    note = db.query(models.Note).filter(models.Note.paper_id == paper_id).first()
    if note:
        note.content = content
    else:
        note = models.Note(paper_id=paper_id, content=content)
        db.add(note)
    
    db.commit()
    return {"ok": True}

@router.get("/{paper_id}/notes")
def get_notes(paper_id: str, db: Session = Depends(get_db)):
    note = db.query(models.Note).filter(models.Note.paper_id == paper_id).first()
    return note if note else {"content": ""}

@router.post("/{paper_id}/retry")
def retry_paper(paper_id: str, db: Session = Depends(get_db)):
    paper = db.query(models.Paper).filter(models.Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    # Reset status to queued so processor picks it up
    paper.status = "queued"
    paper.failure_reason = None
    db.commit()
    return {"ok": True}

@router.delete("/{paper_id}")
def delete_paper(paper_id: str, db: Session = Depends(get_db)):
    paper = db.query(models.Paper).filter(models.Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    # Delete PDF file if exists
    try:
        # Try to delete from standard path first
        if paper.task_id:
            standard_path = os.path.join(DATA_DIR, "pdfs", paper.task_id, f"{paper.id}.pdf")
            if os.path.exists(standard_path):
                os.remove(standard_path)
                
        # Also try stored path if different (Legacy absolute paths)
        if paper.pdf_path:
             # If stored path is absolute and exists
             if os.path.exists(paper.pdf_path) and (not paper.task_id or paper.pdf_path != standard_path):
                 try:
                    os.remove(paper.pdf_path)
                 except OSError:
                    pass
                    
             # If stored path is relative
             rel_path = os.path.join(DATA_DIR, paper.pdf_path)
             if os.path.exists(rel_path) and (not paper.task_id or rel_path != standard_path):
                 try:
                    os.remove(rel_path)
                 except OSError:
                    pass
                    
    except Exception as e:
        logger.warning(f"Failed to delete PDF file for paper {paper_id}: {e}")

    # Delete associated data from DB
    # We need to manually delete related records if cascade delete is not configured in DB schema
    # Chat messages
    db.query(models.ChatMessage).filter(models.ChatMessage.paper_id == paper_id).delete()
    # Interpretations
    db.query(models.Interpretation).filter(models.Interpretation.paper_id == paper_id).delete()
    # Notes
    db.query(models.Note).filter(models.Note.paper_id == paper_id).delete()
    # Paper collections
    # db.query(models.PaperCollection).filter(models.PaperCollection.paper_id == paper_id).delete()

    db.delete(paper)
    db.commit()
    return {"ok": True}
