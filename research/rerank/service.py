from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from research.providers.dashscope_rerank import DashScopeRerankClient
from research.retrieval.embedding_index import RetrievalHit


@dataclass(frozen=True)
class RerankedHit:
    hit: RetrievalHit
    rerank_score: float


def build_rerank_document(hit: RetrievalHit) -> str:
    return f"Title: {hit.paper.title}\nAbstract: {hit.paper.abstract}"


class RerankService:
    def __init__(self, client: DashScopeRerankClient) -> None:
        self.client = client

    def rerank_hits(
        self,
        query: str,
        hits: Iterable[RetrievalHit],
        top_n: int = 20,
    ) -> list[RerankedHit]:
        hit_list = list(hits)
        if not hit_list:
            return []

        documents = [build_rerank_document(hit) for hit in hit_list]
        reranked = self.client.rerank(
            query=query,
            documents=documents,
            top_n=min(top_n, len(documents)),
            return_documents=False,
        )

        results: list[RerankedHit] = []
        for item in reranked:
            if item.index < 0 or item.index >= len(hit_list):
                continue
            results.append(
                RerankedHit(
                    hit=hit_list[item.index],
                    rerank_score=item.relevance_score,
                )
            )
        return results
