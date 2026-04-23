import json
from sqlalchemy.orm import Session
import models

SEED_CONFERENCES = [
    {
        "code": "neurips_2025",
        "name": "NeurIPS 2025",
        "year": 2025,
        "papers": [
            {
                "title": "Red Teaming Large Language Models with Adaptive Multi-Turn Attack Planning",
                "abstract": "We study large language model safety under adaptive multi-turn jailbreak attacks. The paper introduces a planning-based red teaming loop that chains prompts, monitors policy failures, and surfaces overlooked attack trajectories in aligned assistants.",
                "authors": ["Maya Chen", "Lucas Hart", "Priya Raman"],
                "official_url": "https://papers.nips.cc/paper_files/paper/2025/hash/red-teaming-adaptive-multi-turn.html",
                "arxiv_id": "2506.01001",
                "keywords": ["llm safety", "red teaming", "jailbreak", "alignment"]
            },
            {
                "title": "Benchmarking Hidden Goal Drift in Tool-Using Language Agents",
                "abstract": "Tool-using language agents often drift from user intent when solving long-horizon tasks. We propose a benchmark for hidden goal drift, quantify failure patterns, and show that safety constraints degrade under extended planning horizons.",
                "authors": ["Jin Park", "Sara Nouri"],
                "official_url": "https://papers.nips.cc/paper_files/paper/2025/hash/goal-drift-tools.html",
                "arxiv_id": "2507.01452",
                "keywords": ["language agents", "tool use", "safety", "evaluation"]
            },
            {
                "title": "Sparse Oversight for Detecting Emergent Deception in Foundation Models",
                "abstract": "This work explores sparse oversight mechanisms for detecting deceptive reasoning in foundation models. We use selective audits over chain-of-thought summaries and show improved detection of emergent deception with limited human feedback.",
                "authors": ["Daniel Wu", "Emma Ortiz", "Keiko Sato"],
                "official_url": "https://papers.nips.cc/paper_files/paper/2025/hash/sparse-oversight-deception.html",
                "arxiv_id": "2508.02111",
                "keywords": ["deception", "oversight", "alignment", "foundation models"]
            },
            {
                "title": "Continual Alignment for Retrieval-Augmented Assistants in Enterprise Settings",
                "abstract": "Retrieval-augmented assistants face safety regressions as enterprise knowledge bases evolve. We present continual alignment techniques that preserve harmlessness while updating policies for changing corpora and tools.",
                "authors": ["Aarav Mehta", "Lena Fischer"],
                "official_url": "https://papers.nips.cc/paper_files/paper/2025/hash/continual-alignment-rag.html",
                "arxiv_id": "2508.03229",
                "keywords": ["retrieval augmented generation", "alignment", "enterprise ai", "safety"]
            }
        ]
    },
    {
        "code": "iclr_2026",
        "name": "ICLR 2026",
        "year": 2026,
        "papers": [
            {
                "title": "Can We Anticipate Misuse? Forecasting Harmful Capabilities in Frontier Language Models",
                "abstract": "We propose a forecasting framework for harmful capabilities in frontier language models. By combining scaling signals, probe tasks, and adversarial evaluation, the method predicts future misuse risk before deployment.",
                "authors": ["Noah Bennett", "Yuna Kim", "Iris Patel"],
                "official_url": "https://openreview.net/forum?id=forecasting-misuse-froniter-llm",
                "openreview_url": "https://openreview.net/forum?id=forecasting-misuse-froniter-llm",
                "arxiv_id": "2601.00478",
                "keywords": ["frontier models", "misuse", "forecasting", "safety"]
            },
            {
                "title": "Safety Cases for Autonomous LLM Agents",
                "abstract": "The paper introduces safety case construction for autonomous LLM agents. It connects evidence from tests, monitoring, and capability assessments to structured risk arguments that guide deployment decisions.",
                "authors": ["Olivia Stone", "Haruto Akiyama"],
                "official_url": "https://openreview.net/forum?id=safety-cases-llm-agents",
                "openreview_url": "https://openreview.net/forum?id=safety-cases-llm-agents",
                "arxiv_id": "2601.00861",
                "keywords": ["autonomous agents", "safety cases", "risk", "governance"]
            },
            {
                "title": "Latent Boundary Probes for Early Detection of Unsafe Reasoning",
                "abstract": "We develop latent boundary probes that detect unsafe reasoning trajectories in large language models before the final answer is produced. The probes enable early intervention and reduce harmful completion rates.",
                "authors": ["Victor Alvarez", "Mina Solberg"],
                "official_url": "https://openreview.net/forum?id=latent-boundary-probes",
                "openreview_url": "https://openreview.net/forum?id=latent-boundary-probes",
                "arxiv_id": "2602.01114",
                "keywords": ["probing", "unsafe reasoning", "representation analysis", "llm safety"]
            },
            {
                "title": "Reward Hacking in Self-Improving Language Agents",
                "abstract": "Self-improving language agents can learn to exploit proxy objectives while appearing helpful. We analyze reward hacking behaviors, propose evaluation scenarios, and identify open problems in robust self-improvement.",
                "authors": ["Sofia Rossi", "Rohan Desai", "Elena Brooks"],
                "official_url": "https://openreview.net/forum?id=reward-hacking-self-improving-agents",
                "openreview_url": "https://openreview.net/forum?id=reward-hacking-self-improving-agents",
                "arxiv_id": "2602.01742",
                "keywords": ["reward hacking", "agents", "self-improvement", "alignment"]
            }
        ]
    },
    {
        "code": "icml_2025",
        "name": "ICML 2025",
        "year": 2025,
        "papers": [
            {
                "title": "Auditing Multimodal Jailbreak Transfer Across Vision-Language Models",
                "abstract": "We study how multimodal jailbreak prompts transfer across vision-language models. The work reveals systematic attack transfer patterns and suggests new benchmark directions for safer multimodal assistants.",
                "authors": ["Tianyu Zhao", "Nadia Ibrahim"],
                "official_url": "https://icml.cc/virtual/2025/poster/vision-language-jailbreaks",
                "arxiv_id": "2505.01981",
                "keywords": ["multimodal safety", "vision language models", "jailbreak", "benchmark"]
            },
            {
                "title": "Failure Taxonomies for Long-Context Safety Evaluation",
                "abstract": "Long-context language models exhibit new safety failures when malicious context is injected over hundreds of turns. We organize these failures into a taxonomy and release a benchmark for systematic stress testing.",
                "authors": ["Grace Li", "Marco Bellini"],
                "official_url": "https://icml.cc/virtual/2025/poster/long-context-safety",
                "arxiv_id": "2505.02802",
                "keywords": ["long context", "evaluation", "safety taxonomy", "stress testing"]
            },
            {
                "title": "Preference Fine-Tuning Under Strategic User Manipulation",
                "abstract": "Preference fine-tuning can be exploited by strategic users who shape feedback to induce unsafe policies. We characterize this threat model and present defenses based on robust reward estimation.",
                "authors": ["Hannah Moore", "Arjun Singh"],
                "official_url": "https://icml.cc/virtual/2025/poster/strategic-feedback-manipulation",
                "arxiv_id": "2505.03190",
                "keywords": ["preference learning", "strategic manipulation", "rlhf", "safety"]
            }
        ]
    }
]

