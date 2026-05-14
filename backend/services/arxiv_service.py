import difflib
import html
import logging
import re
import threading
import time
from typing import Dict, Optional
from urllib.parse import urlencode

import arxiv
import requests

logger = logging.getLogger(__name__)

TITLE_TOKEN_RE = re.compile(r"[a-z0-9]+")
MIN_ACCEPTABLE_TITLE_SCORE = 0.72
ARXIV_MIN_REQUEST_INTERVAL_SECONDS = 3.2
ARXIV_USER_AGENT = "PaperReader/1.0"
ARXIV_SEARCH_TIMEOUT_SECONDS = 25

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
    overlap = len(query_tokens & candidate_tokens) / max(len(query_tokens), 1)
    ratio = difflib.SequenceMatcher(None, query, candidate).ratio()
    contains = 1.0 if query in candidate or candidate in query else 0.0
    return max(ratio, 0.65 * ratio + 0.25 * overlap + 0.10 * contains)


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


def _strip_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(value).split())


def _html_result_payload(arxiv_id: str, title: str, abstract: str = "", authors: list[str] | None = None) -> Dict:
    clean_id = arxiv_id.strip().removesuffix(".pdf")
    return {
        "title": title,
        "authors": authors or [],
        "abstract": abstract,
        "pdf_url": f"https://arxiv.org/pdf/{clean_id}.pdf",
        "source": "arxiv",
        "source_url": f"https://arxiv.org/abs/{clean_id}",
        "published": None,
    }


def _search_arxiv_html(clean_title: str) -> Optional[Dict]:
    params = {
        "query": clean_title,
        "searchtype": "title",
        "abstracts": "show",
        "order": "-announced_date_first",
        "size": "25",
    }
    url = f"https://arxiv.org/search/?{urlencode(params)}"
    _wait_for_arxiv_slot()
    try:
        response = requests.get(
            url,
            headers={"User-Agent": ARXIV_USER_AGENT},
            timeout=ARXIV_SEARCH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        if _is_temporary_arxiv_error(exc):
            raise ArxivTemporaryError(f"arXiv HTML search temporarily unavailable: {exc}") from exc
        logger.warning("arXiv HTML search failed for %s: %s", clean_title, exc)
        return None

    best_payload: Dict | None = None
    best_score = 0.0
    for block in re.findall(r'<li class="arxiv-result">(.*?)</li>', response.text, flags=re.S):
        id_match = re.search(r'href="(?:https?://arxiv\.org)?/abs/([^"#?]+)"', block)
        if not id_match:
            continue
        title_match = re.search(r'<p class="title[^"]*">(.*?)</p>', block, flags=re.S)
        if not title_match:
            title_match = re.search(r'<p class="list-title[^"]*">.*?</span>(.*?)</p>', block, flags=re.S)
        if not title_match:
            continue

        candidate_title = _strip_html(title_match.group(1))
        score = _title_score(clean_title, candidate_title)
        if score <= best_score:
            continue

        abstract_match = re.search(r'<span class="abstract-full[^"]*">(.*?)</span>', block, flags=re.S)
        authors = [
            _strip_html(item)
            for item in re.findall(r'<p class="authors[^"]*">(.*?)</p>', block, flags=re.S)
        ]
        best_score = score
        best_payload = _html_result_payload(
            id_match.group(1),
            candidate_title,
            _strip_html(abstract_match.group(1)) if abstract_match else "",
            authors,
        )

    if best_payload and best_score >= MIN_ACCEPTABLE_TITLE_SCORE:
        logger.info(
            "arXiv HTML matched '%s' to '%s' with score %.3f",
            clean_title,
            best_payload["title"],
            best_score,
        )
        return best_payload
    if best_payload:
        logger.info(
            "arXiv HTML best candidate score too low for '%s': '%s' (%.3f)",
            clean_title,
            best_payload["title"],
            best_score,
        )
    return None


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
            temporary_error: ArxivTemporaryError | None = None

            try:
                for result in _iter_candidates(client, clean_title):
                    score = _title_score(clean_title, result.title)
                    if score > best_score:
                        best_result = result
                        best_score = score
                    if score >= 0.98:
                        break
            except ArxivTemporaryError as exc:
                temporary_error = exc

            time.sleep(0.1)

            if best_result and best_score >= MIN_ACCEPTABLE_TITLE_SCORE:
                logger.info(
                    "Arxiv matched '%s' to '%s' with score %.3f",
                    title,
                    best_result.title,
                    best_score,
                )
                return _result_payload(best_result)

            html_result = _search_arxiv_html(clean_title)
            if html_result:
                return html_result

            if temporary_error:
                raise temporary_error

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
