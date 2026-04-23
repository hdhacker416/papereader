from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from research.build.paperlists_repo import ConferenceFile
from research.config import BuildConfig, DEFAULT_CONFIG


@dataclass(frozen=True)
class NormalizedPaper:
    paper_id: str
    conference: str
    year: int
    title: str
    abstract: str
    authors: tuple[str, ...]
    source_url: str
    raw_status: str
    normalized_status: str
    raw_payload: dict[str, Any]


def normalize_status(raw_status: str, config: BuildConfig | None = None) -> str:
    cfg = config or DEFAULT_CONFIG.build
    value = (raw_status or "").strip().lower()

    if not value:
        return "unknown"

    for marker in cfg.rejected_status_markers:
        if marker in value:
            if marker == "withdraw":
                return "withdrawn"
            return "rejected"

    return "accepted"


def should_keep_paper(raw_status: str, config: BuildConfig | None = None) -> bool:
    return normalize_status(raw_status, config=config) == "accepted"


def split_authors(value: str) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in value.split(";") if part.strip())


def load_paperlist_json(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"Expected list payload in {path}, got {type(data).__name__}")

    return data


def normalize_record(
    conference_file: ConferenceFile,
    record: dict[str, Any],
    config: BuildConfig | None = None,
) -> NormalizedPaper | None:
    cfg = config or DEFAULT_CONFIG.build

    title = (record.get("title") or "").strip()
    abstract = (record.get("abstract") or "").strip()
    paper_id = str(record.get("id") or "").strip()
    source_url = (record.get("site") or "").strip()
    raw_status = (record.get("status") or "").strip()

    if not title or not abstract or not paper_id:
        return None

    if not should_keep_paper(raw_status, config=cfg):
        return None

    return NormalizedPaper(
        paper_id=paper_id,
        conference=conference_file.conference,
        year=conference_file.year,
        title=title,
        abstract=abstract,
        authors=split_authors(record.get("author") or ""),
        source_url=source_url,
        raw_status=raw_status,
        normalized_status=normalize_status(raw_status, config=cfg),
        raw_payload=record,
    )


def load_conference_file(
    conference_file: ConferenceFile,
    config: BuildConfig | None = None,
) -> list[NormalizedPaper]:
    records = load_paperlist_json(conference_file.path)
    papers: list[NormalizedPaper] = []

    for record in records:
        if not isinstance(record, dict):
            continue
        normalized = normalize_record(conference_file, record, config=config)
        if normalized is not None:
            papers.append(normalized)

    return papers


def load_many_conference_files(
    conference_files: Iterable[ConferenceFile],
    config: BuildConfig | None = None,
) -> list[NormalizedPaper]:
    papers: list[NormalizedPaper] = []
    for conference_file in conference_files:
        papers.extend(load_conference_file(conference_file, config=config))
    return papers
