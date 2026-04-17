from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

import models
import schemas
from database import SessionLocal

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from research.build.normalize_paperlists import normalize_conference_file
from research.build.packager import Packager
from research.build.paperlists_repo import (
    ConferenceFile,
    ensure_paperlists_repo,
    filter_conference_files,
    list_conference_files,
)
from research.providers.dashscope_embedding import DashScopeEmbeddingClient
from research.retrieval.embedding_index import EmbeddingIndex
from research.targeting import conference_display_name


logger = logging.getLogger(__name__)

PACK_BUILD_POLL_SECONDS = 2


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_target_states(job: models.PackBuildJob) -> list[dict[str, Any]]:
    try:
        payload = json.loads(job.target_states_json or "[]")
    except Exception:
        payload = []
    return payload if isinstance(payload, list) else []


def _save_target_states(job: models.PackBuildJob, states: list[dict[str, Any]]) -> None:
    job.target_states_json = json.dumps(states, ensure_ascii=False)
    job.completed_targets = sum(1 for item in states if item.get("status") == "completed")
    job.failed_targets = sum(1 for item in states if item.get("status") == "failed")


def _serialize_job(job: models.PackBuildJob) -> schemas.PackBuildJob:
    target_states = [
        schemas.PackBuildTargetState(
            conference=str(item.get("conference", "")),
            year=int(item.get("year", 0)),
            label=f"{conference_display_name(str(item.get('conference', '')).lower())} {item.get('year', '')}".strip(),
            status=str(item.get("status", "queued")),
            current_stage=item.get("current_stage"),
            error=item.get("error"),
            pack_name=item.get("pack_name"),
        )
        for item in _load_target_states(job)
    ]
    completed_fraction = float(job.completed_targets)
    if job.total_targets > 0 and job.current_stage == "embedding" and job.current_step_total > 0:
        completed_fraction += float(job.current_step_completed) / float(job.current_step_total)
    progress_percent = 0.0
    if job.total_targets > 0:
        progress_percent = min(100.0, max(0.0, completed_fraction / float(job.total_targets) * 100.0))
    return schemas.PackBuildJob(
        id=job.id,
        status=job.status,
        version=job.version,
        requested_conferences=json.loads(job.requested_conferences_json or "[]"),
        requested_years=json.loads(job.requested_years_json or "[]"),
        total_targets=job.total_targets,
        completed_targets=job.completed_targets,
        failed_targets=job.failed_targets,
        current_conference=job.current_conference,
        current_year=job.current_year,
        current_stage=job.current_stage,
        current_step_completed=job.current_step_completed,
        current_step_total=job.current_step_total,
        progress_percent=progress_percent,
        progress_message=job.progress_message,
        target_states=target_states,
        error=job.error,
        can_resume=job.status == "failed",
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def _resolve_requested_files(
    conferences: list[str] | None,
    years: list[int] | None,
) -> list[ConferenceFile]:
    ensure_paperlists_repo()
    available_files = list_conference_files()
    selected = filter_conference_files(
        available_files,
        conferences=conferences,
        years=years,
    )
    selected.sort(key=lambda item: (item.conference, item.year))
    return selected


def create_pack_build_job(
    db: Session,
    payload: schemas.ResearchPackBuildRequest,
) -> schemas.PackBuildJob:
    selected = _resolve_requested_files(payload.conferences, payload.years)
    if not selected:
        raise HTTPException(status_code=400, detail="No available conference/year source files for the selected pack targets")

    target_states = [
        {
            "conference": item.conference,
            "year": int(item.year),
            "status": "queued",
            "current_stage": "queued",
            "error": None,
            "pack_name": None,
        }
        for item in selected
    ]
    job = models.PackBuildJob(
        status="queued",
        version=payload.version or "v1",
        requested_conferences_json=json.dumps(payload.conferences or [], ensure_ascii=False),
        requested_years_json=json.dumps(payload.years or [], ensure_ascii=False),
        total_targets=len(target_states),
        completed_targets=0,
        failed_targets=0,
        current_stage="queued",
        progress_message="Queued for background build.",
        target_states_json=json.dumps(target_states, ensure_ascii=False),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return _serialize_job(job)


def list_pack_build_jobs(db: Session) -> list[schemas.PackBuildJob]:
    jobs = db.query(models.PackBuildJob).order_by(models.PackBuildJob.created_at.desc()).limit(20).all()
    return [_serialize_job(job) for job in jobs]


def resume_pack_build_job(db: Session, job_id: str) -> schemas.PackBuildJob:
    job = db.query(models.PackBuildJob).filter(models.PackBuildJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Pack build job not found")
    if job.status == "completed":
        raise HTTPException(status_code=400, detail="Completed pack build jobs do not need resume")
    if job.status == "running":
        return _serialize_job(job)

    states = _load_target_states(job)
    for item in states:
        if item.get("status") in {"failed", "processing"}:
            item["status"] = "queued"
            item["current_stage"] = "queued"
            item["error"] = None
    _save_target_states(job, states)
    job.status = "queued"
    job.current_conference = None
    job.current_year = None
    job.current_stage = "queued"
    job.current_step_completed = 0
    job.current_step_total = 0
    job.progress_message = "Resumed and waiting to continue."
    job.error = None
    job.finished_at = None
    db.commit()
    db.refresh(job)
    return _serialize_job(job)


def recover_stale_pack_build_jobs() -> None:
    db = SessionLocal()
    try:
        jobs = db.query(models.PackBuildJob).filter(models.PackBuildJob.status == "running").all()
        for job in jobs:
            states = _load_target_states(job)
            for item in states:
                if item.get("status") == "processing":
                    item["status"] = "queued"
                    item["current_stage"] = "queued"
            _save_target_states(job, states)
            job.status = "queued"
            job.current_conference = None
            job.current_year = None
            job.current_stage = "queued"
            job.current_step_completed = 0
            job.current_step_total = 0
            job.progress_message = "Recovered after backend restart."
            job.error = None
        db.commit()
    finally:
        db.close()


def _update_job(
    db: Session,
    job: models.PackBuildJob,
    states: list[dict[str, Any]],
    *,
    status: str | None = None,
    current_conference: str | None = None,
    current_year: int | None = None,
    current_stage: str | None = None,
    current_step_completed: int | None = None,
    current_step_total: int | None = None,
    progress_message: str | None = None,
    error: str | None = None,
) -> None:
    _save_target_states(job, states)
    if status is not None:
        job.status = status
    job.current_conference = current_conference
    job.current_year = current_year
    job.current_stage = current_stage
    job.current_step_completed = current_step_completed or 0
    job.current_step_total = current_step_total or 0
    job.progress_message = progress_message
    job.error = error
    db.commit()


def _process_single_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.query(models.PackBuildJob).filter(models.PackBuildJob.id == job_id).first()
        if not job or job.status not in {"queued", "running"}:
            return

        states = _load_target_states(job)
        job.status = "running"
        if job.started_at is None:
            job.started_at = _utcnow()
        db.commit()

        file_lookup = {
            (item.conference, int(item.year)): item
            for item in list_conference_files()
        }
        embedding_client = DashScopeEmbeddingClient()
        embedding_index = EmbeddingIndex(embedding_client)
        packager = Packager()

        for state in states:
            if state.get("status") == "completed":
                continue

            conference = str(state["conference"]).lower()
            year = int(state["year"])
            conference_file = file_lookup.get((conference, year))
            if conference_file is None:
                state["status"] = "failed"
                state["current_stage"] = "failed"
                state["error"] = "Source conference file not found"
                _update_job(
                    db,
                    job,
                    states,
                    status="failed",
                    current_conference=conference,
                    current_year=year,
                    current_stage="failed",
                    progress_message=f"Failed: source file missing for {conference} {year}.",
                    error=state["error"],
                )
                job.finished_at = _utcnow()
                db.commit()
                return

            state["status"] = "processing"
            state["current_stage"] = "normalizing"
            state["error"] = None
            _update_job(
                db,
                job,
                states,
                status="running",
                current_conference=conference,
                current_year=year,
                current_stage="normalizing",
                progress_message=f"Normalizing {conference_display_name(conference)} {year}.",
            )

            normalized = normalize_conference_file(conference_file)

            last_progress = {"done": -1}

            def progress_callback(done: int, total: int) -> None:
                if done != total and done == last_progress["done"]:
                    return
                if done != total and total > 0 and done - last_progress["done"] < max(1, total // 20):
                    return
                last_progress["done"] = done
                _update_job(
                    db,
                    job,
                    states,
                    status="running",
                    current_conference=conference,
                    current_year=year,
                    current_stage="embedding",
                    current_step_completed=done,
                    current_step_total=total,
                    progress_message=f"Embedding {conference_display_name(conference)} {year}: {done}/{total}.",
                )

            state["current_stage"] = "embedding"
            _update_job(
                db,
                job,
                states,
                status="running",
                current_conference=conference,
                current_year=year,
                current_stage="embedding",
                current_step_completed=0,
                current_step_total=max(1, normalized.paper_count),
                progress_message=f"Embedding {conference_display_name(conference)} {year}.",
            )
            embedding_path = embedding_index.build_and_cache_embeddings(
                conference=conference,
                year=year,
                normalized_jsonl_path=Path(normalized.output_path),
                force=False,
                progress_callback=progress_callback,
            )

            state["current_stage"] = "packing"
            _update_job(
                db,
                job,
                states,
                status="running",
                current_conference=conference,
                current_year=year,
                current_stage="packing",
                current_step_completed=0,
                current_step_total=0,
                progress_message=f"Packing {conference_display_name(conference)} {year}.",
            )
            built = packager.build_pack_from_files(
                conference=conference,
                year=year,
                normalized_path=Path(normalized.output_path),
                embedding_path=Path(embedding_path),
                version=job.version,
            )

            state["status"] = "completed"
            state["current_stage"] = "completed"
            state["pack_name"] = built.pack_name
            _update_job(
                db,
                job,
                states,
                status="running",
                current_conference=conference,
                current_year=year,
                current_stage="completed",
                progress_message=f"Completed {conference_display_name(conference)} {year}.",
            )

        job.finished_at = _utcnow()
        _update_job(
            db,
            job,
            states,
            status="completed",
            current_conference=None,
            current_year=None,
            current_stage="completed",
            progress_message="Pack build completed.",
            error=None,
        )
        db.refresh(job)
        job.finished_at = _utcnow()
        db.commit()
    except Exception as exc:
        logger.exception("Pack build job failed: %s", exc)
        try:
            job = db.query(models.PackBuildJob).filter(models.PackBuildJob.id == job_id).first()
            if job:
                states = _load_target_states(job)
                for item in states:
                    if item.get("status") == "processing":
                        item["status"] = "failed"
                        item["current_stage"] = "failed"
                        item["error"] = str(exc)
                        break
                job.finished_at = _utcnow()
                _update_job(
                    db,
                    job,
                    states,
                    status="failed",
                    current_conference=job.current_conference,
                    current_year=job.current_year,
                    current_stage="failed",
                    progress_message=f"Build failed: {exc}",
                    error=str(exc),
                )
                db.refresh(job)
                job.finished_at = _utcnow()
                db.commit()
        except Exception:
            logger.exception("Failed to persist pack build job failure state")
    finally:
        db.close()


async def pack_build_loop() -> None:
    logger.info("Starting pack build loop")
    while True:
        db = SessionLocal()
        try:
            queued = (
                db.query(models.PackBuildJob)
                .filter(models.PackBuildJob.status == "queued")
                .order_by(models.PackBuildJob.created_at.asc())
                .first()
            )
            if queued is None:
                await asyncio.sleep(PACK_BUILD_POLL_SECONDS)
                continue
            await asyncio.to_thread(_process_single_job, queued.id)
        except Exception:
            logger.exception("Error in pack build loop")
            await asyncio.sleep(PACK_BUILD_POLL_SECONDS)
        finally:
            db.close()
