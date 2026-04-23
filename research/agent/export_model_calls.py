from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from research.agent import bounded as bounded_mod


BRIEF_SYSTEM_PROMPT = (
    "You are designing a bounded academic research workflow for paper search. "
    "Return compact JSON only. "
    "If the user explicitly asks for breadth, set breadth_mode to 'broad' and make sure the search axes cover both the narrow topic and the broader topic. "
    "initial_queries must be short retrieval-oriented queries. "
    "reading_prompts must be three prompts for full-paper reading. "
    "The third reading prompt should explicitly connect the paper back to the user's question."
)

SELECTION_SYSTEM_PROMPT = (
    "You are controlling a bounded deep-research agent. "
    "Choose which papers deserve full reading. "
    "Respect the user's desired breadth. "
    "If breadth_mode is 'broad', avoid selecting only one narrow subtopic when broader post-training coverage is available. "
    "Use continue_search only when important axes are still missing and there are search rounds left. "
    "Never reference papers that are not in the candidate list."
)

EVIDENCE_PACK_SCHEMA_DOCS: dict[str, str] = {
    "evidence_cards": "逐篇全文精读后抽取出的高置信度证据卡。",
    "weak_signal_summary": "只基于检索结果、尚未全文精读的弱信号总结。",
    "cross_paper_observations": "跨论文的初步共性观察。",
    "evidence_gaps": "当前证据不足、仍未验证清楚的点。",
}

EVIDENCE_CARD_SCHEMA_DOCS: dict[str, str] = {
    "conference": "论文会议代码。",
    "year": "论文年份。",
    "paper_id": "论文唯一标识。",
    "title": "论文标题。",
    "primary_direction": "这篇论文最主要归属的研究方向。",
    "primary_type": "论文类型，例如 attack、defense、alignment 等。",
    "training_stage": "论文主要作用在哪个后训练阶段或技术环节。",
    "selection_reason": "这篇论文为什么被纳入精读。",
    "problem": "论文试图解决的核心问题。",
    "method": "核心方法或技术路线。",
    "method_novelty": "方法的新意在哪里，和已有路线相比的独特贡献是什么。",
    "evaluation_strength": "证据强度如何，实验或分析到底有多能支撑结论。",
    "deployment_relevance": "这篇论文对真实后训练流程或部署场景的相关性有多强。",
    "key_findings": "关键发现列表。",
    "strongest_evidence": "最能支撑论文结论的实验或分析证据。",
    "limitations": "论文的主要局限。",
    "relevance_to_query": "它和用户问题的直接关系。",
    "confidence": "这张证据卡的置信度等级。",
}

REPORT_OUTLINE_SCHEMA_DOCS: dict[str, str] = {
    "title": "报告标题。",
    "executive_summary_claims": "执行摘要里的核心结论清单，每条都要绑定证据。",
    "directions": "报告准备展开的主要研究方向。",
    "paper_analysis_order": "详细逐篇分析的顺序。",
    "synthesis_points": "跨论文综合比较时要重点覆盖的点。",
    "evidence_gaps": "报告里必须明确交代的证据缺口。",
    "suggested_reading_order": "给用户的推荐阅读顺序。",
    "open_questions": "报告最后要提出的开放问题。",
}

REPORT_OUTLINE_DIRECTION_DOCS: dict[str, str] = {
    "name": "方向名称。",
    "importance": "为什么这个方向值得关注。",
    "supporting_paper_ids": "支撑这个方向的论文 id。当前 schema 要求至少 2 篇。",
    "maturity": "这个方向当前成熟度。",
    "evidence_strength": "当前证据强弱。",
    "comparison_points": "这个方向与其它方向比较时的重点。",
}

BRIEF_SCHEMA_DOCS: dict[str, str] = {
    "research_goal": "这次 research 的总体目标，用一句话概括系统到底要找什么。",
    "breadth_mode": "搜索范围模式。`focused` 表示窄而深，`broad` 表示要主动覆盖更宽的相关方向。",
    "search_axes": "模型认为应该分别覆盖的研究维度或子方向。",
    "initial_queries": "第一轮真正发给检索系统的短 query 列表。",
    "rerank_query": "精排时使用的统一排序标准，通常比 coarse query 更像一个综合判断口径。",
    "reading_prompts": "给单篇论文精读时使用的 3 条固定 prompt。",
    "target_conferences": "模型建议优先搜索的会议集合。空列表表示不主动限制会议。",
    "target_years": "模型建议优先搜索的年份集合。空列表表示不主动限制年份。",
}

