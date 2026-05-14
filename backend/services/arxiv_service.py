import difflib
import logging
import re
import threading
import time
from typing import Dict, Optional

import arxiv

logger = logging.getLogger(__name__)

TITLE_TOKEN_RE = re.compile(r"[a-z0-9]+")
MIN_ACCEPTABLE_TITLE_SCORE = 0.94
ARXIV_MIN_REQUEST_INTERVAL_SECONDS = 3.2

_arxiv_request_lock = threading.Lock()
_last_arxiv_request_at = 0.0


class ArxivTemporaryError(RuntimeError):
    """Raised when arXiv is reachable but temporarily refusing or timing out."""


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
    intersection = len(query_tokens & candidate_tokens)
    union = len(query_tokens | candidate_tokens) or 1
    jaccard = intersection / union
    coverage = intersection / max(len(query_tokens), 1)
    length_penalty = min(len(query_tokens), len(candidate_tokens)) / max(len(query_tokens), len(candidate_tokens), 1)
    ratio = difflib.SequenceMatcher(None, query, candidate).ratio()
    contains_score = coverage * length_penalty if query in candidate or candidate in query else 0.0
    return max(0.78 * ratio + 0.22 * jaccard, contains_score)


def _wait_for_arxiv_slot() -> None:
    global _last_arxiv_request_at
    with _arxiv_request_lock:
        now = time.monotonic()
        elapsed = now - _last_arxiv_request_at
        if elapsed < ARXIV_MIN_REQUEST_INTERVAL_SECONDS:
            time.sleep(ARXIV_MIN_REQUEST_INTERVAL_SECONDS - elapsed)
        _last_arxiv_request_at = time.monotonic()


def _is_temporary_arxiv_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "429" in text
        or "timed out" in text
        or "timeout" in text
        or "temporarily unavailable" in text
        or "502" in text
        or "503" in text
        or "504" in text
    )


def _result_payload(result: arxiv.Result) -> Dict:
    pdf_url = result.pdf_url
    source_url = pdf_url.replace("/pdf/", "/abs/")
    if source_url.endswith(".pdf"):
        source_url = source_url[:-4]
    return {
        "title": result.title,
        "authors": [a.name for a in result.authors],
        "abstract": result.summary.replace("\n", " "),
        "pdf_url": pdf_url,
        "source": "arxiv",
        "source_url": source_url,
        "published": result.published,
    }


def _iter_candidates(client: arxiv.Client, clean_title: str):
    searches = [
        arxiv.Search(
            query=f'ti:"{clean_title}"',
            max_results=3,
            sort_by=arxiv.SortCriterion.Relevance,
        ),
        arxiv.Search(
            query=clean_title,
            max_results=8,
            sort_by=arxiv.SortCriterion.Relevance,
        ),
    ]
    seen_ids: set[str] = set()
    for search in searches:
        try:
            _wait_for_arxiv_slot()
            for result in client.results(search):
                entry_id = getattr(result, "entry_id", None) or result.pdf_url
                if entry_id in seen_ids:
                    continue
                seen_ids.add(entry_id)
                yield result
        except Exception as exc:
            if _is_temporary_arxiv_error(exc):
                raise ArxivTemporaryError(f"arXiv API temporarily unavailable: {exc}") from exc
            logger.warning("Arxiv candidate query failed for %s: %s", clean_title, exc)

def search_arxiv(title: str) -> Optional[Dict]:
    """
    Search for a paper on Arxiv by title.
    Returns metadata dict if found, None otherwise.
    """
    client = arxiv.Client(
        page_size=8,
        delay_seconds=ARXIV_MIN_REQUEST_INTERVAL_SECONDS,
        num_retries=2
    )
    
    retries = 3
    while retries > 0:
        try:
            clean_title = title.replace("\n", " ").strip()
            best_result = None
            best_score = 0.0

            for result in _iter_candidates(client, clean_title):
                score = _title_score(clean_title, result.title)
                if score > best_score:
                    best_result = result
                    best_score = score
                if score >= 0.98:
                    break

            time.sleep(0.1)

            if best_result and best_score >= MIN_ACCEPTABLE_TITLE_SCORE:
                logger.info(
                    "Arxiv matched '%s' to '%s' with score %.3f",
                    title,
                    best_result.title,
                    best_score,
                )
                return _result_payload(best_result)

            if best_result:
                logger.info(
                    "Arxiv best candidate score too low for '%s': '%s' (%.3f)",
                    title,
                    best_result.title,
                    best_score,
                )
            return None
            
        except ArxivTemporaryError:
            raise
        except Exception as e:
            retries -= 1
            if retries > 0:
                time.sleep(2.0) # Error delay
            else:
                logger.error(f"Arxiv search failed after retries: {title} - {e}")
                pass
                
    return None
