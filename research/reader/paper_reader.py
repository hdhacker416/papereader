from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from backend.services.arxiv_service import search_arxiv
from backend.services.gemini_service import interpret_paper
from backend.services.openreview_service import search_openreview
from backend.services.pdf_service import download_pdf
from research.config import DEFAULT_CONFIG


OPENREVIEW_FIRST_CONFERENCES = {"iclr", "nips", "neurips", "icml", "colm"}
DEFAULT_READING_PROMPTS = (
    "Read this paper carefully. Summarize the problem, main idea, and technical method. "
    "Be concrete and avoid generic praise.",
    "Summarize the experimental evidence, strongest results, and the main limitations or caveats.",
    "For this research question: {user_query}\n"
    "Explain why this paper is relevant or not relevant. "
    "Classify it into one primary type: attack, defense, evaluation, alignment, mechanism, or other. "
    "Then give 3 concrete takeaways.",
)


@dataclass(frozen=True)
class ResolvedPaperSource:
    source: str
    pdf_url: str
    source_url: str
    title: str
    abstract: str
    authors: list[str]


@dataclass(frozen=True)
class PaperReadingResult:
    paper: dict[str, Any]
    resolve_status: str
    download_status: str
    read_status: str
    local_pdf_path: str | None
    resolved_source: ResolvedPaperSource | None
    reading_text: str | None
    reading_turns: list[dict[str, Any]]
    error: str | None


def _slugify_filename(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", value).strip("._")
    return cleaned or "paper"


class PaperReader:
    def __init__(
        self,
        pdf_cache_dir: Path | None = None,
        reading_cache_dir: Path | None = None,
        model_name: str = "gemini-3-flash-preview",
    ) -> None:
        self.pdf_cache_dir = pdf_cache_dir or DEFAULT_CONFIG.runtime.pdf_cache_dir
        self.reading_cache_dir = reading_cache_dir or DEFAULT_CONFIG.runtime.reading_cache_dir
        self.model_name = model_name

    def read_papers(
        self,
        papers: list[dict[str, Any]],
        user_query: str,
    ) -> list[PaperReadingResult]:
        results: list[PaperReadingResult] = []
        for paper in papers:
            results.append(self.read_paper(paper=paper, user_query=user_query))
        return results

    def read_paper(
        self,
        paper: dict[str, Any],
        user_query: str,
    ) -> PaperReadingResult:
        resolved = self.resolve_source(paper)
        if resolved is None:
            return PaperReadingResult(
                paper=paper,
                resolve_status="not_found",
                download_status="skipped",
                read_status="skipped",
                local_pdf_path=None,
                resolved_source=None,
                reading_text=None,
                reading_turns=[],
                error="No paper source found on OpenReview or arXiv.",
            )

        pdf_path = self._pdf_path_for_paper(paper)
        ok = download_pdf(resolved.pdf_url, str(pdf_path))
        if not ok:
            return PaperReadingResult(
                paper=paper,
                resolve_status="resolved",
                download_status="failed",
                read_status="skipped",
                local_pdf_path=str(pdf_path),
                resolved_source=resolved,
                reading_text=None,
                reading_turns=[],
                error=f"Failed to download PDF from {resolved.pdf_url}",
            )

        reading_cache_path = self._reading_cache_path_for_paper(paper)
        if reading_cache_path.exists():
            cached = json.loads(reading_cache_path.read_text(encoding="utf-8"))
            return PaperReadingResult(
                paper=paper,
                resolve_status="resolved",
                download_status="downloaded",
                read_status="cached",
                local_pdf_path=str(pdf_path),
                resolved_source=resolved,
                reading_text=cached.get("reading_text"),
                reading_turns=cached.get("reading_turns", []),
                error=None,
            )

        prompts = [item.format(user_query=user_query) for item in DEFAULT_READING_PROMPTS]
        try:
            reading_text, reading_turns = interpret_paper(
                pdf_path=str(pdf_path),
                template_prompts=prompts,
                model_name=self.model_name,
            )
        except Exception as exc:
            return PaperReadingResult(
                paper=paper,
                resolve_status="resolved",
                download_status="downloaded",
                read_status="failed",
                local_pdf_path=str(pdf_path),
                resolved_source=resolved,
                reading_text=None,
                reading_turns=[],
                error=str(exc),
            )

        reading_cache_path.parent.mkdir(parents=True, exist_ok=True)
        reading_cache_path.write_text(
            json.dumps(
                {
                    "paper": paper,
                    "resolved_source": asdict(resolved),
                    "reading_text": reading_text,
                    "reading_turns": reading_turns,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return PaperReadingResult(
            paper=paper,
            resolve_status="resolved",
            download_status="downloaded",
            read_status="completed",
            local_pdf_path=str(pdf_path),
            resolved_source=resolved,
            reading_text=reading_text,
            reading_turns=reading_turns,
            error=None,
        )

    def resolve_source(self, paper: dict[str, Any]) -> ResolvedPaperSource | None:
        title = str(paper.get("title", "")).strip()
        conference = str(paper.get("conference", "")).strip().lower()
        source_url = str(paper.get("source_url", "")).strip()

        search_order = self._source_search_order(conference=conference, source_url=source_url)
        for source_name in search_order:
            if source_name == "openreview":
                found = search_openreview(title)
            else:
                found = search_arxiv(title)
            if not found or not found.get("pdf_url"):
                continue
            return ResolvedPaperSource(
                source=found.get("source", source_name),
                pdf_url=found["pdf_url"],
                source_url=found.get("source_url", ""),
                title=found.get("title", title),
                abstract=found.get("abstract", paper.get("abstract", "")),
                authors=list(found.get("authors") or paper.get("authors") or []),
            )
        return None

    def _source_search_order(self, conference: str, source_url: str) -> tuple[str, ...]:
        lowered = source_url.lower()
        if "openreview.net" in lowered:
            return ("openreview", "arxiv")
        if "arxiv.org" in lowered:
            return ("arxiv", "openreview")
        if conference in OPENREVIEW_FIRST_CONFERENCES:
            return ("openreview", "arxiv")
        return ("arxiv", "openreview")

    def _pdf_path_for_paper(self, paper: dict[str, Any]) -> Path:
        conference = str(paper.get("conference", "unknown")).lower()
        year = int(paper.get("year", 0))
        paper_id = _slugify_filename(str(paper.get("paper_id", paper.get("title", "paper"))))
        return self.pdf_cache_dir / conference / str(year) / f"{paper_id}.pdf"

    def _reading_cache_path_for_paper(self, paper: dict[str, Any]) -> Path:
        conference = str(paper.get("conference", "unknown")).lower()
        year = int(paper.get("year", 0))
        paper_id = _slugify_filename(str(paper.get("paper_id", paper.get("title", "paper"))))
        return self.reading_cache_dir / conference / str(year) / f"{paper_id}.json"
