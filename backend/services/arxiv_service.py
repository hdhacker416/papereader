import logging
import re
import time
from typing import Dict, Optional, List
import arxiv

logger = logging.getLogger(__name__)

def search_arxiv(title: str) -> Optional[Dict]:
    """
    Search for a paper on Arxiv by title.
    Returns metadata dict if found, None otherwise.
    """
    # Create client with retries configuration
    # Note: arxiv.Client is available in newer versions of arxiv library (2.0+)
    client = arxiv.Client(
        page_size=1,
        delay_seconds=0.1,
        num_retries=1
    )
    
    retries = 3
    while retries > 0:
        try:
            # Clean title: remove newlines, extra spaces
            clean_title = title.replace("\n", " ").strip()
            # Search by title explicitly using ti: prefix
            search_query = f'ti:"{clean_title}"'
            
            search = arxiv.Search(
                query=search_query,
                max_results=1,
                sort_by=arxiv.SortCriterion.Relevance
            )
            
            # Execute search
            results = list(client.results(search))
            time.sleep(0.1) # Normal delay to be nice to API
            
            if not results:
                return None
                
            result = results[0]
            
            # Simple title matching verification
            # Normalize strings for comparison (lowercase, alphanumeric only)
            def simplify(s):
                return re.sub(r'[^a-zA-Z0-9]', '', s.lower())
                
            if simplify(result.title) == simplify(title):
                pdf_url = result.pdf_url
                # Construct abstract/source URL from PDF URL
                # Arxiv PDF URLs are like https://arxiv.org/pdf/2312.12345.pdf
                # Abstract URLs are like https://arxiv.org/abs/2312.12345
                source_url = pdf_url.replace("/pdf/", "/abs/")
                if source_url.endswith(".pdf"):
                    source_url = source_url[:-4]
                
                return {
                    "title": result.title, # Use official title from Arxiv
                    "authors": [a.name for a in result.authors],
                    "abstract": result.summary.replace("\n", " "),
                    "pdf_url": pdf_url,
                    "source": "arxiv",
                    "source_url": source_url,
                    "published": result.published
                }
            
            logger.info(f"Arxiv search result title mismatch: '{result.title}' != '{title}'")
            return None # Title mismatch
            
        except Exception as e:
            retries -= 1
            if retries > 0:
                time.sleep(2.0) # Error delay
            else:
                logger.error(f"Arxiv search failed after retries: {title} - {e}")
                pass
                
    return None
