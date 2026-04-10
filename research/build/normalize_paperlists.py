from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from research.build.paperlists_repo import ConferenceFile
from research.config import BuildConfig, DEFAULT_CONFIG
from research.corpus.exporter import export_normalized_papers, write_manifest
from research.corpus.paperlists_loader import load_conference_file


@dataclass(frozen=True)
class NormalizeResult:
    conference: str
    year: int
    paper_count: int
    output_path: Path
    manifest_path: Path


def normalize_conference_file(
    conference_file: ConferenceFile,
    config: BuildConfig | None = None,
) -> NormalizeResult:
    cfg = config or DEFAULT_CONFIG.build
    papers = load_conference_file(conference_file, config=cfg)
    output_path = export_normalized_papers(
        papers,
        conference=conference_file.conference,
        year=conference_file.year,
        config=cfg,
    )
    manifest_path = write_manifest(
        papers,
        conference=conference_file.conference,
        year=conference_file.year,
        output_path=output_path,
    )
    return NormalizeResult(
        conference=conference_file.conference,
        year=conference_file.year,
        paper_count=len(papers),
        output_path=output_path,
        manifest_path=manifest_path,
    )
