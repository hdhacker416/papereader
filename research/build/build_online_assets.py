from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from research.build.normalize_paperlists import normalize_conference_file
from research.build.paperlists_repo import (
    ConferenceFile,
    filter_conference_files,
    list_conference_files,
)
from research.providers.dashscope_embedding import DashScopeEmbeddingClient
from research.retrieval.embedding_index import EmbeddingIndex


@dataclass(frozen=True)
class BuildAssetResult:
    conference: str
    year: int
    paper_count: int
    normalized_path: str
    embedding_path: str


def select_available_files(
    conferences: Iterable[str],
    years: Iterable[int],
) -> tuple[list[ConferenceFile], list[dict[str, int | str]]]:
    available = list_conference_files()
    selected = filter_conference_files(available, conferences=conferences, years=years)
    found = {(item.conference, item.year) for item in selected}

    missing: list[dict[str, int | str]] = []
    for conference in conferences:
        for year in years:
            if (conference, year) not in found:
                missing.append({"conference": conference, "year": year})

    selected.sort(key=lambda item: (item.conference, item.year))
    return selected, missing


def build_online_assets(
    conferences: Iterable[str],
    years: Iterable[int],
    force_embeddings: bool = False,
) -> tuple[list[BuildAssetResult], list[dict[str, int | str]]]:
    files, missing = select_available_files(conferences, years)
    embedding_client = DashScopeEmbeddingClient()
    embedding_index = EmbeddingIndex(embedding_client)

    results: list[BuildAssetResult] = []
    for conference_file in files:
        normalized = normalize_conference_file(conference_file)
        embedding_path = embedding_index.build_and_cache_embeddings(
            conference=conference_file.conference,
            year=conference_file.year,
            normalized_jsonl_path=Path(normalized.output_path),
            force=force_embeddings,
        )
        results.append(
            BuildAssetResult(
                conference=conference_file.conference,
                year=conference_file.year,
                paper_count=normalized.paper_count,
                normalized_path=str(normalized.output_path),
                embedding_path=str(embedding_path),
            )
        )
    return results, missing


def write_summary(
    results: Iterable[BuildAssetResult],
    missing: Iterable[dict[str, int | str]],
    output_path: Path,
) -> Path:
    payload = {
        "results": [asdict(item) for item in results],
        "missing": list(missing),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return output_path
