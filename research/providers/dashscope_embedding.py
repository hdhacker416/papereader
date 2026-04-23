from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Iterable

from openai import OpenAI


DEFAULT_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_EMBEDDING_MODEL = "text-embedding-v4"
DEFAULT_EMBEDDING_BATCH_SIZE = 10


@dataclass(frozen=True)
class EmbeddingResult:
    text: str
    embedding: list[float]


class DashScopeEmbeddingClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEFAULT_DASHSCOPE_BASE_URL,
        model: str = DEFAULT_EMBEDDING_MODEL,
        dimensions: int = 1024,
        batch_size: int = DEFAULT_EMBEDDING_BATCH_SIZE,
    ) -> None:
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self.base_url = base_url
        self.model = model
        self.dimensions = dimensions
        self.batch_size = batch_size
        self._client: OpenAI | None = None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get_client(self) -> OpenAI:
        if not self.api_key:
            raise RuntimeError("DASHSCOPE_API_KEY is not configured")
        if self._client is None:
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    def embed_text(self, text: str) -> EmbeddingResult:
        client = self._get_client()
        response = client.embeddings.create(
            model=self.model,
            input=text,
            dimensions=self.dimensions,
            encoding_format="float",
        )
        return EmbeddingResult(
            text=text,
            embedding=list(response.data[0].embedding),
        )

    def embed_many(self, texts: Iterable[str]) -> list[EmbeddingResult]:
        return self.embed_many_with_progress(texts)

    def embed_many_with_progress(
        self,
        texts: Iterable[str],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[EmbeddingResult]:
        items = list(texts)
        if not items:
            return []

        client = self._get_client()
        results: list[EmbeddingResult] = []
        step = min(max(self.batch_size, 1), DEFAULT_EMBEDDING_BATCH_SIZE)

        for i in range(0, len(items), step):
            batch = items[i : i + step]
            response = client.embeddings.create(
                model=self.model,
                input=batch,
                dimensions=self.dimensions,
                encoding_format="float",
            )
            for text, item in zip(batch, response.data, strict=True):
                results.append(
                    EmbeddingResult(
                        text=text,
                        embedding=list(item.embedding),
                    )
                )
            if progress_callback is not None:
                progress_callback(min(i + len(batch), len(items)), len(items))

        return results
