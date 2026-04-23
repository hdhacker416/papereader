from __future__ import annotations

from research.agent.semi_fixed import SemiFixedResearchRunner


def main() -> None:
    runner = SemiFixedResearchRunner()
    result = runner.run(
        user_query="请帮我总结 ICLR 2025 和 NeurIPS 2025 里与大模型安全、越狱和 prompt injection 最相关的论文方向。",
        conferences=["iclr", "nips"],
        years=[2025],
    )
    print("plan:")
    print(result.plan)
    print()
    print("coarse sub_queries:")
    for item in result.coarse_results:
        print("-", item["sub_query"], len(item["results"]))
    print()
    print("top reranked:")
    for item in result.reranked_results[:5]:
        print(item["rerank_score"], item["paper"]["conference"], item["paper"]["year"], item["paper"]["title"])
    print()
    print("paper readings:")
    for item in result.reading_results:
        print(
            item["read_status"],
            item["paper"]["conference"],
            item["paper"]["year"],
            item["paper"]["title"],
        )
    print()
    print(result.final_text)


if __name__ == "__main__":
    main()
