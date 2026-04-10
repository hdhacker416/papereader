from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from google import genai
from google.genai import types
from sqlalchemy.orm import Session

import models
import schemas
from routers.tasks import DEFAULT_USER_ID
from services.research_service import ensure_default_template


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from research.agent.semi_fixed import SemiFixedResearchRunner
from research.tools.search_tools import SearchTools


TASK_REPORT_PROMPT = (
    "You are writing a deep-research style academic report in Chinese. "
    "The report is for a task that already contains paper-level interpretations. "
    "Base the report only on the provided task papers, interpretations, and metadata. "
    "Do not invent methods, experiments, or conclusions. "
    "Treat papers with full interpretation content as high-confidence evidence. "
    "Write in Markdown with these top-level sections exactly: "
    "1. Executive Summary "
    "2. Directions "
    "3. Paper Analyses "
    "4. Synthesis "
    "5. Limitations."
)
MIN_REPORT_PAPERS = 2


def _get_gemini_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not configured")
    return genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})


def _serialize_report(report: models.DeepResearchReport) -> schemas.DeepResearchReport:
    return schemas.DeepResearchReport.model_validate(report)


def _get_template_id(db: Session, template_id: str | None) -> str:
    if template_id:
        template = db.query(models.Template).filter(
            models.Template.id == template_id,
            models.Template.user_id == DEFAULT_USER_ID,
        ).first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        return template.id
    return ensure_default_template(db).id


def search_conference_papers(payload: schemas.ConferenceSearchRequest) -> schemas.ConferenceSearchResponse:
    tools = SearchTools()
    result = tools.coarse_search(
        query=payload.query,
        conferences=payload.conferences,
        years=payload.years,
        top_k_per_asset=payload.top_k_per_asset,
        top_k_global=payload.top_k_global,
    )
    hits = [
        schemas.ConferenceSearchHit(
            **item["paper"],
            coarse_score=float(item["coarse_score"]),
        )
        for item in result["results"]
    ]
    return schemas.ConferenceSearchResponse(
        query=result["query"],
        asset_count=result["asset_count"],
        elapsed_sec=float(result["elapsed_sec"]),
        results=hits,
    )


