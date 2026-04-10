from __future__ import annotations

import os
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Iterable


DEFAULT_RERANK_MODEL = "qwen3-rerank"


@dataclass(frozen=True)
class RerankItem:
    index: int
    relevance_score: float
    document: str | None = None


class DashScopeRerankClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_RERANK_MODEL,
    ) -> None:
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self.model = model

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def rerank(
        self,
        query: str,
        documents: Iterable[str],
        top_n: int = 20,
        instruct: str = "Given a search query, retrieve relevant passages that answer the query.",
        return_documents: bool = True,
    ) -> list[RerankItem]:
        if not self.api_key:
            raise RuntimeError("DASHSCOPE_API_KEY is not configured")

        try:
            import dashscope
        except ImportError as exc:
            raise RuntimeError(
                "dashscope package is required for rerank calls"
            ) from exc

        dashscope.api_key = self.api_key
        response = dashscope.TextReRank.call(
            model=self.model,
            query=query,
            documents=list(documents),
            top_n=top_n,
            return_documents=return_documents,
            instruct=instruct,
        )

        if response.status_code != HTTPStatus.OK:
            raise RuntimeError(
                f"DashScope rerank failed: status={response.status_code}, body={response}"
            )

        results: list[RerankItem] = []
        for item in _extract_results(response):
            results.append(
                RerankItem(
                    index=int(item.get("index", -1)),
                    relevance_score=float(item.get("relevance_score", 0.0)),
                    document=item.get("document"),
                )
            )
        return results


def _extract_results(response: Any) -> list[dict[str, Any]]:
    output = getattr(response, "output", None)
    if output is None:
        return []

    if isinstance(output, dict):
        results = output.get("results")
        return results if isinstance(results, list) else []

    results = getattr(output, "results", None)
    return results if isinstance(results, list) else []
