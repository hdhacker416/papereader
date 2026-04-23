from __future__ import annotations

from research.agent.runner import ResearchAgentRunner


SYSTEM_PROMPT = """You are a research assistant focused on academic paper discovery.
Use the provided tools to search, rerank, and inspect papers before answering.
Prefer structured search over guessing.
Keep the final answer concise and evidence-based.
Today is April 9, 2026.
Never claim a conference is unavailable if the tools return results.
Never invent paper IDs, conference names, or years.
Use this workflow unless the user asks otherwise:
1. Call coarse_search once.
2. Call rerank_search on the returned coarse_search.results.
3. Only call get_paper_details with paper_id values that came directly from tool results.
Base the final answer only on tool outputs.
"""


def main() -> None:
    runner = ResearchAgentRunner()
    result = runner.run(
        user_query="请帮我总结 ICLR 2025 和 NeurIPS 2025 里与大模型安全、越狱和 prompt injection 最相关的论文方向。",
        system_prompt=SYSTEM_PROMPT,
        max_rounds=8,
    )
    print("tool_calls:", len(result.tool_calls))
    for item in result.tool_calls:
        print(item["tool_name"])
    print()
    print(result.final_text)


if __name__ == "__main__":
    main()
