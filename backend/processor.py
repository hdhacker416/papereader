import json
import asyncio
import logging
from sqlalchemy.orm import Session
from database import SessionLocal, get_data_dir, iter_user_ids, user_context
import models
from services import arxiv_service, openreview_service, pdf_service, llm_service
from services.template_service import parse_template_prompts
import os
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Concurrency limit
MAX_CONCURRENT_PAPERS = 3
executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_PAPERS)


def _should_try_arxiv_fallback(search_result: dict | None, download_result) -> bool:
    if not search_result or search_result.get("source") != "openreview":
        return False
    if download_result.ok:
        return False
    return True


def _format_pdf_download_failure(search_result: dict, download_result) -> str:
    source = search_result.get("source")
    if source == "openreview" and download_result.status_code == 404:
        return (
            "No downloadable PDF was found via arXiv or OpenReview. "
            "OpenReview returned a matching record, but its PDF endpoint returned 404; "
            "the arXiv fallback also did not provide a downloadable PDF. "
            f"OpenReview PDF URL: {download_result.url}; "
            f"Final URL: {download_result.final_url or '-'}"
        )

    return (
        f"Failed to download PDF from {download_result.url}. "
        f"Final URL: {download_result.final_url or '-'}; "
        f"Status: {download_result.status_code or '-'}; "
        f"Error: {download_result.error or 'Unknown error'}"
    )


def _clear_resolved_source(paper: models.Paper) -> None:
    if paper.source == "local":
        return
    paper.source = None
    paper.source_url = None
    paper.pdf_path = None


def _resolve_local_pdf_path(paper: models.Paper) -> str | None:
    if paper.source != "local" or not paper.pdf_path:
        return None

    candidates = []
    if os.path.isabs(paper.pdf_path):
        candidates.append(paper.pdf_path)
    else:
        candidates.append(os.path.join(get_data_dir(), paper.pdf_path))

    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "rb") as file:
                if file.read(4) == b"%PDF":
                    return path
        except OSError:
            continue
    return None


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

async def process_paper(paper_id: str, user_id: str):
    context = user_context(user_id)
    context.__enter__()
    db: Session = SessionLocal()
    paper = None
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

        local_pdf_path = _resolve_local_pdf_path(paper)
        if paper.source == "local":
            if not local_pdf_path:
                paper.status = "failed"
                paper.failure_reason = "Local PDF file is missing or invalid"
                log_error_to_chat(db, paper, paper.failure_reason)
                db.commit()
                return
            save_path = local_pdf_path
        else:
            # 1. Resolve source
            had_existing_source_url = bool(paper.source_url)
            search_result = resolve_existing_source(paper.source_url)
            search_result_from_existing_source = search_result is not None
            if not search_result:
                # Try Arxiv first
                search_result = await asyncio.get_event_loop().run_in_executor(executor, arxiv_service.search_arxiv, paper.title)

            if not search_result:
                # Try OpenReview
                search_result = await asyncio.get_event_loop().run_in_executor(executor, openreview_service.search_openreview, paper.title)

            if not search_result:
                paper.status = "failed"
                paper.failure_reason = "Paper not found via existing source_url, Arxiv, or OpenReview"
                if not had_existing_source_url:
                    _clear_resolved_source(paper)
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
                if not search_result_from_existing_source:
                    _clear_resolved_source(paper)
                log_error_to_chat(db, paper, paper.failure_reason)
                db.commit()
                return

            # Define save path: data/pdfs/{task_id}/{paper_id}.pdf
            # Use relative path for database storage (portability), absolute path for file operations
            rel_path = os.path.join("pdfs", paper.task_id, f"{paper.id}.pdf")
            save_path = os.path.join(get_data_dir(), rel_path)

            download_result = await asyncio.get_event_loop().run_in_executor(
                executor,
                pdf_service.download_pdf_with_details,
                pdf_url,
                save_path,
            )

            if _should_try_arxiv_fallback(search_result, download_result):
                logger.warning(
                    "OpenReview download failed for '%s' (%s). Trying arXiv fallback.",
                    paper.title,
                    paper.id,
                )
                fallback_result = await asyncio.get_event_loop().run_in_executor(
                    executor,
                    arxiv_service.search_arxiv,
                    paper.title,
                )
                if fallback_result and fallback_result.get("pdf_url"):
                    fallback_download_result = await asyncio.get_event_loop().run_in_executor(
                        executor,
                        pdf_service.download_pdf_with_details,
                        fallback_result["pdf_url"],
                        save_path,
                    )
                    if fallback_download_result.ok:
                        search_result = fallback_result
                        download_result = fallback_download_result
                        paper.source = fallback_result["source"]
                        paper.source_url = fallback_result["source_url"]
                        db.commit()

            if not download_result.ok:
                paper.status = "failed"
                paper.failure_reason = _format_pdf_download_failure(search_result, download_result)
                if not search_result_from_existing_source:
                    _clear_resolved_source(paper)
                log_error_to_chat(db, paper, paper.failure_reason)
                db.commit()
                return

            paper.pdf_path = rel_path # Store relative path
            db.commit()

        # 3. Interpret with configured model
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
                llm_service.interpret_paper,
                save_path,
                prompts,
                model_name,
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
            if paper is not None:
                paper.status = "failed"
                paper.failure_reason = f"System error: {str(e)}"
                log_error_to_chat(db, paper, paper.failure_reason)
                db.commit()
        except:
            pass
    finally:
        db.close()
        context.__exit__(None, None, None)

async def processor_loop():
    logger.info("Starting background processor loop")
    while True:
        did_work = False
        try:
            for user_id in iter_user_ids():
                with user_context(user_id):
                    db: Session = SessionLocal()
                    try:
                        papers = db.query(models.Paper).join(models.Task).filter(
                            models.Paper.status == "queued",
                            models.Task.status == "running"
                        ).limit(MAX_CONCURRENT_PAPERS).all()
                        if not papers:
                            continue
                        did_work = True
                        await asyncio.gather(*(process_paper(paper.id, user_id) for paper in papers))
                    finally:
                        db.close()
            if not did_work:
                await asyncio.sleep(2)
                
        except Exception as e:
            logger.error(f"Error in processor loop: {e}")
            await asyncio.sleep(5)
