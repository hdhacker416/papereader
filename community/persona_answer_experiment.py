from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from openai import OpenAI


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
for path in (ROOT_DIR, BACKEND_DIR):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from backend.services import deepseek_service, qwen_service, secret_service  # noqa: E402
from backend.services.pdf_service import download_pdf_with_details  # noqa: E402
from research.reader.paper_reader import PaperReader  # noqa: E402
from research.tools.search_tools import SearchTools  # noqa: E402

from community.figure_extractor import extract_figures  # noqa: E402


DEFAULT_QUESTION = "对于大模型越狱攻击，最有效的防御思路是什么，如何在安全性和有用性之间取舍？"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "community" / "output" / "persona_answer_experiment"
DEFAULT_CONFERENCES = ("iclr", "nips")
DEFAULT_YEARS = (2024, 2025, 2026)
ROUTE_1 = "1_qwen_evidence_deepseek_answer"
ROUTE_3 = "3_qwen_direct_answer"
ROUTE_4 = "4_deepseek_text_figures_answer"


@dataclass
class ExperimentPaper:
    rank: int
    paper: dict[str, Any]
    coarse_score: float | None
    rerank_score: float | None
    local_pdf_path: str | None = None
    resolved_source: dict[str, Any] | None = None
    download_error: str | None = None
    figure_manifest: dict[str, Any] | None = None
    route_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)


def _now_run_id() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _safe_filename(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value).strip("._")
    return cleaned or "paper"


def _question_prompt(question: str, title: str) -> str:
    return (
        "请把下面这篇论文拟人化成一个知乎答主来回答用户问题。\n"
        "要求：\n"
        "1. 必须用第一人称“我”来回答；这里的“我”指这篇论文本身，不是作者，也不是 AI 助手。\n"
        "2. 不要说“这篇论文认为”“本文认为”，而要说“我觉得”“我会这样处理”。\n"
        "3. 所有判断必须严格基于论文内容；不确定就明确说不确定。\n"
        "4. 如果论文只能回答问题的一部分，要直接承认边界。\n"
        "5. 尽量像知乎回答：先给观点，再解释证据和取舍，最后说局限。\n"
        "6. 如果有图表证据，请用类似“见 Figure 2”这样的方式自然引用。\n"
        "7. 中文输出，控制在 700 到 1000 字。\n\n"
        f"用户问题：{question}\n"
        f"你要扮演的论文：{title}"
    )


def _qwen_evidence_prompt(question: str, paper: dict[str, Any]) -> str:
    return (
        "你只做证据提取，不写最终回答。请严格基于上传的 PDF，围绕用户问题提取一个 evidence pack。\n"
        "输出中文 Markdown，结构固定为：\n"
        "## answerability\n"
        "回答 yes / partial / no，并说明原因。\n"
        "## stance\n"
        "这篇论文对问题能支持的核心立场。\n"
        "## evidence\n"
        "列出 5-8 条证据，每条尽量包含页码、章节、实验、表格或 Figure 编号。\n"
        "## safety_utility_tradeoff\n"
        "专门总结安全性与有用性之间的取舍。\n"
        "## figures\n"
        "列出和问题最相关的图表编号与它们说明了什么。\n"
        "## limitations\n"
        "列出这篇论文不能回答或证据不足的地方。\n\n"
        f"用户问题：{question}\n"
        f"论文标题：{paper.get('title')}\n"
        f"摘要：{paper.get('abstract', '')}"
    )


def _deepseek_from_evidence_prompt(question: str, paper: dict[str, Any], evidence: str) -> tuple[str, str]:
    system = (
        "你是一个学术问答写手，但当前要把一篇论文拟人化。"
        "你必须只基于用户提供的 evidence pack 写回答，不要补充 evidence pack 之外的事实。"
    )
    user = (
        f"{_question_prompt(question, str(paper.get('title') or ''))}\n\n"
        "<evidence_pack>\n"
        f"{evidence}\n"
        "</evidence_pack>"
    )
    return system, user


def _figure_manifest_for_prompt(manifest: dict[str, Any] | None, max_figures: int = 8) -> str:
    if not manifest:
        return "[]"
    figures = []
    for item in manifest.get("figures", [])[:max_figures]:
        figures.append(
            {
                "id": item.get("id"),
                "page_number": item.get("page_number"),
                "label": item.get("label"),
                "caption": item.get("caption"),
                "crop_path": item.get("crop_path"),
                "confidence": item.get("confidence"),
                "warnings": item.get("warnings", []),
            }
        )
    return json.dumps(figures, ensure_ascii=False, indent=2)


