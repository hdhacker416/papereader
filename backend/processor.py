import json
import asyncio
import logging
from sqlalchemy.orm import Session
from database import SessionLocal, DATA_DIR
import models
from services import arxiv_service, openreview_service, pdf_service, gemini_service
from services.template_service import parse_template_prompts
import os
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Concurrency limit
MAX_CONCURRENT_PAPERS = 3
executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_PAPERS)


def resolve_existing_source(source_url: str | None):
    if not source_url:
        return None
    url = source_url.strip()
    if not url:
        return None

    lower_url = url.lower()
    if "openreview.net" in lower_url:
        if "/pdf?" in lower_url:
            pdf_url = url
            forum_url = url.replace("/pdf?", "/forum?")
        elif "/forum?" in lower_url:
            pdf_url = url.replace("/forum?", "/pdf?")
            forum_url = url
        else:
            pdf_url = url
            forum_url = url
        return {
            "title": None,
            "authors": [],
            "abstract": "",
            "pdf_url": pdf_url,
            "source": "openreview",
            "source_url": forum_url,
            "published": None,
        }

    if "arxiv.org" in lower_url:
        if "/pdf/" in lower_url:
            pdf_url = url
            abs_url = url.replace("/pdf/", "/abs/")
            if abs_url.endswith(".pdf"):
                abs_url = abs_url[:-4]
        elif "/abs/" in lower_url:
            abs_url = url
            pdf_url = url.replace("/abs/", "/pdf/")
            if not pdf_url.endswith(".pdf"):
                pdf_url = f"{pdf_url}.pdf"
        else:
            pdf_url = url
            abs_url = url
        return {
            "title": None,
            "authors": [],
            "abstract": "",
            "pdf_url": pdf_url,
            "source": "arxiv",
            "source_url": abs_url,
            "published": None,
        }

    return None

def log_error_to_chat(db: Session, paper: models.Paper, error_msg: str):
    """Helper to log error message to chat history so it's visible in UI."""
    try:
        msg = models.ChatMessage(
            paper_id=paper.id,
            role="assistant",
            content=f"**Error Processing Paper:** {error_msg}"
        )
        db.add(msg)
    except Exception as e:
        logger.error(f"Failed to log error to chat: {e}")