def create_task_from_selection(
    db: Session,
    payload: schemas.TaskFromSelectionCreate,
) -> schemas.DeepResearchTaskCreateResponse:
    if not payload.selected_papers:
        raise HTTPException(status_code=400, detail="selected_papers is required")

    template_id = _get_template_id(db, payload.template_id)
    tools = SearchTools()
    paper_refs = [item.model_dump() for item in payload.selected_papers]
    details = tools.get_paper_details(paper_refs)
    selected = details["results"]
    if not selected:
        raise HTTPException(status_code=400, detail="No selected papers were resolved")

    task = models.Task(
        user_id=DEFAULT_USER_ID,
        name=payload.name.strip(),
        description=(payload.description or "Created from conference search selection").strip(),
        template_id=template_id,
        model_name=payload.model_name or "gemini-3-flash-preview",
        status="running",
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    imported_count = 0
    for item in selected:
        db.add(
            models.Paper(
                task_id=task.id,
                title=item["title"],
                source_url=item.get("source_url"),
                status="queued",
            )
        )
        imported_count += 1

    db.commit()
    return schemas.DeepResearchTaskCreateResponse(
        ok=True,
        task_id=task.id,
        task_name=task.name,
        imported_count=imported_count,
    )


def create_task_from_auto_research(
    db: Session,
    payload: schemas.AutoResearchTaskCreate,
) -> schemas.DeepResearchTaskCreateResponse:
    template_id = _get_template_id(db, payload.template_id)
    runner = SemiFixedResearchRunner()
    plan = runner.plan(
        user_query=payload.query,
        conferences=payload.conferences,
        years=payload.years,
    )

    coarse_results: list[dict[str, Any]] = []
    for sub_query in plan.sub_queries:
        coarse = runner.search_tools.coarse_search(
            query=sub_query,
            conferences=plan.target_conferences,
            years=plan.target_years,
            top_k_per_asset=8,
            top_k_global=15,
        )
        coarse_results.append(
            {"sub_query": sub_query, "results": coarse["results"], "elapsed_sec": coarse["elapsed_sec"]}
        )

    merged = runner._merge_candidates(coarse_results)
    reranked = runner.search_tools.rerank_search(
        query=plan.rerank_query,
        candidates=merged,
        top_n=max(payload.max_papers, payload.min_papers),
    )["results"]

    selected = _select_by_threshold(
        reranked_results=reranked,
        threshold=payload.rerank_score_threshold,
        min_papers=payload.min_papers,
        max_papers=payload.max_papers,
    )
    if not selected:
        raise HTTPException(status_code=400, detail="Auto research did not select any papers")

    task = models.Task(
        user_id=DEFAULT_USER_ID,
        name=(payload.name or f"Deep Research: {payload.query[:48]}").strip(),
        description=(payload.description or f"Auto-selected from query: {payload.query}").strip(),
        template_id=template_id,
        model_name=payload.model_name or "gemini-3-flash-preview",
        status="running",
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    imported_count = 0
    for item in selected:
        paper = item["paper"]
        db.add(
            models.Paper(
                task_id=task.id,
                title=paper["title"],
                source_url=paper.get("source_url"),
                status="queued",
            )
        )
        imported_count += 1

    db.commit()
    return schemas.DeepResearchTaskCreateResponse(
        ok=True,
        task_id=task.id,
        task_name=task.name,
        imported_count=imported_count,
    )


def _select_by_threshold(
    reranked_results: list[dict[str, Any]],
    threshold: float,
    min_papers: int,
    max_papers: int,
) -> list[dict[str, Any]]:
    selected = [item for item in reranked_results if float(item["rerank_score"]) >= threshold]
    if len(selected) < min_papers:
        selected = reranked_results[:min_papers]
    return selected[:max_papers]


def generate_task_report(
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

    papers = db.query(models.Paper).filter(models.Paper.task_id == task.id).all()
    interpreted = []
    for paper in papers:
        interpretation = db.query(models.Interpretation).filter(
            models.Interpretation.paper_id == paper.id
        ).first()
        if not interpretation:
            continue
        interpreted.append(
            {
                "paper_id": paper.id,
                "title": paper.title,
                "source": paper.source,
                "source_url": paper.source_url,
                "status": paper.status,
                "interpretation": interpretation.content,
                "template_used": interpretation.template_used,
            }
        )

    if not interpreted:
        raise HTTPException(status_code=400, detail="Task has no interpreted papers yet")
    if len(interpreted) < MIN_REPORT_PAPERS:
        raise HTTPException(
            status_code=400,
            detail=f"Task needs at least {MIN_REPORT_PAPERS} interpreted papers before generating a report",
        )

    client = _get_gemini_client()
    request_payload = {
        "query": payload.query or task.description or task.name,
        "task": {
            "id": task.id,
            "name": task.name,
            "description": task.description,
            "model_name": task.model_name,
        },
        "papers": interpreted,
    }
    response = client.models.generate_content(
        model=task.model_name or "gemini-3-flash-preview",
        contents=json.dumps(request_payload, ensure_ascii=False),
        config=types.GenerateContentConfig(
            system_instruction=TASK_REPORT_PROMPT,
            max_output_tokens=4096,
        ),
    )
    content = response.text or ""
    if not content.strip():
        raise HTTPException(status_code=500, detail="Empty report response from model")

    report = db.query(models.DeepResearchReport).filter(
        models.DeepResearchReport.task_id == task.id
    ).first()
    if report is None:
        report = models.DeepResearchReport(
            task_id=task.id,
            query=payload.query,
            source_type=payload.source_type or "task",
            source_meta=payload.source_meta,
            status="completed",
            content=content,
        )
        db.add(report)
    else:
        report.query = payload.query
        report.source_type = payload.source_type or report.source_type
        report.source_meta = payload.source_meta
        report.status = "completed"
        report.content = content
    db.commit()
    db.refresh(report)
    return _serialize_report(report)


def get_task_report(db: Session, task_id: str) -> schemas.DeepResearchReport:
    report = db.query(models.DeepResearchReport).join(models.Task).filter(
        models.DeepResearchReport.task_id == task_id,
        models.Task.user_id == DEFAULT_USER_ID,
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Task report not found")
    return _serialize_report(report)
