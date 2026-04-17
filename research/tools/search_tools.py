from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from research.config import DEFAULT_CONFIG
from research.pipeline.search_pipeline import SearchAsset, SearchPipeline, load_search_assets
from research.providers.dashscope_embedding import DashScopeEmbeddingClient
from research.providers.dashscope_rerank import DashScopeRerankClient
from research.retrieval.embedding_index import IndexedPaper, load_normalized_jsonl


SUMMARY_PATH_CANDIDATES = [
    DEFAULT_CONFIG.build.build_root_dir / "build_summary_ai_top_2024_2026.json",
    DEFAULT_CONFIG.build.build_root_dir / "build_summary_2025_2026.json",
]


def _resolve_default_summary_path() -> Path:
    for path in SUMMARY_PATH_CANDIDATES:
        if path.exists():
            return path
    return SUMMARY_PATH_CANDIDATES[0]


DEFAULT_SUMMARY_PATH = _resolve_default_summary_path()

CONFERENCE_ALIASES = {
    "neurips": "nips",
    "neurips": "nips",
    "neurips conference": "nips",
    "nips": "nips",
    "iclr": "iclr",
    "icml": "icml",
    "acl": "acl",
    "aaai": "aaai",
    "colm": "colm",
    "colt": "colt",
    "cvpr": "cvpr",
    "iccv": "iccv",
    "eccv": "eccv",
}


@dataclass(frozen=True)
class ToolPaperRecord:
    paper_id: str
    conference: str
    year: int
    title: str
    abstract: str
    authors: list[str]
    source_url: str


def _paper_to_tool_record(paper: IndexedPaper) -> ToolPaperRecord:
    return ToolPaperRecord(
        paper_id=paper.paper_id,
        conference=paper.conference,
        year=paper.year,
        title=paper.title,
        abstract=paper.abstract,
        authors=list(paper.authors),
        source_url=paper.source_url,
    )


def _select_assets(
    all_assets: Iterable[SearchAsset],
    conferences: Iterable[str] | None = None,
    years: Iterable[int] | None = None,
) -> list[SearchAsset]:
    conference_set = {_normalize_conference_name(item) for item in conferences} if conferences else None
    year_set = set(years) if years else None

    selected: list[SearchAsset] = []
    for asset in all_assets:
        if conference_set is not None and asset.conference.lower() not in conference_set:
            continue
        if year_set is not None and asset.year not in year_set:
            continue
        selected.append(asset)
    return selected


def _normalize_conference_name(name: str) -> str:
    value = name.strip().lower()
    return CONFERENCE_ALIASES.get(value, value)


class SearchTools:
    def __init__(
        self,
        summary_path: Path = DEFAULT_SUMMARY_PATH,
    ) -> None:
        self.summary_path = summary_path
        self.assets = load_search_assets(summary_path)
        self.pipeline = SearchPipeline(
            embedding_client=DashScopeEmbeddingClient(batch_size=10),
            rerank_client=DashScopeRerankClient(),
        )

    def coarse_search(
        self,
        query: str,
        conferences: Iterable[str] | None = None,
        years: Iterable[int] | None = None,
        top_k_per_asset: int = 10,
        top_k_global: int = 50,
    ) -> dict:
        assets = _select_assets(self.assets, conferences=conferences, years=years)
        hits, elapsed = self.pipeline.coarse_search_assets(
            query=query,
            assets=assets,
            top_k_per_asset=top_k_per_asset,
            top_k_global=top_k_global,
        )
        return {
            "query": query,
            "asset_count": len(assets),
            "elapsed_sec": elapsed,
            "results": [
                {
                    "paper": asdict(_paper_to_tool_record(hit.paper)),
                    "coarse_score": hit.score,
                }
                for hit in hits
            ],
        }

    def rerank_search(
        self,
        query: str,
        candidates: list[dict],
        top_n: int = 20,
    ) -> dict:
        # Rebuild RetrievalHit-like objects by mapping candidate papers back to assets.
        # We intentionally use the existing coarse results as the source of truth.
        paper_lookup = self._build_paper_lookup()
        coarse_hits = []
        for item in candidates:
            paper = item["paper"]
            key = (paper["conference"], int(paper["year"]), paper["paper_id"])
            indexed_paper = paper_lookup.get(key)
            if indexed_paper is None:
                continue
            from research.retrieval.embedding_index import RetrievalHit

            coarse_hits.append(
                RetrievalHit(
                    paper=indexed_paper,
                    score=float(item.get("coarse_score", 0.0)),
                )
            )

        start_results = self.pipeline.rerank_service.rerank_hits(
            query=query,
            hits=coarse_hits,
            top_n=top_n,
        )
        return {
            "query": query,
            "candidate_count": len(coarse_hits),
            "results": [
                {
                    "paper": asdict(_paper_to_tool_record(item.hit.paper)),
                    "coarse_score": item.hit.score,
                    "rerank_score": item.rerank_score,
                }
                for item in start_results
            ],
        }

    def get_paper_details(
        self,
        paper_refs: list[dict],
    ) -> dict:
        paper_lookup = self._build_paper_lookup()
        results = []
        for ref in paper_refs:
            key = (ref["conference"], int(ref["year"]), ref["paper_id"])
            paper = paper_lookup.get(key)
            if paper is None:
                continue
            results.append(asdict(_paper_to_tool_record(paper)))
        return {"results": results}

    def _build_paper_lookup(self) -> dict[tuple[str, int, str], IndexedPaper]:
        lookup: dict[tuple[str, int, str], IndexedPaper] = {}
        for asset in self.assets:
            for paper in load_normalized_jsonl(asset.normalized_path):
                key = (paper.conference, paper.year, paper.paper_id)
                lookup[key] = paper
        return lookup