async def process_paper(paper_id: str):
    db: Session = SessionLocal()
    try:
        paper = db.query(models.Paper).filter(models.Paper.id == paper_id).first()
        if not paper:
            return

        # Double check status
        if paper.status != "queued":
            return

        # Update status to processing
        paper.status = "processing"
        db.commit()
        
        # Clear existing data for re-read
        # We need to manually delete related records if cascade delete is not configured in DB schema
        try:
            db.query(models.ChatMessage).filter(models.ChatMessage.paper_id == paper_id).delete()
            db.query(models.Interpretation).filter(models.Interpretation.paper_id == paper_id).delete()
            db.query(models.Note).filter(models.Note.paper_id == paper_id).delete()
            db.commit()
        except Exception as e:
            logger.error(f"Error clearing existing data for paper {paper_id}: {e}")
            
        logger.info(f"Processing paper: {paper.title} ({paper.id})")

        # 1. Resolve source
        search_result = resolve_existing_source(paper.source_url)
        if not search_result:
            # Try Arxiv first
            search_result = await asyncio.get_event_loop().run_in_executor(executor, arxiv_service.search_arxiv, paper.title)
        
        if not search_result:
            # Try OpenReview
            search_result = await asyncio.get_event_loop().run_in_executor(executor, openreview_service.search_openreview, paper.title)
        
        if not search_result:
            paper.status = "failed"
            paper.failure_reason = "Paper not found via existing source_url, Arxiv, or OpenReview"
            log_error_to_chat(db, paper, paper.failure_reason)
            db.commit()
            return

        # Update metadata
        paper.source = search_result["source"]
        paper.source_url = search_result["source_url"]
        # paper.title = search_result["title"] # Update title to official one? Maybe optional.
        db.commit()

        # 2. Download PDF
        pdf_url = search_result["pdf_url"]
        if not pdf_url:
            paper.status = "failed"
            paper.failure_reason = "PDF URL not found"
            log_error_to_chat(db, paper, paper.failure_reason)
            db.commit()
            return
            
        # Define save path: data/pdfs/{task_id}/{paper_id}.pdf
        # Use relative path for database storage (portability), absolute path for file operations
        rel_path = os.path.join("pdfs", paper.task_id, f"{paper.id}.pdf")
        save_path = os.path.join(DATA_DIR, rel_path)
        
        success = await asyncio.get_event_loop().run_in_executor(executor, pdf_service.download_pdf, pdf_url, save_path)
        
        if not success:
            paper.status = "failed"
            paper.failure_reason = "Failed to download PDF"
            log_error_to_chat(db, paper, paper.failure_reason)
            db.commit()
            return
            
        paper.pdf_path = rel_path # Store relative path
        db.commit()

        # 3. Interpret with Gemini
        # Get template
        task = db.query(models.Task).filter(models.Task.id == paper.task_id).first()

        try:
            prompts = parse_template_prompts(task.custom_reading_prompts_json or "")
            template_used = task.custom_reading_prompts_json

            if not prompts:
                template_id = paper.template_id if paper.template_id else task.template_id
                template = db.query(models.Template).filter(models.Template.id == template_id).first()
                if not template:
                    paper.status = "failed"
                    paper.failure_reason = "Template not found"
                    log_error_to_chat(db, paper, paper.failure_reason)
                    db.commit()
                    return
                prompts = parse_template_prompts(template.content)
                template_used = template.content

            # Pass model_name (check for override, then task default, then fallback)
            task_model = task.model_name if task.model_name else "gemini-3-flash-preview"
            model_name = paper.model_name if paper.model_name else task_model
            
            interpretation_text, chat_history = await asyncio.get_event_loop().run_in_executor(
                executor, 
                gemini_service.interpret_paper, 
                save_path, 
                prompts,
                model_name
            )
            
            # Save interpretation
            interp = models.Interpretation(
                paper_id=paper.id,
                content=interpretation_text,
                template_used=template_used or json.dumps(prompts, ensure_ascii=False)
            )
            db.add(interp)
            
            # Save Chat History
            # We must save the interpretation process as chat messages now that the Interpretation UI is removed.
            for turn in chat_history:
                # turn structure: {'user': {'role': 'user', 'parts': [{'text': '...'}]}, 'model': {'role': 'model', 'parts': [{'text': '...'}]}, 'meta': {...}}
                
                # 1. User Message (Prompt)
                user_part = turn.get('user', {}).get('parts', [{}])[0]
                user_text = user_part.get('text', '') if isinstance(user_part, dict) else str(user_part)
                
                if user_text:
                    user_msg = models.ChatMessage(
                        paper_id=paper.id,
                        role='user',
                        content=user_text
                    )
                    db.add(user_msg)
                
                # 2. Assistant Message (Response)
                model_part = turn.get('model', {}).get('parts', [{}])[0]
                model_text = model_part.get('text', '') if isinstance(model_part, dict) else str(model_part)
                
                meta = turn.get('meta', {})
                
                if model_text:
                    assistant_msg = models.ChatMessage(
                        paper_id=paper.id,
                        role='assistant',
                        content=model_text,
                        cost=meta.get('cost', 0.0),
                        time_cost=meta.get('time_cost', 0.0)
                    )
                    db.add(assistant_msg)
            
            paper.status = "done"
            db.commit()
            
        except Exception as e:
            logger.error(f"Error interpreting paper {paper.id}: {e}")
            paper.status = "failed"
            paper.failure_reason = str(e)
            log_error_to_chat(db, paper, paper.failure_reason)
            db.commit()
            
    except Exception as e:
        logger.error(f"Error processing paper {paper_id}: {e}")
        # Try to update status if possible
        try:
            paper.status = "failed"
            paper.failure_reason = f"System error: {str(e)}"
            log_error_to_chat(db, paper, paper.failure_reason)
            db.commit()
        except:
            pass
    finally:
        db.close()

async def processor_loop():
    logger.info("Starting background processor loop")
    while True:
        db: Session = SessionLocal()
        try:
            # Find papers that are queued and belong to tasks that are running
            papers = db.query(models.Paper).join(models.Task).filter(
                models.Paper.status == "queued",
                models.Task.status == "running"
            ).limit(MAX_CONCURRENT_PAPERS).all()
            
            if not papers:
                await asyncio.sleep(2)
                continue
                
            tasks = []
            for paper in papers:
                tasks.append(process_paper(paper.id))
            
            if tasks:
                await asyncio.gather(*tasks)
                
        except Exception as e:
            logger.error(f"Error in processor loop: {e}")
            await asyncio.sleep(5)
        finally:
            db.close()
