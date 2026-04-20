from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

load_dotenv(ROOT_DIR / "backend" / ".env")

from database import check_and_migrate_database, engine
import models
from research.agent.bounded import BoundedResearchRunner


QUERY = "安全对齐的文章有哪些"
CONFERENCES = ["iclr"]
YEARS = [2026]
MODEL = "gemini-3-flash-preview"
MAX_SEARCH_ROUNDS = 5
MAX_QUERIES_PER_ROUND = 5
MAX_FULL_READS = 12


def _bootstrap() -> None:
    models.Base.metadata.create_all(bind=engine)
    check_and_migrate_database()


def main() -> None:
    _bootstrap()

    runner = BoundedResearchRunner(model=MODEL)
    result = runner.run_selection(
        user_query=QUERY,
        conferences=CONFERENCES,
        years=YEARS,
        max_search_rounds=MAX_SEARCH_ROUNDS,
        max_queries_per_round=MAX_QUERIES_PER_ROUND,
        max_full_reads=MAX_FULL_READS,
        min_full_reads=1,
    )

    print("\n=== CONFIG ===")
    print(
        json.dumps(
            {
                "query": QUERY,
                "conferences": CONFERENCES,
                "years": YEARS,
                "model": MODEL,
                "max_search_rounds": MAX_SEARCH_ROUNDS,
                "max_queries_per_round": MAX_QUERIES_PER_ROUND,
                "max_full_reads": MAX_FULL_READS,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    print("\n=== BRIEF ===")
    print(
        json.dumps(
            {
                "research_goal": result.brief.research_goal,
                "search_axes": result.brief.search_axes,
                "initial_queries": result.brief.initial_queries,
                "rerank_query": result.brief.rerank_query,
                "reading_prompts": result.brief.reading_prompts,
                "target_conferences": result.brief.target_conferences,
                "target_years": result.brief.target_years,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    print("\n=== ROUNDS ===")
    for round_item in result.rounds:
        print(f"\n--- Round {round_item.round_index} ---")
        payload = {
            "queries": round_item.queries,
            "coarse_hits": sum(len(item["results"]) for item in round_item.coarse_results),
            "merged_candidates": len(round_item.merged_candidates),
            "reranked_candidates": len(round_item.reranked_results),
            "decision": {
                "continue_search": round_item.decision.continue_search,
                "rationale": round_item.decision.rationale,
                "missing_axes": round_item.decision.missing_axes,
                "additional_queries": round_item.decision.additional_queries,
                "selected_papers": [
                    {
                        "title": item.title,
                        "paper_id": item.paper_id,
                        "conference": item.conference,
                        "year": item.year,
                        "axis": item.axis,
                        "priority": item.priority,
                        "reason": item.reason,
                    }
                    for item in round_item.selected_papers
                ],
            },
            "top_reranked": [
                {
                    "title": item["paper"]["title"],
                    "conference": item["paper"]["conference"],
                    "year": item["paper"]["year"],
                    "rerank_score": item["rerank_score"],
                }
                for item in round_item.reranked_results[:10]
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    print("\n=== SELECTED PAPERS ===")
    print(
        json.dumps(
            [
                {
                    "title": item["paper"]["title"],
                    "conference": item["conference"],
                    "year": item["year"],
                    "paper_id": item["paper_id"],
                    "axis": item["axis"],
                    "priority": item["priority"],
                    "coarse_score": item["coarse_score"],
                    "rerank_score": item["rerank_score"],
                    "reason": item["reason"],
                }
                for item in result.selected_papers
            ],
            ensure_ascii=False,
            indent=2,
        )
    )

    print("\n=== DETAIL RESULTS ===")
    print(
        json.dumps(
            [
                {
                    "paper_id": item["paper_id"],
                    "conference": item["conference"],
                    "year": item["year"],
                    "title": item["title"],
                    "source_url": item["source_url"],
                }
                for item in result.detail_results
            ],
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
