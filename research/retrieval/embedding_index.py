from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

from research.config import BuildConfig, DEFAULT_CONFIG
from research.providers.dashscope_embedding import DashScopeEmbeddingClient


@dataclass(frozen=True)
class IndexedPaper:
    paper_id: str
    conference: str
    year: int
    title: str
    abstract: str
    authors: list[str]
    source_url: str
    raw_status: str
    normalized_status: str


@dataclass(frozen=True)
class RetrievalHit:
    paper: IndexedPaper
    score: float


def build_embedding_text(record: IndexedPaper) -> str:
    return f"Title: {record.title}\nAbstract: {record.abstract}"


def load_normalized_jsonl(path: Path) -> list[IndexedPaper]:
    papers: list[IndexedPaper] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            papers.append(
                IndexedPaper(
                    paper_id=item["paper_id"],
                    conference=item["conference"],
                    year=int(item["year"]),
                    title=item["title"],
                    abstract=item["abstract"],
                    authors=list(item.get("authors", [])),
                    source_url=item.get("source_url", ""),
                    raw_status=item.get("raw_status", ""),
                    normalized_status=item.get("normalized_status", ""),
                )
            )
    return papers


class EmbeddingIndex:
    def __init__(
        self,
        embedding_client: DashScopeEmbeddingClient,
        config: BuildConfig | None = None,
    ) -> None:
        self.embedding_client = embedding_client
        self.config = config or DEFAULT_CONFIG.build

    def _cache_path(self, conference: str, year: int) -> Path:
        return self.config.embeddings_dir / conference / f"{conference}{year}.embeddings.json"

    def _normalize_matrix(self, matrix: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return matrix / norms

    def embed_query(self, query: str) -> np.ndarray:
        query_vector = np.array(
            self.embedding_client.embed_text(query).embedding,
            dtype=np.float32,
        )
        query_norm = np.linalg.norm(query_vector)
        if query_norm == 0:
            query_norm = 1.0
        return query_vector / query_norm

    def build_and_cache_embeddings(
        self,
        conference: str,
        year: int,
        normalized_jsonl_path: Path,
        force: bool = False,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Path:
        cache_path = self._cache_path(conference, year)
        if cache_path.exists() and not force:
            return cache_path

        papers = load_normalized_jsonl(normalized_jsonl_path)
        texts = [build_embedding_text(paper) for paper in papers]
        results = self.embedding_client.embed_many_with_progress(
            texts,
            progress_callback=progress_callback,
        )

        payload = {
            "conference": conference,
            "year": year,
            "paper_count": len(papers),
            "model": self.embedding_client.model,
            "dimensions": self.embedding_client.dimensions,
            "items": [
                {
                    "paper_id": paper.paper_id,
                    "embedding": result.embedding,
                }
                for paper, result in zip(papers, results, strict=True)
            ],
        }

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f)
        return cache_path

    def search(
        self,
        query: str,
        normalized_jsonl_path: Path,
        embedding_cache_path: Path,
        top_k: int = 50,
    ) -> list[RetrievalHit]:
        query_vector = self.embed_query(query)
        return self.search_with_query_vector(
            query_vector=query_vector,
            normalized_jsonl_path=normalized_jsonl_path,
            embedding_cache_path=embedding_cache_path,
            top_k=top_k,
        )

    def search_with_query_vector(
        self,
        query_vector: np.ndarray,
        normalized_jsonl_path: Path,
        embedding_cache_path: Path,
        top_k: int = 50,
    ) -> list[RetrievalHit]:
        papers = load_normalized_jsonl(normalized_jsonl_path)
        with embedding_cache_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        id_to_paper = {paper.paper_id: paper for paper in papers}
        paper_ids: list[str] = []
        vectors: list[list[float]] = []
        for item in payload.get("items", []):
            paper_id = item["paper_id"]
            if paper_id not in id_to_paper:
                continue
            paper_ids.append(paper_id)
            vectors.append(item["embedding"])

        if not vectors:
            return []

        matrix = np.array(vectors, dtype=np.float32)
        matrix = self._normalize_matrix(matrix)

        scores = matrix @ query_vector
        ranked_indices = np.argsort(scores)[::-1][:top_k]

        hits: list[RetrievalHit] = []
        for idx in ranked_indices:
            paper_id = paper_ids[int(idx)]
            hits.append(
                RetrievalHit(
                    paper=id_to_paper[paper_id],
                    score=float(scores[int(idx)]),
                )
            )
        return hits
