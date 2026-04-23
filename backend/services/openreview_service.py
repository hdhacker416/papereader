import logging
import datetime
import difflib
import re
import time
from typing import Dict, List, Optional

import requests
try:
    import openreview
except ImportError:
    openreview = None

logger = logging.getLogger(__name__)

TITLE_TOKEN_RE = re.compile(r"[a-z0-9]+")
OPENREVIEW_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
MIN_ACCEPTABLE_TITLE_SCORE = 0.72
OPENREVIEW_SEARCH_TIME_BUDGET_SECONDS = 8.0


def _normalize_title(title: str) -> str:
    return " ".join(TITLE_TOKEN_RE.findall(title.lower()))


def _title_score(query_title: str, candidate_title: str) -> float:
    query = _normalize_title(query_title)
    candidate = _normalize_title(candidate_title)
    if not query or not candidate:
        return 0.0
    if query == candidate:
        return 1.0

    query_tokens = set(query.split())
    candidate_tokens = set(candidate.split())
    overlap = len(query_tokens & candidate_tokens) / max(len(query_tokens), 1)
    ratio = difflib.SequenceMatcher(None, query, candidate).ratio()
    contains = 1.0 if query in candidate or candidate in query else 0.0
    return max(ratio, 0.65 * ratio + 0.25 * overlap + 0.10 * contains)


def _title_variants(title: str) -> List[str]:
    clean_title = title.replace("\n", " ").strip()
    normalized = _normalize_title(clean_title)
    variants = [clean_title]
    punctuation_stripped = re.sub(r"[^\w\s]", " ", clean_title)
    punctuation_stripped = " ".join(punctuation_stripped.split())
    if punctuation_stripped and punctuation_stripped not in variants:
        variants.append(punctuation_stripped)
    if normalized and normalized not in variants:
        variants.append(normalized)
    return variants


def _extract_title(note) -> str:
    title = note.content.get("title", "")
    if isinstance(title, dict):
        title = title.get("value", "")
    return str(title or "").strip()


def _extract_abstract(note) -> str:
    abstract = note.content.get("abstract", "")
    if isinstance(abstract, dict):
        abstract = abstract.get("value", "")
    return str(abstract or "").strip()


def _build_payload(note, source_title: str) -> Dict:
    return {
        "title": _extract_title(note) or source_title,
        "authors": [],
        "abstract": _extract_abstract(note),
        "pdf_url": f"https://openreview.net/pdf?id={note.id}",
        "source": "openreview",
        "source_url": f"https://openreview.net/forum?id={note.id}",
        "published": None,
    }


def _maybe_pick_best(title: str, notes) -> Optional[Dict]:
    best_note = None
    best_score = 0.0
    for note in notes:
        candidate_title = _extract_title(note)
        if not candidate_title:
            continue
        score = _title_score(title, candidate_title)
        if score > best_score:
            best_note = note
            best_score = score
        if score >= 0.98:
            break

    if best_note and best_score >= MIN_ACCEPTABLE_TITLE_SCORE:
        logger.info(
            "OpenReview matched '%s' to '%s' with score %.3f",
            title,
            _extract_title(best_note),
            best_score,
        )
        return _build_payload(best_note, title)
    return None


def _search_openreview_html(title: str) -> Optional[Dict]:
    variants = _title_variants(title)
    patterns = [
        re.compile(r"https://openreview\.net/forum\?id=([A-Za-z0-9_-]+)"),
        re.compile(r"https://openreview\.net/pdf\?id=([A-Za-z0-9_-]+)"),
        re.compile(r"[?&]id=([A-Za-z0-9_-]{8,})"),
    ]
    for variant in variants[:2]:
        try:
            response = requests.get(
                "https://openreview.net/search",
                params={"term": variant},
                headers=OPENREVIEW_HEADERS,
                timeout=20,
            )
            response.raise_for_status()
            text = response.text
            if _normalize_title(title) not in _normalize_title(text):
                continue
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    note_id = match.group(1)
                    return {
                        "title": title,
                        "authors": [],
                        "abstract": "",
                        "pdf_url": f"https://openreview.net/pdf?id={note_id}",
                        "source": "openreview",
                        "source_url": f"https://openreview.net/forum?id={note_id}",
                        "published": None,
                    }
        except Exception as exc:
            logger.debug("OpenReview HTML fallback failed for %s: %s", variant, exc)
    return None

def get_openreview_venue_ids(conference: str, year: str) -> List[str]:
    """
    Get possible OpenReview venue IDs for a given conference and year.
    """
    conf = conference.lower().strip()
    try:
        y = int(year)
    except ValueError:
        return []
    
    venues = []
    
    # Common patterns
    if conf == 'iclr':
        venues.append(f'ICLR.cc/{y}/Conference')
    elif conf in ('nips', 'neurips'):
        venues.append(f'NeurIPS.cc/{y}/Conference')
    elif conf == 'icml':
        venues.append(f'ICML.cc/{y}/Conference')
    elif conf == 'uai':
        venues.append(f'auai.org/UAI/{y}/Conference')
        
    return venues

def search_openreview(title: str) -> Optional[Dict]:
    """
    Search for a paper on OpenReview by title.
    Returns metadata dict if found, None otherwise.
    """
    clean_title = title.replace("\n", " ").strip()
    title_variants = _title_variants(clean_title)
    deadline = time.monotonic() + OPENREVIEW_SEARCH_TIME_BUDGET_SECONDS
    
    venue_ids = []
    current_year = datetime.datetime.now().year
    target_years = range(current_year, 2022, -1)
    target_confs = ['iclr', 'neurips', 'icml', 'uai']
    
    for y in target_years:
        for conf in target_confs:
            venue_ids.extend(get_openreview_venue_ids(conf, str(y)))
            
    if openreview is None:
        logger.warning("OpenReview dependency is not installed; skipping OpenReview search.")
        return _search_openreview_html(title)
    
    try:
        try:
            client = openreview.api.OpenReviewClient(baseurl='https://api2.openreview.net')
            for variant in title_variants:
                if time.monotonic() >= deadline:
                    break
                for vid in venue_ids:
                    if time.monotonic() >= deadline:
                        break
                    try:
                        notes = client.get_notes(content={'venueid': vid, 'title': variant}, limit=5)
                        payload = _maybe_pick_best(title, notes)
                        if payload:
                            return payload
                    except Exception:
                        continue
                try:
                    if time.monotonic() >= deadline:
                        break
                    notes = client.get_notes(content={'title': variant}, limit=10)
                    payload = _maybe_pick_best(title, notes)
                    if payload:
                        return payload
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"OpenReview v2 search failed: {e}")
            
        try:
            client_v1 = openreview.Client(baseurl='https://api.openreview.net')
            for variant in title_variants:
                if time.monotonic() >= deadline:
                    break
                for vid in venue_ids:
                    if time.monotonic() >= deadline:
                        break
                    try:
                        notes_v1 = client_v1.get_notes(content={'venueid': vid, 'title': variant}, limit=5)
                        payload = _maybe_pick_best(title, notes_v1)
                        if payload:
                            return payload
                    except Exception:
                        continue
                try:
                    if time.monotonic() >= deadline:
                        break
                    notes_v1 = client_v1.get_notes(content={'title': variant}, limit=10)
                    payload = _maybe_pick_best(title, notes_v1)
                    if payload:
                        return payload
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"OpenReview v1 search failed: {e}")
            
    except Exception as e:
        logger.error(f"OpenReview search error for {title}: {e}")

    if time.monotonic() >= deadline:
        logger.info("OpenReview search timed out for '%s'; falling back to HTML search only", title)
    return _search_openreview_html(title)
