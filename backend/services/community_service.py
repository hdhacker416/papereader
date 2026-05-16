from __future__ import annotations

import json
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from urllib.parse import quote

import schemas
from services import deepseek_service


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

SEED_TOPIC_DIR = ROOT_DIR / "community" / "seeded_topics"
SEED_FIGURE_DIR = ROOT_DIR / "community" / "seeded_figures"
COMMUNITY_PROCESS_CONCURRENCY = 5

from community.figure_extractor import extract_figures  # noqa: E402
from community.persona_answer_experiment import (  # noqa: E402
    ROUTE_4,
    _deepseek_text_figures_prompt,
    _download_pdf,
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
    path = ROOT_DIR / "data" / "community"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _topic_cache_path(topic_id: str) -> Path:
    return _community_dir() / "topics" / f"{topic_id}.json"


def _topic_seed_path(topic_id: str) -> Path:
    return SEED_TOPIC_DIR / f"{topic_id}.json"


def get_seeded_figure_path(topic_id: str, paper_id: str, figure_id: str) -> Path:
    base_dir = SEED_FIGURE_DIR.resolve()
    target = (base_dir / topic_id / paper_id / f"{figure_id}.png").resolve()
    if not str(target).startswith(str(base_dir)) or not target.is_file():
        raise FileNotFoundError("figure not found")
    return target


def get_community_asset_path(asset_path: str) -> Path:
    base_dir = _community_dir().resolve()
    target = (base_dir / asset_path).resolve()
    if not str(target).startswith(str(base_dir)) or not target.is_file() or target.suffix.lower() != ".png":
        raise FileNotFoundError("community asset not found")
    return target


def _load_topic_cache(topic_id: str) -> dict | None:
    for path in (_topic_cache_path(topic_id), _topic_seed_path(topic_id)):
        if not path.exists():
            continue
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _topic_has_cache(topic_id: str) -> bool:
    return _topic_cache_path(topic_id).exists() or _topic_seed_path(topic_id).exists()


def _topic_by_id(topic_id: str) -> dict:
    for topic in TOPICS:
        if topic["id"] == topic_id:
            return topic
    raise ValueError("topic not found")


def _topic_schema(topic: dict) -> schemas.CommunityTopic:
    answer_count = 0
    updated_at = None
    cached = None
    if _topic_has_cache(topic["id"]):
        try:
            cached = _load_topic_cache(topic["id"])
            answer_count = len(cached.get("results") or [])
            updated_at = cached.get("updated_at")
        except Exception:
            answer_count = 0
    return schemas.CommunityTopic(
        id=topic["id"],
        question=topic["question"],
        description=topic["description"],
        tags=list(topic["tags"]),
        cached=cached is not None,
        answer_count=answer_count,
        updated_at=updated_at,
    )


def _figure_refs(manifest: dict | None, limit: int = 8) -> list[schemas.CommunityFigureRef]:
    if not manifest:
        return []
    refs: list[schemas.CommunityFigureRef] = []
    output_dir = Path(str(manifest.get("output_dir") or "")) if manifest.get("output_dir") else None
    community_dir = _community_dir().resolve()
    for item in (manifest.get("figures") or [])[:limit]:
        image_url = None
        if output_dir and item.get("crop_path"):
            crop_path = (output_dir / str(item.get("crop_path"))).resolve()
            try:
                relative_path = crop_path.relative_to(community_dir)
                image_url = f"/community/assets/{quote(str(relative_path), safe='/')}"
            except ValueError:
                image_url = None
        refs.append(
            schemas.CommunityFigureRef(
                id=str(item.get("id") or ""),
                page_number=int(item.get("page_number") or 0),
                label=str(item.get("label") or ""),
                caption=str(item.get("caption") or ""),
                confidence=float(item.get("confidence") or 0.0),
                warnings=[str(warning) for warning in (item.get("warnings") or [])],
                image_url=image_url,
            )
        )
    return refs


def _parse_json_object(value: str) -> dict:
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        start = value.find("{")
        end = value.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(value[start : end + 1])
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
    return {}


def _judge_answerability(
    *,
    query: str,
    paper: dict,
    paper_text: str,
) -> tuple[str, str]:
    system = (
        "你是论文问答产品的内容筛选器。你只判断这篇论文能不能回答用户问题。"
        "必须严格基于提供的标题、摘要和论文文本。不要因为主题相近就判 yes。"
        "输出 JSON。"
    )
    user = (
        "请判断这篇论文能否作为一个拟人化答主回答用户问题。\n"
        "answerability 只能是 yes、partial、no：\n"
        "- yes: 论文直接研究这个问题，能给出具体立场和证据。\n"
        "- partial: 论文只回答问题中的一个重要侧面，但仍值得展示。\n"
        "- no: 论文只是关键词相近，不能实质回答，或者证据太弱。\n\n"
        "输出字段：answerability, reason。\n\n"
        f"用户问题：{query}\n"
        f"论文标题：{paper.get('title')}\n"
        f"摘要：{paper.get('abstract', '')}\n"
        "<paper_text_excerpt>\n"
        f"{paper_text[:30000]}\n"
        "</paper_text_excerpt>"
    )
    raw = deepseek_service.complete_json(
        model_name=deepseek_service.DEFAULT_DEEPSEEK_MODEL,
        system_instruction=system,
        user_content=user,
        max_tokens=700,
    )
    parsed = _parse_json_object(raw)
    answerability = str(parsed.get("answerability") or "no").strip().lower()
    if answerability not in {"yes", "partial", "no"}:
        answerability = "no"
    reason = str(parsed.get("reason") or "").strip()
    return answerability, reason


def _generate_answer_from_text(
    *,
    query: str,
    paper: dict,
    pdf_path: str,
    paper_text: str,
    figure_manifest: dict | None,
) -> dict:
    started = time.time()
    system, user = _deepseek_text_figures_prompt(query, paper, paper_text, figure_manifest)
    answer = deepseek_service.complete_text(
        model_name=deepseek_service.DEFAULT_DEEPSEEK_MODEL,
        system_instruction=system,
        user_content=user,
        max_tokens=1800,
    )
    return {
        "status": "ok",
        "answer": answer,
        "paper_text_chars": len(paper_text),
        "seconds": round(time.time() - started, 2),
        "pdf_path": pdf_path,
    }


def _candidate_base(item) -> dict:
    paper = item.paper
    return {
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


def _process_downloaded_candidate(
    *,
    item,
    base: dict,
    pdf_path: str,
    query: str,
    figures_root: Path,
    max_text_chars: int,
    figure_max_pages: int,
) -> schemas.CommunityPaperAnswer | None:
    paper = item.paper
    figure_manifest: dict | None = None
    figure_error: str | None = None
    try:
        paper_text = deepseek_service.extract_pdf_text(pdf_path, max_chars=max_text_chars)
        answerability, answerability_reason = _judge_answerability(
            query=query,
            paper=paper,
            paper_text=paper_text,
        )
        if answerability == "no":
            return None
    except Exception as exc:
        return schemas.CommunityPaperAnswer(
            **base,
            local_pdf_path=pdf_path,
            status="error",
            error=str(exc),
        )

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
        figure_error = str(exc)
        figure_manifest = {
            "figure_count": 0,
            "figures": [],
            "error": figure_error,
        }

    try:
        route_output = _generate_answer_from_text(
            query=query,
            paper=paper,
            pdf_path=pdf_path,
            paper_text=paper_text,
            figure_manifest=figure_manifest,
        )
    except Exception as exc:
        route_output = {
            "status": "error",
            "error": str(exc),
        }
        answerability = None
        answerability_reason = None

    return schemas.CommunityPaperAnswer(
        **base,
        local_pdf_path=pdf_path,
        figure_count=int((figure_manifest or {}).get("figure_count") or 0),
        figures=_figure_refs(figure_manifest),
        answerability=answerability,
        answerability_reason=answerability_reason,
        answer=route_output.get("answer"),
        seconds=route_output.get("seconds"),
        status=str(route_output.get("status") or "ok"),
        error=route_output.get("error") or figure_error,
    )


def _process_downloaded_candidates(
    *,
    downloaded_candidates: list[tuple[object, dict, str]],
    query: str,
    figures_root: Path,
    max_text_chars: int,
    figure_max_pages: int,
    limit: int,
) -> list[schemas.CommunityPaperAnswer]:
    if not downloaded_candidates:
        return []

    accepted: list[schemas.CommunityPaperAnswer] = []
    candidate_iter = iter(downloaded_candidates)
    max_workers = min(COMMUNITY_PROCESS_CONCURRENCY, len(downloaded_candidates))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        pending = {}

        def submit_next() -> bool:
            try:
                item, base, pdf_path = next(candidate_iter)
            except StopIteration:
                return False
            future = executor.submit(
                _process_downloaded_candidate,
                item=item,
                base=base,
                pdf_path=pdf_path,
                query=query,
                figures_root=figures_root,
                max_text_chars=max_text_chars,
                figure_max_pages=figure_max_pages,
            )
            pending[future] = (item, base, pdf_path)
            return True

        while len(pending) < max_workers and submit_next():
            pass

        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                pending_context = pending.pop(future, None)
                try:
                    result = future.result()
                except Exception as exc:
                    if not pending_context:
                        continue
                    _, base, pdf_path = pending_context
                    result = schemas.CommunityPaperAnswer(
                        **base,
                        local_pdf_path=pdf_path,
                        status="error",
                        error=str(exc),
                    )
                if result is not None:
                    accepted.append(result)

            if len(accepted) >= limit:
                continue

            while len(pending) < max_workers and len(accepted) < limit and submit_next():
                pass

    ordered = sorted(accepted, key=lambda answer: answer.rank)[:limit]
    for rank, answer in enumerate(ordered, start=1):
        answer.rank = rank
    return ordered


def generate_persona_answers(payload: schemas.CommunityAnswerRequest) -> schemas.CommunityAnswerResponse:
    started = time.time()
    query = payload.query.strip()
    if not query:
        raise ValueError("query cannot be empty")

    limit = _clamp_int(payload.limit, minimum=1, maximum=10)
    max_text_chars = _clamp_int(payload.max_text_chars, minimum=20_000, maximum=250_000)
    figure_max_pages = _clamp_int(payload.figure_max_pages, minimum=1, maximum=20)
    output_root = _community_dir() / "runs" / time.strftime("%Y%m%d_%H%M%S")
    figures_root = output_root / "figures"
    figures_root.mkdir(parents=True, exist_ok=True)

    downloaded_candidates: list[tuple[object, dict, str]] = []
    papers = _search_top_papers(query, limit=max(limit * 4, 30))
    for item in papers:
        paper = item.paper
        base = _candidate_base(item)

        pdf_path, _, download_error = _download_pdf(paper)
        if download_error or not pdf_path:
            continue
        downloaded_candidates.append((item, base, pdf_path))

    results = _process_downloaded_candidates(
        downloaded_candidates=downloaded_candidates,
        query=query,
        figures_root=figures_root,
        max_text_chars=max_text_chars,
        figure_max_pages=figure_max_pages,
        limit=limit,
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
    results: list[schemas.CommunityPaperAnswer] = []
    cached = _load_topic_cache(topic_id)
    if cached:
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
        limit=payload.limit if payload else 10,
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
