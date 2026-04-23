from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research.config import DEFAULT_CONFIG


BUILD_SUMMARY_CANDIDATES = [
    DEFAULT_CONFIG.build.build_root_dir / "build_summary_ai_top_2024_2026.json",
    DEFAULT_CONFIG.build.build_root_dir / "build_summary_2025_2026.json",
]

PACK_NAME_ALIASES = {
    "nips": "neurips",
}


def resolve_default_build_summary_path() -> Path:
    for path in BUILD_SUMMARY_CANDIDATES:
        if path.exists():
            return path
    return BUILD_SUMMARY_CANDIDATES[0]


@dataclass(frozen=True)
class PackBuildResult:
    conference: str
    year: int
    version: str
    pack_name: str
    pack_path: Path
    manifest_path: Path
    sha256_path: Path
    file_count: int
    pack_size_bytes: int


class Packager:
    def __init__(
        self,
        packs_dir: Path | None = None,
        build_summary_path: Path | None = None,
    ) -> None:
        self.packs_dir = packs_dir or DEFAULT_CONFIG.build.packs_dir
        self.build_summary_path = build_summary_path or resolve_default_build_summary_path()

    def build_pack(
        self,
        conference: str,
        year: int,
        version: str = "v1",
    ) -> PackBuildResult:
        conference = conference.lower().strip()
        summary_item = self._get_summary_item(conference=conference, year=year)

        normalized_path = Path(summary_item["normalized_path"]).resolve()
        embedding_path = Path(summary_item["embedding_path"]).resolve()
        return self.build_pack_from_files(
            conference=conference,
            year=year,
            normalized_path=normalized_path,
            embedding_path=embedding_path,
            version=version,
        )

    def build_pack_from_files(
        self,
        conference: str,
        year: int,
        normalized_path: Path,
        embedding_path: Path,
        version: str = "v1",
    ) -> PackBuildResult:
        conference = conference.lower().strip()
        normalized_manifest_path = normalized_path.with_suffix(".manifest.json")

        if not normalized_path.exists():
            raise FileNotFoundError(f"Normalized corpus file not found: {normalized_path}")
        if not embedding_path.exists():
            raise FileNotFoundError(f"Embedding file not found: {embedding_path}")
        if not normalized_manifest_path.exists():
            raise FileNotFoundError(f"Manifest file not found: {normalized_manifest_path}")

        pack_name = self._pack_name(conference=conference, year=year)
        pack_root = self.packs_dir / conference / str(year)
        pack_root.mkdir(parents=True, exist_ok=True)

        pack_path = pack_root / f"{pack_name}.zip"
        manifest_path = pack_root / f"{pack_name}.manifest.json"
        sha256_path = pack_root / f"{pack_name}.sha256"

        pack_manifest = self._build_manifest(
            conference=conference,
            year=year,
            version=version,
            paper_count=self._read_paper_count(normalized_manifest_path),
            normalized_path=normalized_path,
            embedding_path=embedding_path,
            normalized_manifest_path=normalized_manifest_path,
        )
        archive_root = f"{pack_name}/"

        archive_members = {
            f"{archive_root}normalized/{normalized_path.name}": normalized_path,
            f"{archive_root}embeddings/{embedding_path.name}": embedding_path,
            f"{archive_root}metadata/{normalized_manifest_path.name}": normalized_manifest_path,
        }

        with zipfile.ZipFile(pack_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                f"{archive_root}manifest.json",
                json.dumps(pack_manifest, ensure_ascii=False, indent=2),
            )
            for archive_name, source_path in archive_members.items():
                zf.write(source_path, arcname=archive_name)

        sha256_value = self._sha256_file(pack_path)
        manifest_path.write_text(
            json.dumps(pack_manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        sha256_path.write_text(f"{sha256_value}  {pack_path.name}\n", encoding="utf-8")

        return PackBuildResult(
            conference=conference,
            year=year,
            version=version,
            pack_name=pack_name,
            pack_path=pack_path,
            manifest_path=manifest_path,
            sha256_path=sha256_path,
            file_count=1 + len(archive_members),
            pack_size_bytes=pack_path.stat().st_size,
        )

    def build_many(
        self,
        conferences: list[str] | None = None,
        years: list[int] | None = None,
        version: str = "v1",
    ) -> list[PackBuildResult]:
        summary_items = self._load_summary_items()
        results: list[PackBuildResult] = []
        conference_filter = {item.lower() for item in conferences} if conferences else None
        year_filter = set(years) if years else None

        for item in summary_items:
            conference = str(item["conference"]).lower()
            year = int(item["year"])
            if conference_filter is not None and conference not in conference_filter:
                continue
            if year_filter is not None and year not in year_filter:
                continue
            results.append(self.build_pack(conference=conference, year=year, version=version))
        return results

    def _build_manifest(
        self,
        conference: str,
        year: int,
        version: str,
        paper_count: int | None,
        normalized_path: Path,
        embedding_path: Path,
        normalized_manifest_path: Path,
    ) -> dict[str, Any]:
        normalized_manifest = json.loads(normalized_manifest_path.read_text(encoding="utf-8"))
        pack_name = self._pack_name(conference=conference, year=year)
        return {
            "pack_name": pack_name,
            "conference": conference,
            "year": year,
            "version": version,
            "created_from": "paperreader research build",
            "paper_count": paper_count,
            "files": {
                "normalized": {
                    "archive_path": f"normalized/{normalized_path.name}",
                    "filename": normalized_path.name,
                    "size_bytes": normalized_path.stat().st_size,
                    "sha256": self._sha256_file(normalized_path),
                },
                "embeddings": {
                    "archive_path": f"embeddings/{embedding_path.name}",
                    "filename": embedding_path.name,
                    "size_bytes": embedding_path.stat().st_size,
                    "sha256": self._sha256_file(embedding_path),
                },
                "normalized_manifest": {
                    "archive_path": f"metadata/{normalized_manifest_path.name}",
                    "filename": normalized_manifest_path.name,
                    "size_bytes": normalized_manifest_path.stat().st_size,
                    "sha256": self._sha256_file(normalized_manifest_path),
                    "paper_count": normalized_manifest.get("paper_count"),
                },
            },
        }

    @staticmethod
    def _pack_name(conference: str, year: int) -> str:
        display_conference = PACK_NAME_ALIASES.get(conference, conference)
        short_year = str(year)[-2:]
        return f"{display_conference}-{short_year}"

    def _get_summary_item(self, conference: str, year: int) -> dict[str, Any]:
        for item in self._load_summary_items():
            if str(item["conference"]).lower() == conference and int(item["year"]) == year:
                return item
        raise ValueError(f"No build summary item found for {conference} {year}")

    def _load_summary_items(self) -> list[dict[str, Any]]:
        payload = json.loads(self.build_summary_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return payload
        return payload.get("results", [])

    @staticmethod
    def _read_paper_count(normalized_manifest_path: Path) -> int | None:
        try:
            normalized_manifest = json.loads(normalized_manifest_path.read_text(encoding="utf-8"))
            return normalized_manifest.get("paper_count")
        except Exception:
            return None

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
