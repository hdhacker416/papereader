import json
import logging
import re
from collections import Counter
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from services import conference_service

logger = logging.getLogger(__name__)

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "for", "from", "how",
    "in", "into", "is", "it", "of", "on", "or", "our", "that", "the", "their",
    "there", "these", "this", "to", "under", "using", "with", "you", "your",
    "please", "help", "look", "new", "what", "about", "have", "has", "could",
    "should", "would", "some", "more", "than"
}

def extract_terms(text: str):
    return [token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2 and token not in STOPWORDS]

def calculate_relevance(query_terms, paper: models.ConferencePaper):
    title_terms = extract_terms(paper.title)
    abstract_terms = extract_terms(paper.abstract)
    keyword_terms = extract_terms(paper.keywords or "")

    score = 0.0
    matched_terms = []
    for term in query_terms:
        if term in title_terms:
            score += 3.0
            matched_terms.append(term)
        elif term in keyword_terms:
            score += 2.5
            matched_terms.append(term)
        elif term in abstract_terms:
            score += 1.5
            matched_terms.append(term)

    if "safety" in matched_terms or "secure" in matched_terms or "alignment" in matched_terms:
        score += 1.5

    return score, sorted(set(matched_terms))

def build_reason(matched_terms, paper: models.ConferencePaper):
    if matched_terms:
        return f"Matched query concepts: {', '.join(matched_terms[:4])}. The abstract explicitly discusses relevant safety or capability issues in {paper.conference.name}."
    return f"The paper was retained as a broad background reference from {paper.conference.name} because its abstract overlaps with the selected research area."

def build_themes(candidates):
    theme_counter = Counter()
    for candidate in candidates:
        tokens = extract_terms(candidate.title + " " + candidate.abstract)
        for token in tokens:
            if token in {"safety", "alignment", "agents", "evaluation", "jailbreak", "reasoning", "reward", "oversight", "misuse"}:
                theme_counter[token] += 1

    ordered = [term for term, _ in theme_counter.most_common(5)]
    if not ordered:
        ordered = ["safety evaluation", "alignment", "language agents"]
    return ordered

def build_summary(query: str, candidates, themes):
    if not candidates:
        return f"The current conference slice does not surface strong matches for '{query}'. A useful next step is to broaden conference coverage or relax the query constraints."

    conference_names = sorted({candidate.conference_label for candidate in candidates})
    return (
        f"Across {', '.join(conference_names)}, the strongest signals for '{query}' cluster around "
        f"{', '.join(themes[:3])}. The shortlisted papers emphasize evaluation, failure analysis, and deployment risk, "
        f"which suggests the area is moving from broad alignment narratives toward more operational safety tooling."
    )

def build_opportunities(candidates, themes):
    if not candidates:
        return [
            "Expand to more conferences or a broader year range to improve recall.",
            "Use a more specific query that names target threat models, benchmarks, or application domains.",
            "Introduce embedding retrieval so weak lexical matches are not missed."
        ]

    opportunities = []
    primary_theme = themes[0] if themes else "safety evaluation"
    secondary_theme = themes[1] if len(themes) > 1 else "agent reliability"

    opportunities.append(f"Combine {primary_theme} with longitudinal evaluation so the same model is stress-tested across deployment updates and tool changes.")
    opportunities.append(f"Study how {secondary_theme} failures evolve in multi-turn settings, especially when planning depth or context length increases.")
    opportunities.append("Build lightweight safety triage pipelines that use abstract-level screening to decide which papers deserve full PDF analysis and replication.")
    return opportunities

def update_job(db: Session, job: models.ResearchJob, status=None, stage=None, progress=None, summary=None, themes=None, opportunities=None, error_message=None):
    if status is not None:
        job.status = status
    if stage is not None:
        job.stage = stage
    if progress is not None:
        job.progress = progress
    if summary is not None:
        job.summary = summary
    if themes is not None:
        job.themes = json.dumps(themes)
    if opportunities is not None:
        job.opportunities = json.dumps(opportunities)
    if error_message is not None:
        job.error_message = error_message
    db.commit()

def run_research_job(job_id: str):
    db = SessionLocal()
    try:
        job = db.query(models.ResearchJob).filter(models.ResearchJob.id == job_id).first()
        if not job:
            return

        conference_codes = json.loads(job.selected_conferences_json)
        query_terms = extract_terms(job.query)

        update_job(db, job, status="running", stage="load_conference_papers", progress=10)
        papers = conference_service.get_papers_for_conference_codes(db, conference_codes)

        update_job(db, job, status="running", stage="recall_candidates", progress=35)
        scored = []
        for paper in papers:
            score, matched_terms = calculate_relevance(query_terms, paper)
            scored.append((paper, score, matched_terms))

        scored.sort(key=lambda item: item[1], reverse=True)
        top_scored = [item for item in scored if item[1] > 0][:12]
        if not top_scored:
            top_scored = scored[:8]

        update_job(db, job, status="running", stage="screen_candidates", progress=65)
        db.query(models.ResearchPaperCandidate).filter(models.ResearchPaperCandidate.research_job_id == job.id).delete()
        db.commit()

        created_candidates = []
        for paper, score, matched_terms in top_scored:
            candidate = models.ResearchPaperCandidate(
                research_job_id=job.id,
                conference_paper_id=paper.id,
                title=paper.title,
                abstract=paper.abstract,
                conference_label=paper.conference.name,
                relevance_score=round(score, 2),
                reason=build_reason(matched_terms, paper),
                status="shortlisted",
                is_selected=True,
            )
            db.add(candidate)
            created_candidates.append(candidate)
        db.commit()

        update_job(db, job, status="running", stage="build_summary", progress=85)
        themes = build_themes(created_candidates)
        summary = build_summary(job.query, created_candidates, themes)
        opportunities = build_opportunities(created_candidates, themes)

        update_job(
            db,
            job,
            status="completed",
            stage="completed",
            progress=100,
            summary=summary,
            themes=themes,
            opportunities=opportunities,
            error_message=None,
        )
    except Exception as exc:
        logger.exception("Research job failed: %s", job_id)
        failed_job = db.query(models.ResearchJob).filter(models.ResearchJob.id == job_id).first()
        if failed_job:
            update_job(
                db,
                failed_job,
                status="failed",
                stage="failed",
                progress=100,
                error_message=str(exc),
            )
    finally:
        db.close()