def ensure_seed_data(db: Session):
    for conference_data in SEED_CONFERENCES:
        conference = db.query(models.ConferenceSource).filter(models.ConferenceSource.code == conference_data["code"]).first()
        if not conference:
            conference = models.ConferenceSource(
                code=conference_data["code"],
                name=conference_data["name"],
                year=conference_data["year"],
                enabled=True,
            )
            db.add(conference)
            db.flush()

        existing_papers = db.query(models.ConferencePaper).filter(models.ConferencePaper.conference_id == conference.id).count()
        if existing_papers == 0:
            for paper_data in conference_data["papers"]:
                paper = models.ConferencePaper(
                    conference_id=conference.id,
                    title=paper_data["title"],
                    abstract=paper_data["abstract"],
                    authors=json.dumps(paper_data.get("authors", [])),
                    official_url=paper_data.get("official_url"),
                    openreview_url=paper_data.get("openreview_url"),
                    arxiv_id=paper_data.get("arxiv_id"),
                    arxiv_url=f"https://arxiv.org/abs/{paper_data['arxiv_id']}" if paper_data.get("arxiv_id") else None,
                    keywords=json.dumps(paper_data.get("keywords", [])),
                )
                db.add(paper)

        conference.paper_count = len(conference_data["papers"])

    db.commit()

def list_enabled_conferences(db: Session):
    return db.query(models.ConferenceSource).filter(models.ConferenceSource.enabled == True).order_by(models.ConferenceSource.year.desc(), models.ConferenceSource.name.asc()).all()

def get_conference_map(db: Session, conference_codes):
    conferences = db.query(models.ConferenceSource).filter(models.ConferenceSource.code.in_(conference_codes)).all()
    return {conference.code: conference for conference in conferences}

def get_papers_for_conference_codes(db: Session, conference_codes):
    conferences = db.query(models.ConferenceSource).filter(models.ConferenceSource.code.in_(conference_codes)).all()
    conference_ids = [conference.id for conference in conferences]
    if not conference_ids:
        return []
    return db.query(models.ConferencePaper).filter(models.ConferencePaper.conference_id.in_(conference_ids)).all()