def _deepseek_text_figures_prompt(
    question: str,
    paper: dict[str, Any],
    paper_text: str,
    figure_manifest: dict[str, Any] | None,
) -> tuple[str, str]:
    system = (
        "你要把一篇论文拟人化成知乎答主。"
        "你必须严格基于提供的 PDF 文本和 figure manifest 回答，不要编造。"
        "figure manifest 只包含图注和裁剪图路径；如果图注不足以支持某个视觉结论，就不要硬说。"
    )
    user = (
        f"{_question_prompt(question, str(paper.get('title') or ''))}\n\n"
        "<paper_metadata>\n"
        f"title: {paper.get('title')}\n"
        f"conference: {paper.get('conference')} {paper.get('year')}\n"
        f"abstract: {paper.get('abstract', '')}\n"
        "</paper_metadata>\n\n"
        "<figure_manifest>\n"
        f"{_figure_manifest_for_prompt(figure_manifest)}\n"
        "</figure_manifest>\n\n"
        "<paper_text>\n"
        f"{paper_text}\n"
        "</paper_text>"
    )
    return system, user


def _download_pdf(paper: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None, str | None]:
    reader = PaperReader(model_name="qwen-long")
    resolved = reader.resolve_source(paper)
    if resolved is None:
        return None, None, "No OpenReview/arXiv source found."

    pdf_path = reader._pdf_path_for_paper(paper)
    result = download_pdf_with_details(resolved.pdf_url, str(pdf_path))
    if not result.ok:
        return (
            str(pdf_path),
            asdict(resolved),
            f"Failed to download PDF: status={result.status_code or '-'} error={result.error or '-'} final={result.final_url or '-'}",
        )
    return str(pdf_path), asdict(resolved), None


def _qwen_chat_with_paper_upload_timeout(
    *,
    pdf_path: str,
    message: str,
    model_name: str,
    upload_timeout: float,
) -> tuple[str, dict[str, Any], float, float]:
    api_key = secret_service.get_secret("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("DASHSCOPE_API_KEY is not configured")
    client = OpenAI(
        api_key=api_key,
        base_url=qwen_service.DEFAULT_DASHSCOPE_BASE_URL,
        timeout=upload_timeout,
    )
    file_id = qwen_service._upload_file_for_extract(client, pdf_path)
    try:
        qwen_service._wait_until_file_processed(client, file_id)
        return qwen_service._chat_with_uploaded_file(
            client=client,
            file_id=file_id,
            history={},
            message=message,
            model_name=model_name,
        )
    finally:
        qwen_service._delete_uploaded_file(client, file_id)


def _search_top_papers(question: str, limit: int) -> list[ExperimentPaper]:
    tools = SearchTools()
    coarse = tools.coarse_search(
        question,
        conferences=DEFAULT_CONFERENCES,
        years=DEFAULT_YEARS,
        top_k_per_asset=15,
        top_k_global=max(30, limit * 4),
    )
    reranked = tools.rerank_search(question, coarse["results"], top_n=limit)
    results: list[ExperimentPaper] = []
    for index, item in enumerate(reranked["results"], start=1):
        results.append(
            ExperimentPaper(
                rank=index,
                paper=item["paper"],
                coarse_score=item.get("coarse_score"),
                rerank_score=item.get("rerank_score"),
            )
        )
    return results


def _run_route_1(question: str, paper: dict[str, Any], pdf_path: str, qwen_upload_timeout: float) -> dict[str, Any]:
    started = time.time()
    evidence, _, _, evidence_seconds = _qwen_chat_with_paper_upload_timeout(
        pdf_path=pdf_path,
        message=_qwen_evidence_prompt(question, paper),
        model_name="qwen-long",
        upload_timeout=qwen_upload_timeout,
    )
    system, user = _deepseek_from_evidence_prompt(question, paper, evidence)
    answer = deepseek_service.complete_text(
        model_name=deepseek_service.DEFAULT_DEEPSEEK_MODEL,
        system_instruction=system,
        user_content=user,
        max_tokens=1800,
    )
    return {
        "status": "ok",
        "qwen_evidence": evidence,
        "answer": answer,
        "seconds": round(time.time() - started, 2),
        "qwen_evidence_seconds": round(evidence_seconds, 2),
    }


def _run_route_3(question: str, paper: dict[str, Any], pdf_path: str, qwen_upload_timeout: float) -> dict[str, Any]:
    started = time.time()
    answer, _, _, qwen_seconds = _qwen_chat_with_paper_upload_timeout(
        pdf_path=pdf_path,
        message=_question_prompt(question, str(paper.get("title") or "")),
        model_name="qwen-long",
        upload_timeout=qwen_upload_timeout,
    )
    return {
        "status": "ok",
        "answer": answer,
        "seconds": round(time.time() - started, 2),
        "qwen_seconds": round(qwen_seconds, 2),
    }


def _run_route_4(
    question: str,
    paper: dict[str, Any],
    pdf_path: str,
    figure_manifest: dict[str, Any] | None,
    max_text_chars: int,
) -> dict[str, Any]:
    started = time.time()
    paper_text = deepseek_service.extract_pdf_text(pdf_path, max_chars=max_text_chars)
    system, user = _deepseek_text_figures_prompt(question, paper, paper_text, figure_manifest)
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
    }


def _run_with_error_capture(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
        }


