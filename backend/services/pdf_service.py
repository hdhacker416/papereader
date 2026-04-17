import logging
import os
import time
import requests

logger = logging.getLogger(__name__)

ARXIV_RETRY_STATUS_CODES = {429}
ARXIV_RETRY_SLEEP_SECONDS = 5
ARXIV_MAX_DOWNLOAD_ATTEMPTS = 4

def download_pdf(url: str, save_path: str) -> bool:
    """
    Download PDF from URL to save_path.
    Returns True if successful, False otherwise.
    """
    local_path = save_path
    
    if os.path.exists(local_path):
        # Check if it's a valid PDF (simple check)
        try:
            with open(local_path, 'rb') as f:
                header = f.read(4)
                if header == b'%PDF':
                    logger.info(f"PDF already exists at {local_path}")
                    return True
                else:
                    logger.warning(f"Existing file {local_path} is not a valid PDF. Redownloading...")
        except Exception:
            pass
        
    # Ensure directory exists
    directory = os.path.dirname(local_path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory)
        
    logger.info(f"Downloading PDF from {url} to {local_path}...")
    
    # Optimize Arxiv URL to avoid reCAPTCHA and use export mirror
    pdf_url = url
    if "arxiv.org" in pdf_url:
        pdf_url = pdf_url.replace("arxiv.org", "export.arxiv.org")
        
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    for attempt in range(1, ARXIV_MAX_DOWNLOAD_ATTEMPTS + 1):
        try:
            response = requests.get(pdf_url, headers=headers, stream=True, timeout=60)
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

            # Verify Content-Type
            content_type = response.headers.get('Content-Type', '').lower()
            if 'text/html' in content_type:
                    raise ValueError(f"URL returned HTML instead of PDF. Content-Type: {content_type}")

            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Verify file header after download
            with open(local_path, 'rb') as f:
                if f.read(4) != b'%PDF':
                        raise ValueError("Downloaded file does not appear to be a PDF (Header check failed)")

            logger.info("Download completed.")
            return True
        except Exception as e:
            logger.error(f"Failed to download PDF on attempt {attempt}/{ARXIV_MAX_DOWNLOAD_ATTEMPTS}: {e}")
            # If download failed but created empty/incomplete file, remove it
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except OSError:
                    pass
            if attempt >= ARXIV_MAX_DOWNLOAD_ATTEMPTS:
                return False
    return False
