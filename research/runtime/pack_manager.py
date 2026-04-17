from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from research.config import DEFAULT_CONFIG


@dataclass(frozen=True)
class RemotePackSpec:
    url: str
    sha256: str | None = None


@dataclass(frozen=True)
class InstalledPack:
    conference: str
    year: int
    version: str
    install_dir: Path
    manifest_path: Path
    normalized_path: Path
    embedding_path: Path


class PackManager:
    def __init__(
        self,
        installed_packs_dir: Path | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        self.installed_packs_dir = installed_packs_dir or DEFAULT_CONFIG.runtime.installed_packs_dir
        self.cache_dir = cache_dir or DEFAULT_CONFIG.runtime.cache_dir

    def install_from_url(self, remote: RemotePackSpec) -> InstalledPack:
        archive_path = self._download(remote)
        if remote.sha256:
            actual = self._sha256_file(archive_path)
            if actual != remote.sha256:
                raise ValueError(f"SHA256 mismatch for {archive_path.name}: expected {remote.sha256}, got {actual}")
        return self.install_from_archive(archive_path)

    def install_from_archive(self, archive_path: str | Path) -> InstalledPack:
        archive_path = Path(archive_path)
        if not archive_path.exists():
            raise FileNotFoundError(f"Archive not found: {archive_path}")

        with zipfile.ZipFile(archive_path, "r") as zf:
            manifest_member = self._find_manifest_member(zf)
            manifest = json.loads(zf.read(manifest_member).decode("utf-8"))
            conference = str(manifest["conference"]).lower()
            year = int(manifest["year"])
            version = str(manifest["version"])
            install_dir = self.installed_packs_dir / conference / str(year) / version
            if install_dir.exists():
                shutil.rmtree(install_dir)
            install_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=install_dir.parent) as tmp_dir:
                temp_extract_dir = Path(tmp_dir)
                zf.extractall(temp_extract_dir)
                extracted_root = temp_extract_dir / self._member_root_dir(manifest_member)
                if extracted_root.exists():
                    for child in extracted_root.iterdir():
                        shutil.move(str(child), install_dir / child.name)
                else:
                    for child in temp_extract_dir.iterdir():
                        shutil.move(str(child), install_dir / child.name)

        manifest_path = install_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        normalized_path = install_dir / manifest["files"]["normalized"]["archive_path"]
        embedding_path = install_dir / manifest["files"]["embeddings"]["archive_path"]
        if not normalized_path.exists():
            raise FileNotFoundError(f"Installed normalized file missing: {normalized_path}")
        if not embedding_path.exists():
            raise FileNotFoundError(f"Installed embedding file missing: {embedding_path}")

        return InstalledPack(
            conference=conference,
            year=year,
            version=version,
            install_dir=install_dir,
            manifest_path=manifest_path,
            normalized_path=normalized_path,
            embedding_path=embedding_path,
        )

    def list_installed(self) -> list[InstalledPack]:
        results: list[InstalledPack] = []
        if not self.installed_packs_dir.exists():
            return results
        for manifest_path in sorted(self.installed_packs_dir.glob("*/*/*/manifest.json")):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            install_dir = manifest_path.parent
            results.append(
                InstalledPack(
                    conference=str(manifest["conference"]).lower(),
                    year=int(manifest["year"]),
                    version=str(manifest["version"]),
                    install_dir=install_dir,
                    manifest_path=manifest_path,
                    normalized_path=install_dir / manifest["files"]["normalized"]["archive_path"],
                    embedding_path=install_dir / manifest["files"]["embeddings"]["archive_path"],
                )
            )
        return results

    def _download(self, remote: RemotePackSpec) -> Path:
        parsed = urlparse(remote.url)
        filename = Path(parsed.path).name or "pack.zip"
        download_dir = self.cache_dir / "downloads"
        download_dir.mkdir(parents=True, exist_ok=True)
        archive_path = download_dir / filename
        urllib.request.urlretrieve(remote.url, archive_path)
        return archive_path

    @staticmethod
    def _find_manifest_member(zf: zipfile.ZipFile) -> str:
        manifest_members = [name for name in zf.namelist() if name.endswith("manifest.json")]
        if not manifest_members:
            raise FileNotFoundError("manifest.json not found inside pack archive")
        root_level_manifest = next((name for name in manifest_members if "/" not in name.strip("/")), None)
        return root_level_manifest or manifest_members[0]

    @staticmethod
    def _member_root_dir(member: str) -> str:
        parts = Path(member).parts
        if len(parts) <= 1:
            return ""
        return parts[0]

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
