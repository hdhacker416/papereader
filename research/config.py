from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
RESOURCE_DIR = DATA_DIR / "resource"
RESEARCH_DATA_DIR = DATA_DIR / "research"


@dataclass(frozen=True)
class BuildConfig:
    # Fixed upstream source for offline GPU-side data preparation.
    paperlists_repo_url: str = "https://github.com/papercopilot/paperlists.git"
    paperlists_repo_dir: Path = RESOURCE_DIR / "paperlists"

    # Local build outputs on the GPU machine.
    build_root_dir: Path = RESEARCH_DATA_DIR / "build"
    normalized_corpus_dir: Path = RESEARCH_DATA_DIR / "build" / "normalized"
    embeddings_dir: Path = RESEARCH_DATA_DIR / "build" / "embeddings"
    indexes_dir: Path = RESEARCH_DATA_DIR / "build" / "indexes"
    packs_dir: Path = RESEARCH_DATA_DIR / "packs"

    # Defaults for offline jobs.
    default_conferences: Sequence[str] = field(
        default_factory=lambda: ("iclr", "icml", "nips", "cvpr", "acl", "emnlp")
    )
    required_text_fields: Sequence[str] = field(
        default_factory=lambda: ("title", "abstract")
    )

    # These are lower-cased substring rules for filtering obvious non-accepted papers.
    rejected_status_markers: Sequence[str] = field(
        default_factory=lambda: ("reject", "withdraw")
    )

    # Files outside conference/year data should be ignored.
    ignored_top_level_names: Sequence[str] = field(
        default_factory=lambda: (".git", ".github", "README.md", ".gitignore", "croissant.json")
    )


@dataclass(frozen=True)
class RuntimeConfig:
    # Downloaded or installed packs used by online research logic.
    installed_packs_dir: Path = RESEARCH_DATA_DIR / "installed_packs"
    cache_dir: Path = RESEARCH_DATA_DIR / "cache"
    pdf_cache_dir: Path = RESEARCH_DATA_DIR / "runtime" / "pdfs"
    reading_cache_dir: Path = RESEARCH_DATA_DIR / "runtime" / "readings"

    # Retrieval defaults for online query-time execution.
    coarse_retrieval_top_k: int = 200
    rerank_top_k: int = 40
    deep_read_top_k: int = 12

    # Reader / report defaults.
    max_pdf_download_retries: int = 2
    report_max_papers: int = 12


@dataclass(frozen=True)
class ResearchConfig:
    root_dir: Path = ROOT_DIR
    data_dir: Path = DATA_DIR
    resource_dir: Path = RESOURCE_DIR
    research_data_dir: Path = RESEARCH_DATA_DIR
    build: BuildConfig = field(default_factory=BuildConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)


DEFAULT_CONFIG = ResearchConfig()