def _write_partial(output_dir: Path, question: str, papers: list[ExperimentPaper]) -> None:
    (output_dir / "partial_results.json").write_text(
        json.dumps(
            {
                "question": question,
                "papers": [asdict(paper_item) for paper_item in papers],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_markdown_report(question: str, papers: list[ExperimentPaper], output_path: Path, routes: list[str]) -> None:
    route_descriptions = {
        ROUTE_1: "Qwen reads PDF into evidence pack, DeepSeek writes persona answer.",
        ROUTE_3: "Qwen directly reads PDF and writes persona answer.",
        ROUTE_4: "Local text + extracted figure captions, DeepSeek writes persona answer.",
    }
    lines = [
        "# Persona Answer Experiment",
        "",
        f"Question: {question}",
        "",
        "Routes:",
        *(f"- `{route}`: {route_descriptions[route]}" for route in routes),
        "",
        "## Search Top 5",
        "",
    ]
    for item in papers:
        paper = item.paper
        lines.append(
            f"{item.rank}. **{paper.get('title')}** ({paper.get('conference')} {paper.get('year')}, "
            f"rerank={item.rerank_score:.4f}): {paper.get('source_url')}"
        )
    for item in papers:
        paper = item.paper
        lines.extend(
            [
                "",
                f"## {item.rank}. {paper.get('title')}",
                "",
                f"- PDF: `{item.local_pdf_path or '-'}`",
                f"- Download error: `{item.download_error or '-'}`",
                f"- Figures extracted: `{(item.figure_manifest or {}).get('figure_count', 0)}`",
            ]
        )
        for route in routes:
            output = item.route_outputs.get(route) or {}
            lines.extend(["", f"### {route}", ""])
            if output.get("status") != "ok":
                lines.append(f"ERROR: {output.get('error', 'not run')}")
                continue
            if route == ROUTE_1:
                lines.extend(["#### Qwen Evidence", "", output.get("qwen_evidence", "").strip(), ""])
            lines.append(output.get("answer", "").strip())
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def run_experiment(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir / _now_run_id()
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_root = output_dir / "figures"
    question = args.question
    routes = [ROUTE_4]
    if args.include_qwen_baselines:
        routes.extend([ROUTE_1, ROUTE_3])

    papers = _search_top_papers(question, limit=args.limit)
    for item in papers:
        paper = item.paper
        print(f"[paper {item.rank}/{len(papers)}] {paper.get('title')}", flush=True)
        print("  - downloading PDF", flush=True)
        pdf_path, resolved_source, download_error = _download_pdf(paper)
        item.local_pdf_path = pdf_path
        item.resolved_source = resolved_source
        item.download_error = download_error
        if download_error or not pdf_path:
            print(f"  - download failed: {download_error}", flush=True)
            _write_partial(output_dir, question, papers)
            continue

        print("  - extracting figures", flush=True)
        figure_output_dir = figures_root / f"{item.rank:02d}_{_safe_filename(str(paper.get('paper_id') or paper.get('title')))}"
        figures = extract_figures(
            pdf_path=Path(pdf_path),
            output_dir=figure_output_dir,
            dpi=args.figure_dpi,
            max_pages=args.figure_max_pages,
        )
        manifest_path = figure_output_dir / "figures.json"
        item.figure_manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {
            "figure_count": len(figures),
            "figures": [],
        }
        print(f"  - extracted {(item.figure_manifest or {}).get('figure_count', 0)} figures", flush=True)

        print(f"  - running {ROUTE_4}", flush=True)
        item.route_outputs[ROUTE_4] = _run_with_error_capture(
            _run_route_4,
            question,
            paper,
            pdf_path,
            item.figure_manifest,
            args.max_text_chars,
        )
        _write_partial(output_dir, question, papers)

        if args.include_qwen_baselines:
            print(f"  - running {ROUTE_1}", flush=True)
            item.route_outputs[ROUTE_1] = _run_with_error_capture(
                _run_route_1,
                question,
                paper,
                pdf_path,
                args.qwen_upload_timeout,
            )
            _write_partial(output_dir, question, papers)

            print(f"  - running {ROUTE_3}", flush=True)
            item.route_outputs[ROUTE_3] = _run_with_error_capture(
                _run_route_3,
                question,
                paper,
                pdf_path,
                args.qwen_upload_timeout,
            )
            _write_partial(output_dir, question, papers)

    payload = {
        "question": question,
        "routes": routes,
        "output_dir": str(output_dir),
        "papers": [asdict(item) for item in papers],
    }
    (output_dir / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown_report(question, papers, output_dir / "report.md", routes)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run persona answer A/B experiment for the community feature.")
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-text-chars", type=int, default=120_000)
    parser.add_argument("--figure-dpi", type=int, default=110)
    parser.add_argument("--figure-max-pages", type=int, default=12)
    parser.add_argument("--qwen-upload-timeout", type=float, default=90.0)
    parser.add_argument(
        "--include-qwen-baselines",
        action="store_true",
        help="Also run the slower Qwen PDF-upload baselines for comparison.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = run_experiment(args)
    print(f"Wrote experiment output to {result['output_dir']}")


if __name__ == "__main__":
    main()
