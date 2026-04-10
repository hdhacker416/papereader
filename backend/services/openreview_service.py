import logging
import datetime
from typing import Dict, List, Optional
try:
    import openreview
except ImportError:
    openreview = None

logger = logging.getLogger(__name__)

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
    # Clean title
    clean_title = title.replace("\n", " ").strip()
    
    venue_ids = []
    # Default search strategy: ICLR, NeurIPS, ICML, 2023-Present (Descending)
    current_year = datetime.datetime.now().year
    target_years = range(current_year, 2022, -1) # e.g. 2025, 2024, 2023
    target_confs = ['iclr', 'neurips', 'icml']
    
    for y in target_years:
        for conf in target_confs:
            venue_ids.extend(get_openreview_venue_ids(conf, str(y)))
            
    found_note = None
    pdf_url = ""
    abstract = ""

    if openreview is None:
        logger.warning("OpenReview dependency is not installed; skipping OpenReview search.")
        return None
    
    try:
        # Try v2 first
        try:
            client = openreview.api.OpenReviewClient(baseurl='https://api2.openreview.net')
            
            # If we have venue_ids, iterate and search
            if venue_ids:
                for vid in venue_ids:
                    try:
                        notes = client.get_notes(content={'venueid': vid, 'title': clean_title}, limit=1)
                        if notes:
                            found_note = notes[0]
                            pdf_url = f"https://openreview.net/pdf?id={found_note.id}"
                            abstract = found_note.content.get('abstract', {}).get('value', '')
                            break
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"OpenReview v2 search failed: {e}")
            pass
            
        if not found_note:
            # Try v1
            try:
                client_v1 = openreview.Client(baseurl='https://api.openreview.net')
                
                # Try with venue_ids first
                if venue_ids:
                    for vid in venue_ids:
                        try:
                            notes_v1 = client_v1.get_notes(content={'venueid': vid, 'title': clean_title}, limit=1)
                            if notes_v1:
                                found_note = notes_v1[0]
                                pdf_url = f"https://openreview.net/pdf?id={found_note.id}"
                                abstract = found_note.content.get('abstract', '')
                                break
                        except Exception:
                            continue
            except Exception as e:
                 logger.debug(f"OpenReview v1 search failed: {e}")
                 pass
                 
        if found_note:
            return {
                "title": title,
                "authors": [], # OpenReview authors are a bit complex to extract reliably across v1/v2 without more code
                "abstract": abstract,
                "pdf_url": pdf_url,
                "source": "openreview",
                "source_url": pdf_url.replace("/pdf?", "/forum?"),
                "published": None
            }
            
    except Exception as e:
        logger.error(f"OpenReview search error for {title}: {e}")
        
    return None
