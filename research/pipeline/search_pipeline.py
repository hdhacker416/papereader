from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from research.providers.dashscope_embedding import DashScopeEmbeddingClient
from research.providers.dashscope_rerank import DashScopeRerankClient
from research.rerank.service import RerankService, RerankedHit
from research.retrieval.embedding_index import EmbeddingIndex, RetrievalHit


@dataclass(frozen=True)
class SearchAsset:
    conference: str
    year: int
    paper_count: int
    normalized_path: Path
    embedding_path: Path


@dataclass(frozen=True)
class SearchRunResult:
    coarse_hits: list[RetrievalHit]
    reranked_hits: list[RerankedHit]
    coarse_elapsed_sec: float
    rerank_elapsed_sec: float


def load_search_assets(summary_path: Path) -> list[SearchAsset]:
    summary_path = summary_path.resolve()
    with summary_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    assets: list[SearchAsset] = []
    for item in payload.get("results", []):
        normalized_path = Path(item["normalized_path"])
        embedding_path = Path(item["embedding_path"])
        if not normalized_path.is_absolute():
            normalized_path = (summary_path.parent / normalized_path).resolve()
        if not embedding_path.is_absolute():
            embedding_path = (summary_path.parent / embedding_path).resolve()
        assets.append(
            SearchAsset(
                conference=item["conference"],
                year=int(item["year"]),
                paper_count=int(item["paper_count"]),
                normalized_path=normalized_path,
                embedding_path=embedding_path,
            )
        )
    return assets


class SearchPipeline:
    def __init__(
        self,
        embedding_client: DashScopeEmbeddingClient,
        rerank_client: DashScopeRerankClient,
    ) -> None:
        self.embedding_index = EmbeddingIndex(embedding_client)
        self.rerank_service = RerankService(rerank_client)

    def coarse_search_assets(
        self,
        query: str,
        assets: Iterable[SearchAsset],
        top_k_per_asset: int = 20,
        top_k_global: int = 50,
    ) -> tuple[list[RetrievalHit], float]:
        start = time.perf_counter()
        query_vector = self.embedding_index.embed_query(query)
        all_hits: list[RetrievalHit] = []
        for asset in assets:
            all_hits.extend(
                self.embedding_index.search_with_query_vector(
                    query_vector=query_vector,
                    normalized_jsonl_path=asset.normalized_path,
                    embedding_cache_path=asset.embedding_path,
                    top_k=top_k_per_asset,
                )
            )
        all_hits.sort(key=lambda item: item.score, reverse=True)
        elapsed = time.perf_counter() - start
        return all_hits[:top_k_global], elapsed

    def run(
        self,
        query: str,
        assets: Iterable[SearchAsset],
        top_k_per_asset: int = 20,
        top_k_global: int = 50,
        rerank_top_n: int = 20,
    ) -> SearchRunResult:
        coarse_hits, coarse_elapsed = self.coarse_search_assets(
            query=query,
            assets=assets,
            top_k_per_asset=top_k_per_asset,
            top_k_global=top_k_global,
        )
        start = time.perf_counter()
        reranked_hits = self.rerank_service.rerank_hits(
            query=query,
            hits=coarse_hits,
            top_n=rerank_top_n,
        )
        rerank_elapsed = time.perf_counter() - start
        return SearchRunResult(
            coarse_hits=coarse_hits,
            reranked_hits=reranked_hits,
            coarse_elapsed_sec=coarse_elapsed,
            rerank_elapsed_sec=rerank_elapsed,
        )