SELECTION_SCHEMA_DOCS: dict[str, str] = {
    "continue_search": "这一轮筛选后，模型是否认为还值得继续下一轮搜索。",
    "rationale": "模型对当前筛选决策的总体解释。",
    "additional_queries": "如果要继续搜索，下一轮建议补搜的 query。",
    "missing_axes": "模型判断目前仍然覆盖不足的研究方向。",
    "selected_papers": "模型认为应该进入全文精读池的论文列表。",
}

SELECTED_PAPER_SCHEMA_DOCS: dict[str, str] = {
    "conference": "论文所属会议代码。",
    "year": "论文年份。",
    "paper_id": "语料里的唯一论文标识，用于回查详情和 PDF。",
    "axis": "模型认为这篇论文代表的研究方向。",
    "reason": "为什么要选这篇论文进入精读。",
    "priority": "模型给的精读优先级，数值越小越优先。",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export bounded-agent model calls with schema docs.")
    parser.add_argument(
        "--report",
        default="data/research/runtime/reports/test_post_training_query_bounded.json",
        help="Path to a bounded-agent run report JSON.",
    )
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_reading_cache(report: dict[str, Any], paper: dict[str, Any]) -> Path | None:
    conference = paper["conference"]
    year = paper["year"]
    paper_id = paper["paper_id"]
    reading_root = Path("data/research/runtime/readings")
    for path in sorted(reading_root.glob(f"{conference}/{year}/prompt_*/*.json")):
        if path.stem == paper_id:
            return path
    return None


def _extract_turn_text(parts: list[dict[str, Any]]) -> str:
    texts: list[str] = []
    for part in parts:
        if "text" in part:
            texts.append(part["text"])
    return "".join(texts)


def _collect_model_calls(report: dict[str, Any], report_path: Path) -> dict[str, Any]:
    searched_queries: list[str] = []
    selection_calls: list[dict[str, Any]] = []
    for round_item in report.get("rounds", []):
        queried = list(round_item["queries"])
        searched_queries.extend(query for query in queried if query not in searched_queries)
        selection_calls.append(
            {
                "round_index": round_item["round_index"],
                "system_instruction": SELECTION_SYSTEM_PROMPT,
                "response_json_schema": bounded_mod.SELECTION_SCHEMA,
                "schema_docs": {
                    "top_level": SELECTION_SCHEMA_DOCS,
                    "selected_papers_item": SELECTED_PAPER_SCHEMA_DOCS,
                },
                "input_payload": {
                    "user_query": report["query"],
                    "brief": {
                        "research_goal": report["brief"]["research_goal"],
                        "breadth_mode": report["brief"]["breadth_mode"],
                        "search_axes": report["brief"]["search_axes"],
                        "rerank_query": report["brief"]["rerank_query"],
                    },
                    "round_index": round_item["round_index"],
                    "queries_this_round": queried,
                    "searched_queries": list(searched_queries),
                    "remaining_search_rounds": max(0, len(report.get("rounds", [])) - round_item["round_index"]),
                    "max_full_reads": 5,
                    "already_selected": [],
                    "candidate_papers": [
                        {
                            "conference": c["paper"]["conference"],
                            "year": c["paper"]["year"],
                            "paper_id": c["paper"]["paper_id"],
                            "title": c["paper"]["title"],
                            "abstract": c["paper"]["abstract"],
                            "rerank_score": c["rerank_score"],
                            "coarse_score": c["coarse_score"],
                        }
                        for c in round_item["reranked_results"][:20]
                    ],
                },
                "output": round_item["decision"],
            }
        )

    paper_reading_calls: list[dict[str, Any]] = []
    for reading_result in report.get("reading_results", []):
        cache_path = _find_reading_cache(report, reading_result["paper"])
        if cache_path is None:
            continue
        cache = _read_json(cache_path)
        turns = []
        for idx, turn in enumerate(cache.get("reading_turns", []), start=1):
            turns.append(
                {
                    "turn_index": idx,
                    "prompt": _extract_turn_text(turn.get("user", {}).get("parts", [])),
                    "response": _extract_turn_text(turn.get("model", {}).get("parts", [])),
                    "meta": turn.get("meta", {}),
                }
            )
        paper_reading_calls.append(
            {
                "paper": cache.get("paper"),
                "prompt_cache_key": cache.get("prompt_cache_key"),
                "prompts": cache.get("prompts"),
                "cache_path": str(cache_path),
                "response_json_schema": None,
                "schema_docs": None,
                "turns": turns,
            }
        )

    summary_payload = {
        "user_query": report["query"],
        "brief": {
            "research_goal": report["brief"]["research_goal"],
            "breadth_mode": report["brief"]["breadth_mode"],
            "search_axes": report["brief"]["search_axes"],
            "initial_queries": report["brief"]["initial_queries"],
            "rerank_query": report["brief"]["rerank_query"],
        },
        "rounds": report.get("rounds", []),
        "selected_papers": report.get("selected_papers", []),
        "detail_results": report.get("detail_results", []),
        "reading_results": report.get("reading_results", []),
    }

    collected = {
        "source_report_path": str(report_path),
        "brief_call": {
            "system_instruction": BRIEF_SYSTEM_PROMPT,
            "response_json_schema": bounded_mod.BRIEF_SCHEMA,
            "schema_docs": BRIEF_SCHEMA_DOCS,
            "input_payload": {
                "user_query": report["query"],
                "preferred_conferences": [],
                "preferred_years": [],
            },
            "output": report["brief"],
        },
        "selection_calls": selection_calls,
        "paper_reading_calls": paper_reading_calls,
        "final_report_call": {
            "system_instruction": bounded_mod.REPORT_SYSTEM_PROMPT,
            "response_json_schema": None,
            "schema_docs": None,
            "input_payload": {
                "user_query": report["query"],
                "brief": summary_payload["brief"],
                "evidence_pack": report.get("evidence_pack"),
                "report_outline": report.get("report_outline"),
            },
            "output": report["final_text"],
        },
    }
    if report.get("evidence_pack") is not None:
        collected["evidence_pack_call"] = {
            "system_instruction": bounded_mod.EVIDENCE_PACK_SYSTEM_PROMPT,
            "response_json_schema": bounded_mod.EVIDENCE_PACK_SCHEMA,
            "schema_docs": {
                "top_level": EVIDENCE_PACK_SCHEMA_DOCS,
                "evidence_cards_item": EVIDENCE_CARD_SCHEMA_DOCS,
            },
            "input_payload": {
                "user_query": report["query"],
                "brief": summary_payload["brief"],
                "selected_papers": report.get("selected_papers"),
                "reading_results": report.get("reading_results"),
            },
            "output": report.get("evidence_pack"),
        }
    if report.get("report_outline") is not None:
        collected["report_outline_call"] = {
            "system_instruction": bounded_mod.REPORT_OUTLINE_SYSTEM_PROMPT,
            "response_json_schema": bounded_mod.REPORT_OUTLINE_SCHEMA,
            "schema_docs": {
                "top_level": REPORT_OUTLINE_SCHEMA_DOCS,
                "directions_item": REPORT_OUTLINE_DIRECTION_DOCS,
            },
            "input_payload": {
                "user_query": report["query"],
                "brief": {
                    "research_goal": report["brief"]["research_goal"],
                    "breadth_mode": report["brief"]["breadth_mode"],
                    "search_axes": report["brief"]["search_axes"],
                },
                "evidence_pack": report.get("evidence_pack"),
            },
            "output": report.get("report_outline"),
        }
    return collected


def _append_schema_docs(lines: list[str], docs: dict[str, str], title: str) -> None:
    lines.append(title)
    for key, meaning in docs.items():
        lines.append(f"- `{key}`: {meaning}")


def _render_markdown(model_calls: dict[str, Any], output_json_path: Path) -> str:
    lines: list[str] = []
    lines.append("# Bounded Agent Model Calls")
    lines.append("")
    lines.append(f"- Source run: `{model_calls['source_report_path']}`")
    lines.append(f"- Structured dump: `{output_json_path}`")
    lines.append("")

    brief_call = model_calls["brief_call"]
    lines.append("## 1. Brief Call")
    lines.append("")
    lines.append("### System Instruction")
    lines.append("```text")
    lines.append(brief_call["system_instruction"])
    lines.append("```")
    lines.append("### Response JSON Schema")
    lines.append("```json")
    lines.append(json.dumps(brief_call["response_json_schema"], ensure_ascii=False, indent=2))
    lines.append("```")
    _append_schema_docs(lines, brief_call["schema_docs"], "### Schema Field Meanings")
    lines.append("### Input Payload")
    lines.append("```json")
    lines.append(json.dumps(brief_call["input_payload"], ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("### Output")
    lines.append("```json")
    lines.append(json.dumps(brief_call["output"], ensure_ascii=False, indent=2))
    lines.append("```")

    lines.append("## 2. Selection Calls")
    for call in model_calls["selection_calls"]:
        lines.append("")
        lines.append(f"### Round {call['round_index']}")
        lines.append("#### System Instruction")
        lines.append("```text")
        lines.append(call["system_instruction"])
        lines.append("```")
        lines.append("#### Response JSON Schema")
        lines.append("```json")
        lines.append(json.dumps(call["response_json_schema"], ensure_ascii=False, indent=2))
        lines.append("```")
        _append_schema_docs(lines, call["schema_docs"]["top_level"], "#### Top-level Field Meanings")
        _append_schema_docs(lines, call["schema_docs"]["selected_papers_item"], "#### `selected_papers[]` Field Meanings")
        lines.append("#### Input Payload")
        lines.append("```json")
        lines.append(json.dumps(call["input_payload"], ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("#### Output")
        lines.append("```json")
        lines.append(json.dumps(call["output"], ensure_ascii=False, indent=2))
        lines.append("```")

    lines.append("## 3. Paper Reading Calls")
    lines.append("")
    lines.append("这里没有 `response_json_schema`。每一轮精读调用都是自由文本输入和自由文本输出。")
    for call in model_calls["paper_reading_calls"]:
        paper = call["paper"]
        lines.append("")
        lines.append(f"### {paper['conference']} {paper['year']} {paper['title']}")
        lines.append(f"- Cache: `{call['cache_path']}`")
        lines.append(f"- Prompt cache key: `{call['prompt_cache_key']}`")
        for turn in call["turns"]:
            lines.append(f"#### Turn {turn['turn_index']}")
            lines.append("##### Prompt")
            lines.append("```text")
            lines.append(turn["prompt"])
            lines.append("```")
            lines.append("##### Response")
            lines.append("```text")
            lines.append(turn["response"])
            lines.append("```")
            lines.append("##### Meta")
            lines.append("```json")
            lines.append(json.dumps(turn["meta"], ensure_ascii=False, indent=2))
            lines.append("```")

    if model_calls.get("evidence_pack_call") is not None:
        evidence_call = model_calls["evidence_pack_call"]
        lines.append("## 4. Evidence Pack Call")
        lines.append("")
        lines.append("### System Instruction")
        lines.append("```text")
        lines.append(evidence_call["system_instruction"])
        lines.append("```")
        lines.append("### Response JSON Schema")
        lines.append("```json")
        lines.append(json.dumps(evidence_call["response_json_schema"], ensure_ascii=False, indent=2))
        lines.append("```")
        _append_schema_docs(lines, evidence_call["schema_docs"]["top_level"], "### Top-level Field Meanings")
        _append_schema_docs(lines, evidence_call["schema_docs"]["evidence_cards_item"], "### `evidence_cards[]` Field Meanings")
        lines.append("### Input Payload")
        lines.append("```json")
        lines.append(json.dumps(evidence_call["input_payload"], ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("### Output")
        lines.append("```json")
        lines.append(json.dumps(evidence_call["output"], ensure_ascii=False, indent=2))
        lines.append("```")

    if model_calls.get("report_outline_call") is not None:
        outline_call = model_calls["report_outline_call"]
        lines.append("## 5. Report Outline Call")
        lines.append("")
        lines.append("### System Instruction")
        lines.append("```text")
        lines.append(outline_call["system_instruction"])
        lines.append("```")
        lines.append("### Response JSON Schema")
        lines.append("```json")
        lines.append(json.dumps(outline_call["response_json_schema"], ensure_ascii=False, indent=2))
        lines.append("```")
        _append_schema_docs(lines, outline_call["schema_docs"]["top_level"], "### Top-level Field Meanings")
        _append_schema_docs(lines, outline_call["schema_docs"]["directions_item"], "### `directions[]` Field Meanings")
        lines.append("### Input Payload")
        lines.append("```json")
        lines.append(json.dumps(outline_call["input_payload"], ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("### Output")
        lines.append("```json")
        lines.append(json.dumps(outline_call["output"], ensure_ascii=False, indent=2))
        lines.append("```")

    final_call = model_calls["final_report_call"]
    lines.append("## 6. Final Report Call")
    lines.append("")
    lines.append("这里也没有 `response_json_schema`。最终输出是自由文本 Markdown 报告。")
    lines.append("### System Instruction")
    lines.append("```text")
    lines.append(final_call["system_instruction"])
    lines.append("```")
    lines.append("### Input Payload")
    lines.append("```json")
    lines.append(json.dumps(final_call["input_payload"], ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("### Output")
    lines.append("```text")
    lines.append(final_call["output"])
    lines.append("```")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    report_path = Path(args.report)
    report = _read_json(report_path)
    model_calls = _collect_model_calls(report, report_path)

    output_json_path = report_path.with_name(f"{report_path.stem}_model_calls.json")
    output_md_path = report_path.with_name(f"{report_path.stem}_model_calls.md")

    output_json_path.write_text(
        json.dumps(model_calls, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    output_md_path.write_text(
        _render_markdown(model_calls, output_json_path),
        encoding="utf-8",
    )
    print(output_md_path)
    print(output_json_path)


if __name__ == "__main__":
    main()
