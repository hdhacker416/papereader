from __future__ import annotations

from research.agent.bounded import BoundedResearchRunner


def main() -> None:
    runner = BoundedResearchRunner()
    result = runner.run(
        user_query="帮我找找有哪些有趣的大模型安全后训练的文章，也不仅仅是安全吧，任何后训练的文章都可以",
    )
    print("brief:")
    print(result.brief)
    print()
    print("rounds:")
    for item in result.rounds:
        print("round", item.round_index, "queries", item.queries)
        print("decision", item.decision)
    print()
    print("selected:")
    for item in result.selected_papers:
        print(item["priority"], item["conference"], item["year"], item["paper"]["title"], "axis=", item["axis"])
    print()
    print("readings:")
    for item in result.reading_results:
        print(item["read_status"], item["paper"]["conference"], item["paper"]["year"], item["paper"]["title"])
    print()
    print(result.final_text)


if __name__ == "__main__":
    main()
