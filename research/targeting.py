from __future__ import annotations

from datetime import date
from typing import Iterable


DEFAULT_TARGET_YEAR_WINDOW = 3

CONFERENCE_DISPLAY_NAMES = {
    "aaai": "AAAI",
    "acl": "ACL",
    "aistats": "AISTATS",
    "coling": "COLING",
    "colm": "COLM",
    "colt": "COLT",
    "cvpr": "CVPR",
    "eccv": "ECCV",
    "emnlp": "EMNLP",
    "iccv": "ICCV",
    "iclr": "ICLR",
    "icml": "ICML",
    "ijcai": "IJCAI",
    "naacl": "NAACL",
    "nips": "NeurIPS",
}


def default_recent_years(
    reference_year: int | None = None,
    window: int = DEFAULT_TARGET_YEAR_WINDOW,
) -> list[int]:
    year = reference_year or date.today().year
    start_year = year - max(window, 1) + 1
    return list(range(start_year, year + 1))


def normalize_target_years(
    years: Iterable[int] | None,
    available_years: Iterable[int] | None = None,
    reference_year: int | None = None,
    window: int = DEFAULT_TARGET_YEAR_WINDOW,
) -> list[int]:
    normalized = sorted({int(item) for item in (years or [])})
    if normalized:
        return normalized

    recent = default_recent_years(reference_year=reference_year, window=window)
    if available_years is None:
        return recent

    available = sorted({int(item) for item in available_years})
    if not available:
        return recent

    available_set = set(available)
    overlap = [item for item in recent if item in available_set]
    if overlap:
        return overlap
    return available[-min(len(available), max(window, 1)) :]


def conference_display_name(code: str) -> str:
    value = code.strip().lower()
    return CONFERENCE_DISPLAY_NAMES.get(value, value.upper())
