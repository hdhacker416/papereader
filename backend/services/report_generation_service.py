from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app_constants import DEFAULT_USER_ID
from database import SessionLocal
import models
import schemas
from services import deep_research_service


logger = logging.getLogger(__name__)

REPORT_POLL_SECONDS = 2
UNSUPPORTED_REPORT_MODELS = {"qwen-long", "qwen-doc-turbo"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_report(report: models.DeepResearchReport) -> schemas.DeepResearchReport:
    return schemas.DeepResearchReport.model_validate(report)


def _resolve_report_query(task: models.Task, payload: schemas.TaskReportGenerateRequest) -> str:
    trace = deep_research_service._parse_json_dict(task.agent_trace_json)
    return payload.query or trace.get("用户问题") or task.description or task.name


def enqueue_task_report_generation(
    db: Session,
    task_id: str,
    payload: schemas.TaskReportGenerateRequest,
) -> schemas.DeepResearchReport:
    task = db.query(models.Task).filter(
        models.Task.id == task_id,
        models.Task.user_id == DEFAULT_USER_ID,
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    interpreted = deep_research_service._load_interpreted_task_papers(db, task)
    if not interpreted:
        raise HTTPException(status_code=400, detail="Task has no interpreted papers yet")
    if len(interpreted) < deep_research_service.MIN_REPORT_PAPERS:
        raise HTTPException(
            status_code=400,
            detail=f"Task needs at least {deep_research_service.MIN_REPORT_PAPERS} interpreted papers before generating a report",
        )

    report_query = _resolve_report_query(task, payload)
    report_model = payload.model_name or task.model_name or "gemini-3-flash-preview"
    if str(report_model).strip().lower() in UNSUPPORTED_REPORT_MODELS:
        raise HTTPException(
            status_code=400,
            detail="Selected model is only supported for direct PDF reading, not report generation. Use Gemini or Qwen Flash/Plus/Max.",
        )

    report = db.query(models.DeepResearchReport).filter(
        models.DeepResearchReport.task_id == task.id
    ).first()
    if report is None:
        report = models.DeepResearchReport(
            task_id=task.id,
            query=report_query,
            source_type=payload.source_type or "task",
            source_meta=payload.source_meta,
            model_name=report_model,
            status="queued",
            progress_stage="queued",
            progress_message="已加入报告生成队列",
            progress_completed=0,
            progress_total=0,
            error=None,
            content="",
        )
        db.add(report)
    else:
        if report.status == "running":
            return _serialize_report(report)
        report.query = report_query
        report.source_type = payload.source_type or report.source_type or "task"
        report.source_meta = payload.source_meta
        report.model_name = report_model
        report.status = "queued"
        report.progress_stage = "queued"
        report.progress_message = "已加入报告生成队列"
        report.progress_completed = 0
        report.progress_total = 0
        report.error = None
    db.commit()
    db.refresh(report)
    return _serialize_report(report)


def recover_stale_report_jobs() -> None:
    db = SessionLocal()
    try:
        reports = db.query(models.DeepResearchReport).filter(
            models.DeepResearchReport.status == "running"
        ).all()
        for report in reports:
            report.status = "queued"
            report.progress_stage = "queued"
            report.progress_message = "后端重启后已恢复到队列中"
            report.error = None
        db.commit()
    finally:
        db.close()


def _update_report_progress(
    db: Session,
    report: models.DeepResearchReport,
    *,
    status: str | None = None,
    progress_stage: str | None = None,
    progress_message: str | None = None,
    progress_completed: int | None = None,
    progress_total: int | None = None,
    error: str | None = None,
    content: str | None = None,
) -> None:
    if status is not None:
        report.status = status
    if progress_stage is not None:
        report.progress_stage = progress_stage
    if progress_message is not None:
        report.progress_message = progress_message
    if progress_completed is not None:
        report.progress_completed = progress_completed
    if progress_total is not None:
        report.progress_total = progress_total
    if error is not None:
        report.error = error
    if content is not None:
        report.content = content
    db.commit()


def _process_single_report(report_id: str) -> None:
    db = SessionLocal()
    try:
        report = db.query(models.DeepResearchReport).filter(
            models.DeepResearchReport.id == report_id
        ).first()
        if not report or report.status not in {"queued", "running"}:
            return

        task = db.query(models.Task).filter(
            models.Task.id == report.task_id,
            models.Task.user_id == DEFAULT_USER_ID,
        ).first()
        if not task:
            report.status = "failed"
            report.progress_stage = "failed"
            report.progress_message = "关联任务不存在"
            report.error = "Task not found"
            db.commit()
            return

        interpreted = deep_research_service._load_interpreted_task_papers(db, task)
        if not interpreted:
            report.status = "failed"
            report.progress_stage = "failed"
            report.progress_message = "任务里还没有可用于生成报告的精读结果"
            report.error = "No interpreted papers"
            db.commit()
            return

        trace = deep_research_service._parse_json_dict(task.agent_trace_json)
        report_query = report.query or task.description or task.name
        report_model = report.model_name or task.model_name or "gemini-3-flash-preview"

        report.status = "running"
        report.progress_stage = "preparing"
        report.progress_message = "正在整理任务输入"
        report.progress_completed = 0
        report.progress_total = 1
        report.error = None
        db.commit()

        def progress_callback(stage: str, completed: int, total: int, message: str) -> None:
            _update_report_progress(
                db,
                report,
                status="running",
                progress_stage=stage,
                progress_message=message,
                progress_completed=completed,
                progress_total=total,
            )

        content, generated_source_meta = deep_research_service._generate_task_report_content(
            task=task,
            report_query=report_query,
            report_model=report_model,
            interpreted=interpreted,
            trace=trace,
            progress_callback=progress_callback,
        )
        if not content.strip():
            raise RuntimeError("Empty report response from model")

        _update_report_progress(
            db,
            report,
            status="completed",
            progress_stage="completed",
            progress_message="报告生成完成",
            progress_completed=max(report.progress_completed, report.progress_total, 1),
            progress_total=max(report.progress_total, 1),
            error=None,
            content=content,
        )
        report.source_meta = generated_source_meta
        db.commit()
    except Exception as exc:
        logger.exception("Failed to generate report %s", report_id)
        try:
            report = db.query(models.DeepResearchReport).filter(
                models.DeepResearchReport.id == report_id
            ).first()
            if report is not None:
                _update_report_progress(
                    db,
                    report,
                    status="failed",
                    progress_stage="failed",
                    progress_message="报告生成失败",
                    error=str(exc),
                )
        except Exception:
            db.rollback()
    finally:
        db.close()


async def report_generation_loop() -> None:
    logger.info("Starting report generation loop")
    while True:
        db = SessionLocal()
        try:
            report = db.query(models.DeepResearchReport).filter(
                models.DeepResearchReport.status == "queued"
            ).order_by(models.DeepResearchReport.updated_at.asc()).first()
            report_id = report.id if report else None
        except Exception as exc:
            logger.error("Failed to query queued report jobs: %s", exc)
            report_id = None
        finally:
            db.close()

        if report_id:
            await asyncio.to_thread(_process_single_report, report_id)
        else:
            await asyncio.sleep(REPORT_POLL_SECONDS)
