from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import schemas
from database import get_data_dir


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from community.figure_extractor import extract_figures  # noqa: E402
from community.persona_answer_experiment import (  # noqa: E402
    ROUTE_4,
    _download_pdf,
    _run_route_4,
    _safe_filename,
    _search_top_papers,
)


def _clamp_int(value: int, *, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _figure_refs(manifest: dict | None, limit: int = 8) -> list[schemas.CommunityFigureRef]:
    if not manifest:
        return []
    refs: list[schemas.CommunityFigureRef] = []
    for item in (manifest.get("figures") or [])[:limit]:
        refs.append(
            schemas.CommunityFigureRef(
                id=str(item.get("id") or ""),
                page_number=int(item.get("page_number") or 0),
                label=str(item.get("label") or ""),
                caption=str(item.get("caption") or ""),
                confidence=float(item.get("confidence") or 0.0),
                warnings=[str(warning) for warning in (item.get("warnings") or [])],
            )
        )
    return refs


def generate_persona_answers(payload: schemas.CommunityAnswerRequest) -> schemas.CommunityAnswerResponse:
    started = time.time()
    query = payload.query.strip()
    if not query:
        raise ValueError("query cannot be empty")

    limit = _clamp_int(payload.limit, minimum=1, maximum=8)
    max_text_chars = _clamp_int(payload.max_text_chars, minimum=20_000, maximum=250_000)
    figure_max_pages = _clamp_int(payload.figure_max_pages, minimum=1, maximum=20)
    output_root = Path(get_data_dir()) / "community" / time.strftime("%Y%m%d_%H%M%S")
    figures_root = output_root / "figures"
    figures_root.mkdir(parents=True, exist_ok=True)

    results: list[schemas.CommunityPaperAnswer] = []
    papers = _search_top_papers(query, limit=limit)
    for item in papers:
        paper = item.paper
        base = {
            "rank": item.rank,
            "paper_id": str(paper.get("paper_id") or ""),
            "conference": str(paper.get("conference") or ""),
            "year": int(paper.get("year") or 0),
            "title": str(paper.get("title") or ""),
            "abstract": str(paper.get("abstract") or ""),
            "authors": [str(author) for author in (paper.get("authors") or [])],
            "source_url": str(paper.get("source_url") or ""),
            "rerank_score": item.rerank_score,
        }

        pdf_path, _, download_error = _download_pdf(paper)
        if download_error or not pdf_path:
            results.append(
                schemas.CommunityPaperAnswer(
                    **base,
                    local_pdf_path=pdf_path,
                    status="error",
                    error=download_error or "PDF download failed.",
                )
            )
            continue

        figure_manifest: dict | None = None
        try:
            figure_dir = figures_root / f"{item.rank:02d}_{_safe_filename(str(paper.get('paper_id') or paper.get('title')))}"
            extract_figures(
                pdf_path=Path(pdf_path),
                output_dir=figure_dir,
                dpi=110,
                max_pages=figure_max_pages,
            )
            manifest_path = figure_dir / "figures.json"
            if manifest_path.exists():
                figure_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            figure_manifest = {
                "figure_count": 0,
                "figures": [],
                "error": str(exc),
            }

        try:
            route_output = _run_route_4(
                query,
                paper,
                pdf_path,
                figure_manifest,
                max_text_chars,
            )
        except Exception as exc:
            route_output = {
                "status": "error",
                "error": str(exc),
            }
        results.append(
            schemas.CommunityPaperAnswer(
                **base,
                local_pdf_path=pdf_path,
                figure_count=int((figure_manifest or {}).get("figure_count") or 0),
                figures=_figure_refs(figure_manifest),
                answer=route_output.get("answer"),
                seconds=route_output.get("seconds"),
                status=str(route_output.get("status") or "ok"),
                error=route_output.get("error") or (figure_manifest or {}).get("error"),
            )
        )

    return schemas.CommunityAnswerResponse(
        query=query,
        route=ROUTE_4,
        elapsed_sec=round(time.time() - started, 2),
        results=results,
    )
