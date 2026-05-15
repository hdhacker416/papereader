from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import schemas
from database import get_data_dir


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from community.figure_extractor import extract_figures  # noqa: E402
from community.persona_answer_experiment import (  # noqa: E402
    ROUTE_4,
    _download_pdf,
    _run_route_4,
    _safe_filename,
    _search_top_papers,
)


TOPICS = [
    {
        "id": "jailbreak-defense-tradeoff",
        "question": "对于大模型越狱攻击，最有效的防御思路是什么，如何在安全性和有用性之间取舍？",
        "description": "让安全、越狱和对齐相关论文分别回答同一个防御问题。",
        "tags": ["LLM Safety", "Jailbreak", "Alignment"],
    },
    {
        "id": "long-context-retrieval",
        "question": "长上下文模型真的能替代检索增强吗？什么时候应该用 RAG，什么时候应该直接塞长上下文？",
        "description": "围绕长上下文、检索、记忆和推理效率的论文回答。",
        "tags": ["RAG", "Long Context", "Retrieval"],
    },
    {
        "id": "agent-evaluation",
        "question": "评价一个 AI agent 到底应该看任务成功率、过程可解释性，还是安全边界？",
        "description": "让 agent benchmark、tool use 和安全评测论文展开争论。",
        "tags": ["Agents", "Evaluation", "Tool Use"],
    },
    {
        "id": "post-training",
        "question": "大模型后训练最关键的环节是什么：SFT、RLHF、DPO，还是数据筛选？",
        "description": "比较不同后训练路线对能力、对齐和泛化的影响。",
        "tags": ["Post-training", "RLHF", "DPO"],
    },
    {
        "id": "model-compression",
        "question": "如果想把大模型部署到更便宜的机器上，量化、蒸馏和剪枝哪个更值得优先做？",
        "description": "模型压缩、推理加速和部署相关论文的回答合集。",
        "tags": ["Compression", "Quantization", "Deployment"],
    },
]


