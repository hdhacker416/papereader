import logging
import os
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

logger = logging.getLogger(__name__)

ARXIV_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
ARXIV_RETRY_SLEEP_SECONDS = 5
ARXIV_MAX_DOWNLOAD_ATTEMPTS = 4


@dataclass(frozen=True)
class PdfDownloadResult:
    ok: bool
    url: str
    final_url: str | None = None
    status_code: int | None = None
    error: str | None = None


def _normalize_pdf_url(url: str) -> str:
    normalized = url.strip()
    lower = normalized.lower()

    if "openreview.net" in lower:
        parts = urlsplit(normalized)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        note_id = query.get("id", "")
        if "/forum" in parts.path and note_id:
            return urlunsplit((parts.scheme, parts.netloc, "/pdf", urlencode({"id": note_id}), ""))
        if "/pdf" not in parts.path and note_id:
            return urlunsplit((parts.scheme, parts.netloc, "/pdf", urlencode({"id": note_id}), ""))

    if "arxiv.org" in lower:
        normalized = normalized.replace("arxiv.org", "export.arxiv.org")

    return normalized


def download_pdf_with_details(url: str, save_path: str) -> PdfDownloadResult:
    """
    Download PDF from URL to save_path.
    Returns structured success/failure details.
    """
    local_path = save_path
    original_url = url
    pdf_url = _normalize_pdf_url(url)

    if os.path.exists(local_path):
        try:
            with open(local_path, 'rb') as f:
                header = f.read(4)
                if header == b'%PDF':
                    logger.info(f"PDF already exists at {local_path}")
                    return PdfDownloadResult(ok=True, url=original_url, final_url=pdf_url)
                else:
                    logger.warning(f"Existing file {local_path} is not a valid PDF. Redownloading...")
        except Exception:
            pass

    directory = os.path.dirname(local_path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory)

    logger.info("Downloading PDF from %s to %s...", pdf_url, local_path)

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    last_error: str | None = None
    last_status_code: int | None = None
    last_response_url: str | None = None

    for attempt in range(1, ARXIV_MAX_DOWNLOAD_ATTEMPTS + 1):
        try:
            response = requests.get(pdf_url, headers=headers, stream=True, timeout=60, allow_redirects=True)
            last_status_code = response.status_code
            last_response_url = response.url

            if response.status_code in ARXIV_RETRY_STATUS_CODES and attempt < ARXIV_MAX_DOWNLOAD_ATTEMPTS:
                logger.warning(
                    "PDF download hit status %s for %s on attempt %s/%s. Sleeping %ss before retry.",
                    response.status_code,
                    pdf_url,
                    attempt,
                    ARXIV_MAX_DOWNLOAD_ATTEMPTS,
                    ARXIV_RETRY_SLEEP_SECONDS,
                )
                time.sleep(ARXIV_RETRY_SLEEP_SECONDS)
                continue

            response.raise_for_status()

            content_type = response.headers.get('Content-Type', '').lower()
            if 'text/html' in content_type:
                raise ValueError(
                    f"URL returned HTML instead of PDF. Content-Type: {content_type}. "
                    f"Requested={pdf_url}, Final={response.url}"
                )

            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            with open(local_path, 'rb') as f:
                if f.read(4) != b'%PDF':
                    raise ValueError(
                        f"Downloaded file is not a PDF (header check failed). Requested={pdf_url}, Final={response.url}"
                    )

            logger.info("Download completed.")
            return PdfDownloadResult(
                ok=True,
                url=original_url,
                final_url=response.url,
                status_code=response.status_code,
            )
        except Exception as e:
            last_error = str(e)
            logger.error("Failed to download PDF on attempt %s/%s: %s", attempt, ARXIV_MAX_DOWNLOAD_ATTEMPTS, e)
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except OSError:
                    pass
            if attempt >= ARXIV_MAX_DOWNLOAD_ATTEMPTS:
                break

    return PdfDownloadResult(
        ok=False,
        url=original_url,
        final_url=last_response_url or pdf_url,
        status_code=last_status_code,
        error=last_error or "Unknown PDF download error",
    )

def download_pdf(url: str, save_path: str) -> bool:
    return download_pdf_with_details(url, save_path).ok
