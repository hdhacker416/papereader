from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from backend.services.arxiv_service import search_arxiv
try:
    from backend.services.llm_service import interpret_paper
except ModuleNotFoundError:
    from services.llm_service import interpret_paper
from backend.services.openreview_service import search_openreview
from backend.services.pdf_service import download_pdf_with_details
from research.config import DEFAULT_CONFIG


OPENREVIEW_FIRST_CONFERENCES = {"iclr", "nips", "neurips", "icml", "colm"}
DEFAULT_READING_PROMPTS = (
    "请你使用中文总结一下这篇文章的内容，并且举一个例子加以说明。",
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
        template_prompts: list[str] | None = None,
    ) -> list[PaperReadingResult]:
        results: list[PaperReadingResult] = []
        for paper in papers:
            results.append(
                self.read_paper(
                    paper=paper,
                    user_query=user_query,
                    template_prompts=template_prompts,
                )
            )
        return results

    def read_paper(
        self,
        paper: dict[str, Any],
        user_query: str,
        template_prompts: list[str] | None = None,
    ) -> PaperReadingResult:
        prompts = self._render_prompts(user_query=user_query, template_prompts=template_prompts)
        prompt_cache_key = self._prompt_cache_key(prompts)
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
        resolved_source = resolved
        download_result = download_pdf_with_details(resolved.pdf_url, str(pdf_path))
        if not download_result.ok and resolved.source == "openreview":
            fallback = search_arxiv(str(paper.get("title", "")).strip())
            if fallback and fallback.get("pdf_url"):
                fallback_resolved = ResolvedPaperSource(
                    source=fallback.get("source", "arxiv"),
                    pdf_url=fallback["pdf_url"],
                    source_url=fallback.get("source_url", ""),
                    title=fallback.get("title", str(paper.get("title", "")).strip()),
                    abstract=fallback.get("abstract", str(paper.get("abstract", "")).strip()),
                    authors=list(fallback.get("authors") or paper.get("authors") or []),
                )
                fallback_download_result = download_pdf_with_details(
                    fallback_resolved.pdf_url,
                    str(pdf_path),
                )
                if fallback_download_result.ok:
                    resolved_source = fallback_resolved
                    download_result = fallback_download_result

        if not download_result.ok:
            return PaperReadingResult(
                paper=paper,
                resolve_status="resolved",
                download_status="failed",
                read_status="skipped",
                local_pdf_path=str(pdf_path),
                resolved_source=resolved_source,
                reading_text=None,
                reading_turns=[],
                error=(
                    f"Failed to download PDF from {download_result.url}. "
                    f"Final URL: {download_result.final_url or '-'}; "
                    f"Status: {download_result.status_code or '-'}; "
                    f"Error: {download_result.error or 'Unknown error'}"
                ),
            )

        reading_cache_path = self._reading_cache_path_for_paper(
            paper=paper,
            prompt_cache_key=prompt_cache_key,
        )
        if reading_cache_path.exists():
            cached = json.loads(reading_cache_path.read_text(encoding="utf-8"))
            return PaperReadingResult(
                paper=paper,
                resolve_status="resolved",
                download_status="downloaded",
                read_status="cached",
                local_pdf_path=str(pdf_path),
                resolved_source=resolved_source,
                reading_text=cached.get("reading_text"),
                reading_turns=cached.get("reading_turns", []),
                error=None,
            )

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
                    "resolved_source": asdict(resolved_source),
                    "prompt_cache_key": prompt_cache_key,
                    "prompts": prompts,
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
            resolved_source=resolved_source,
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

    def _reading_cache_path_for_paper(
        self,
        paper: dict[str, Any],
        prompt_cache_key: str,
    ) -> Path:
        conference = str(paper.get("conference", "unknown")).lower()
        year = int(paper.get("year", 0))
        paper_id = _slugify_filename(str(paper.get("paper_id", paper.get("title", "paper"))))
        return self.reading_cache_dir / conference / str(year) / prompt_cache_key / f"{paper_id}.json"

    @staticmethod
    def _render_prompts(
        user_query: str,
        template_prompts: list[str] | None = None,
    ) -> list[str]:
        prompts = template_prompts or list(DEFAULT_READING_PROMPTS)
        return [item.format(user_query=user_query) for item in prompts]

    @staticmethod
    def _prompt_cache_key(prompts: list[str]) -> str:
        digest = hashlib.sha1(
            json.dumps(prompts, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        return f"prompt_{digest[:12]}"