def _clamp_int(value: int, *, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _community_dir() -> Path:
    path = Path(get_data_dir()) / "community"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _topic_cache_path(topic_id: str) -> Path:
    return _community_dir() / "topics" / f"{topic_id}.json"


def _topic_by_id(topic_id: str) -> dict:
    for topic in TOPICS:
        if topic["id"] == topic_id:
            return topic
    raise ValueError("topic not found")


def _topic_schema(topic: dict) -> schemas.CommunityTopic:
    cache_path = _topic_cache_path(topic["id"])
    answer_count = 0
    updated_at = None
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            answer_count = len(cached.get("results") or [])
            updated_at = cached.get("updated_at")
        except Exception:
            answer_count = 0
    return schemas.CommunityTopic(
        id=topic["id"],
        question=topic["question"],
        description=topic["description"],
        tags=list(topic["tags"]),
        cached=cache_path.exists(),
        answer_count=answer_count,
        updated_at=updated_at,
    )


def _figure_refs(manifest: dict | None, limit: int = 8) -> list[schemas.CommunityFigureRef]:
    if not manifest:
        return []
    refs: list[schemas.CommunityFigureRef] = []
    for item in (manifest.get("figures") or [])[:limit]:
        refs.append(
            schemas.CommunityFigureRef(
                id=str(item.get("id") or ""),
                page_number=int(item.get("page_number") or 0),
                label=str(item.get("label") or ""),
                caption=str(item.get("caption") or ""),
                confidence=float(item.get("confidence") or 0.0),
                warnings=[str(warning) for warning in (item.get("warnings") or [])],
            )
        )
    return refs


def generate_persona_answers(payload: schemas.CommunityAnswerRequest) -> schemas.CommunityAnswerResponse:
    started = time.time()
    query = payload.query.strip()
    if not query:
        raise ValueError("query cannot be empty")

    limit = _clamp_int(payload.limit, minimum=1, maximum=8)
    max_text_chars = _clamp_int(payload.max_text_chars, minimum=20_000, maximum=250_000)
    figure_max_pages = _clamp_int(payload.figure_max_pages, minimum=1, maximum=20)
    output_root = Path(get_data_dir()) / "community" / time.strftime("%Y%m%d_%H%M%S")
    figures_root = output_root / "figures"
    figures_root.mkdir(parents=True, exist_ok=True)

    results: list[schemas.CommunityPaperAnswer] = []
    papers = _search_top_papers(query, limit=limit)
    for item in papers:
        paper = item.paper
        base = {
            "rank": item.rank,
            "paper_id": str(paper.get("paper_id") or ""),
            "conference": str(paper.get("conference") or ""),
            "year": int(paper.get("year") or 0),
            "title": str(paper.get("title") or ""),
            "abstract": str(paper.get("abstract") or ""),
            "authors": [str(author) for author in (paper.get("authors") or [])],
            "source_url": str(paper.get("source_url") or ""),
            "rerank_score": item.rerank_score,
        }

        pdf_path, _, download_error = _download_pdf(paper)
        if download_error or not pdf_path:
            results.append(
                schemas.CommunityPaperAnswer(
                    **base,
                    local_pdf_path=pdf_path,
                    status="error",
                    error=download_error or "PDF download failed.",
                )
            )
            continue

        figure_manifest: dict | None = None
        try:
            figure_dir = figures_root / f"{item.rank:02d}_{_safe_filename(str(paper.get('paper_id') or paper.get('title')))}"
            extract_figures(
                pdf_path=Path(pdf_path),
                output_dir=figure_dir,
                dpi=110,
                max_pages=figure_max_pages,
            )
            manifest_path = figure_dir / "figures.json"
            if manifest_path.exists():
                figure_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            figure_manifest = {
                "figure_count": 0,
                "figures": [],
                "error": str(exc),
            }

        try:
            route_output = _run_route_4(
                query,
                paper,
                pdf_path,
                figure_manifest,
                max_text_chars,
            )
        except Exception as exc:
            route_output = {
                "status": "error",
                "error": str(exc),
            }
        results.append(
            schemas.CommunityPaperAnswer(
                **base,
                local_pdf_path=pdf_path,
                figure_count=int((figure_manifest or {}).get("figure_count") or 0),
                figures=_figure_refs(figure_manifest),
                answer=route_output.get("answer"),
                seconds=route_output.get("seconds"),
                status=str(route_output.get("status") or "ok"),
                error=route_output.get("error") or (figure_manifest or {}).get("error"),
            )
        )

    return schemas.CommunityAnswerResponse(
        query=query,
        route=ROUTE_4,
        elapsed_sec=round(time.time() - started, 2),
        results=results,
    )


def list_topics() -> schemas.CommunityFeedResponse:
    return schemas.CommunityFeedResponse(topics=[_topic_schema(topic) for topic in TOPICS])


def get_topic(topic_id: str) -> schemas.CommunityTopicResponse:
    topic = _topic_by_id(topic_id)
    cache_path = _topic_cache_path(topic_id)
    results: list[schemas.CommunityPaperAnswer] = []
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        results = [schemas.CommunityPaperAnswer(**item) for item in cached.get("results") or []]
    return schemas.CommunityTopicResponse(
        topic=_topic_schema(topic),
        route=ROUTE_4,
        results=results,
    )


def generate_topic(topic_id: str, payload: schemas.CommunityAnswerRequest | None = None) -> schemas.CommunityTopicResponse:
    topic = _topic_by_id(topic_id)
    request = schemas.CommunityAnswerRequest(
        query=topic["question"],
        limit=payload.limit if payload else 5,
        max_text_chars=payload.max_text_chars if payload else 120000,
        figure_max_pages=payload.figure_max_pages if payload else 12,
    )
    generated = generate_persona_answers(request)
    cache_path = _topic_cache_path(topic_id)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_payload = {
        "topic": topic,
        "route": generated.route,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "results": [item.model_dump() for item in generated.results],
    }
    cache_path.write_text(json.dumps(cache_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return get_topic(topic_id)
