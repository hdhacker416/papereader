from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Iterable

from research.config import BuildConfig, DEFAULT_CONFIG
from research.corpus.paperlists_loader import NormalizedPaper


def paper_to_dict(paper: NormalizedPaper) -> dict:
    return {
        "paper_id": paper.paper_id,
        "conference": paper.conference,
        "year": paper.year,
        "title": paper.title,
        "abstract": paper.abstract,
        "authors": list(paper.authors),
        "source_url": paper.source_url,
        "raw_status": paper.raw_status,
        "normalized_status": paper.normalized_status,
        "raw_payload": paper.raw_payload,
    }


def build_output_path(
    conference: str,
    year: int,
    config: BuildConfig | None = None,
) -> Path:
    cfg = config or DEFAULT_CONFIG.build
    return cfg.normalized_corpus_dir / conference / f"{conference}{year}.jsonl"


def export_normalized_papers(
    papers: Iterable[NormalizedPaper],
    conference: str,
    year: int,
    config: BuildConfig | None = None,
) -> Path:
    cfg = config or DEFAULT_CONFIG.build
    output_path = build_output_path(conference, year, config=cfg)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with output_path.open("w", encoding="utf-8") as f:
        for paper in papers:
            f.write(json.dumps(paper_to_dict(paper), ensure_ascii=False) + "\n")
            count += 1

    return output_path


def write_manifest(
    papers: Iterable[NormalizedPaper],
    conference: str,
    year: int,
    output_path: Path,
) -> Path:
    paper_list = list(papers)
    status_counter = Counter(p.normalized_status for p in paper_list)
    manifest = {
        "conference": conference,
        "year": year,
        "paper_count": len(paper_list),
        "statuses": dict(status_counter),
        "output_file": str(output_path),
    }

    manifest_path = output_path.with_suffix(".manifest.json")
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return manifest_path
