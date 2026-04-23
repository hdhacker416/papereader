from __future__ import annotations

from pathlib import Path

from research.pipeline.search_pipeline import SearchPipeline, load_search_assets
from research.providers.dashscope_embedding import DashScopeEmbeddingClient
from research.providers.dashscope_rerank import DashScopeRerankClient


def main() -> None:
    summary_path = Path("data/research/build/build_summary_2025_2026.json")
    assets = load_search_assets(summary_path)

    pipeline = SearchPipeline(
        embedding_client=DashScopeEmbeddingClient(batch_size=10),
        rerank_client=DashScopeRerankClient(),
    )

    query = "large language model safety jailbreak prompt injection"
    result = pipeline.run(
        query=query,
        assets=assets,
        top_k_per_asset=10,
        top_k_global=50,
        rerank_top_n=10,
    )

    print(f"query={query}")
    print(f"assets={len(assets)}")
    print(f"coarse_elapsed_sec={result.coarse_elapsed_sec:.3f}")
    print(f"rerank_elapsed_sec={result.rerank_elapsed_sec:.3f}")
    print("top coarse:")
    for hit in result.coarse_hits[:5]:
        print(f"  {hit.score:.4f} {hit.paper.conference}{hit.paper.year} {hit.paper.title}")
    print("top rerank:")
    for item in result.reranked_hits[:5]:
        hit = item.hit
        print(
            f"  rerank={item.rerank_score:.4f} coarse={hit.score:.4f} "
            f"{hit.paper.conference}{hit.paper.year} {hit.paper.title}"
        )


if __name__ == "__main__":
    main()
