from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from research.config import BuildConfig, DEFAULT_CONFIG


CONFERENCE_FILE_RE = re.compile(r"^(?P<conference>[a-z0-9_+-]+)(?P<year>\d{4})\.json$")


@dataclass(frozen=True)
class ConferenceFile:
    conference: str
    year: int
    path: Path


def _run_git(args: list[str], cwd: Path | None = None) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True)


def ensure_paperlists_repo(config: BuildConfig | None = None) -> Path:
    cfg = config or DEFAULT_CONFIG.build
    repo_dir = cfg.paperlists_repo_dir

    if (repo_dir / ".git").exists():
        _run_git(["pull", "--ff-only"], cwd=repo_dir)
        return repo_dir

    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    _run_git(["clone", cfg.paperlists_repo_url, str(repo_dir)])
    return repo_dir


def list_conference_files(config: BuildConfig | None = None) -> list[ConferenceFile]:
    cfg = config or DEFAULT_CONFIG.build
    repo_dir = cfg.paperlists_repo_dir
    results: list[ConferenceFile] = []

    if not repo_dir.exists():
        return results

    ignored = set(cfg.ignored_top_level_names)

    for conference_dir in sorted(repo_dir.iterdir()):
        if conference_dir.name in ignored or not conference_dir.is_dir():
            continue

        for json_file in sorted(conference_dir.glob("*.json")):
            match = CONFERENCE_FILE_RE.match(json_file.name)
            if not match:
                continue

            conference = match.group("conference")
            year = int(match.group("year"))
            results.append(
                ConferenceFile(
                    conference=conference,
                    year=year,
                    path=json_file,
                )
            )

    return results


def filter_conference_files(
    files: Iterable[ConferenceFile],
    conferences: Iterable[str] | None = None,
    years: Iterable[int] | None = None,
) -> list[ConferenceFile]:
    conference_set = {item.lower() for item in conferences} if conferences else None
    year_set = set(years) if years else None

    filtered: list[ConferenceFile] = []
    for item in files:
        if conference_set is not None and item.conference.lower() not in conference_set:
            continue
        if year_set is not None and item.year not in year_set:
            continue
        filtered.append(item)
    return filtered
