from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
for path in (ROOT_DIR, BACKEND_DIR):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from backend import schemas  # noqa: E402
from backend.services import community_service  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Precompute cache-first community topic answers.")
    parser.add_argument("--topic-id", action="append", help="Topic id to precompute. Repeat for multiple topics.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--max-text-chars", type=int, default=120000)
    parser.add_argument("--figure-max-pages", type=int, default=12)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    topic_ids = args.topic_id or [topic["id"] for topic in community_service.TOPICS]
    payload = schemas.CommunityAnswerRequest(
        query="placeholder",
        limit=args.limit,
        max_text_chars=args.max_text_chars,
        figure_max_pages=args.figure_max_pages,
    )
    for index, topic_id in enumerate(topic_ids, start=1):
        print(f"[{index}/{len(topic_ids)}] precomputing {topic_id}", flush=True)
        result = community_service.generate_topic(topic_id, payload)
        print(f"  cached {len(result.results)} displayed answers", flush=True)


if __name__ == "__main__":
    main()
