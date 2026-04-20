from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, replace
from typing import Any, Callable

from google import genai
from google.genai import types

from research.reader.paper_reader import PaperReader
from research.targeting import CONFERENCE_DISPLAY_NAMES, normalize_target_years
from research.tools.search_tools import SearchTools


DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"
DEFAULT_MAX_SEARCH_ROUNDS = 3
DEFAULT_MAX_QUERIES_PER_ROUND = 4
DEFAULT_MAX_CANDIDATE_POOL = 60
DEFAULT_MAX_FULL_READS = 8
DEFAULT_MIN_FULL_READS = 3
DEFAULT_READING_PROMPTS = [
    "请你使用中文总结一下这篇文章的内容，并且举一个例子加以说明。"
]
QUERY_WHITESPACE_RE = re.compile(r"\s+")
JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL | re.IGNORECASE)

RESEARCH_GOAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "research_goal": {"type": "string"},
    },
    "required": ["research_goal"],
}

SEARCH_AXES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "search_axes": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 2,
            "maxItems": 6,
        },
    },
    "required": ["search_axes"],
}

INITIAL_QUERIES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "initial_queries": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 2,
            "maxItems": 10,
        },
    },
    "required": ["initial_queries"],
}

RERANK_QUERY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rerank_query": {"type": "string"},
    },
    "required": ["rerank_query"],
}

SEARCH_CONTROL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "continue_search": {"type": "boolean"},
        "rationale": {"type": "string"},
        "additional_queries": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 10,
        },
        "missing_axes": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 5,
        },
    },
    "required": ["continue_search", "rationale", "additional_queries", "missing_axes"],
}

PAPER_ADMISSION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "should_read": {"type": "boolean"},
        "axis": {"type": "string"},
        "reason": {"type": "string"},
        "priority": {"type": "integer", "minimum": 1, "maximum": 10},
    },
    "required": ["should_read", "axis", "reason", "priority"],
}

EVIDENCE_PACK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "evidence_cards": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "conference": {"type": "string"},
                    "year": {"type": "integer"},
                    "paper_id": {"type": "string"},
                    "title": {"type": "string"},
                    "primary_direction": {"type": "string"},
                    "primary_type": {"type": "string"},
                    "training_stage": {"type": "string"},
                    "selection_reason": {"type": "string"},
                    "problem": {"type": "string"},
                    "method": {"type": "string"},
                    "method_novelty": {"type": "string"},
                    "evaluation_strength": {"type": "string"},
                    "deployment_relevance": {"type": "string"},
                    "key_findings": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "strongest_evidence": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "limitations": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "relevance_to_query": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": [
                    "conference",
                    "year",
                    "paper_id",
                    "title",
                    "primary_direction",
                    "primary_type",
                    "training_stage",
                    "selection_reason",
                    "problem",
                    "method",
                    "method_novelty",
                    "evaluation_strength",
                    "deployment_relevance",
                    "key_findings",
                    "strongest_evidence",
                    "limitations",
                    "relevance_to_query",
                    "confidence",
                ],
            },
        },
        "weak_signal_summary": {
            "type": "array",
            "items": {"type": "string"},
        },
        "cross_paper_observations": {
            "type": "array",
            "items": {"type": "string"},
        },
        "evidence_gaps": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "evidence_cards",
        "weak_signal_summary",
        "cross_paper_observations",
        "evidence_gaps",
    ],
}

PER_PAPER_EVIDENCE_CARD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": EVIDENCE_PACK_SCHEMA["properties"]["evidence_cards"]["items"]["properties"],
    "required": EVIDENCE_PACK_SCHEMA["properties"]["evidence_cards"]["items"]["required"],
}

EVIDENCE_PACK_SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "weak_signal_summary": {
            "type": "array",
            "items": {"type": "string"},
        },
        "cross_paper_observations": {
            "type": "array",
            "items": {"type": "string"},
        },
        "evidence_gaps": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "weak_signal_summary",
        "cross_paper_observations",
        "evidence_gaps",
    ],
}

REPORT_OUTLINE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "executive_summary_claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "supporting_paper_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["claim", "supporting_paper_ids", "confidence"],
            },
        },
        "directions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "importance": {"type": "string"},
                    "supporting_paper_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                    },
                    "maturity": {"type": "string", "enum": ["mature", "emerging", "early"]},
                    "evidence_strength": {"type": "string", "enum": ["high", "medium", "low"]},
                    "comparison_points": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "name",
                    "importance",
                    "supporting_paper_ids",
                    "maturity",
                    "evidence_strength",
                    "comparison_points",
                ],
            },
        },
        "paper_analysis_order": {
            "type": "array",
            "items": {"type": "string"},
        },
        "synthesis_points": {
            "type": "array",
            "items": {"type": "string"},
        },
        "paper_relationships": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "paper_id_a": {"type": "string"},
                    "paper_id_b": {"type": "string"},
                    "relationship_type": {
                        "type": "string",
                        "enum": [
                            "extends",
                            "contrasts",
                            "complements",
                            "same_family",
                            "attack_defense",
                            "evaluation_link",
                        ],
                    },
                    "explanation": {"type": "string"},
                },
                "required": ["paper_id_a", "paper_id_b", "relationship_type", "explanation"],
            },
        },
        "evidence_gaps": {
            "type": "array",
            "items": {"type": "string"},
        },
        "suggested_reading_order": {
            "type": "array",
            "items": {"type": "string"},
        },
        "open_questions": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "title",
        "executive_summary_claims",
        "directions",
        "paper_analysis_order",
        "synthesis_points",
        "paper_relationships",
        "evidence_gaps",
        "suggested_reading_order",
        "open_questions",
    ],
}

EVIDENCE_PACK_SYSTEM_PROMPT = (
    "You are extracting a single structured evidence card for one fully-read academic paper. "
    "Use the full-paper reading notes as high-confidence evidence. "
    "Do not invent experiments, numbers, methods, or conclusions. "
    "Capture the problem, method, method novelty, evaluation strength, deployment relevance, strongest evidence, limitations, and relevance to the user query. "
    "Method novelty should state what is genuinely new or distinctive about the approach. "
    "Evaluation strength should judge how convincing the empirical or analytical evidence is, and why. "
    "Deployment relevance should state whether the paper matters mainly for practical post-training/deployment, for research understanding, or both."
)

EVIDENCE_PACK_SUMMARY_SYSTEM_PROMPT = (
    "You are preparing the cross-paper summary for an academic deep-research evidence pack. "
    "Use the provided evidence cards as the main evidence base. "
    "Use retrieval-only weak signals only when they add plausible but unverified context. "
    "Do not invent methods, results, or conclusions. "
    "Your job is to summarize weak signals, identify cross-paper observations, and state evidence gaps. "
    "Cross-paper observations should emphasize recurring method families, tensions, attack-defense pairings, and complementary papers."
)

REPORT_OUTLINE_SYSTEM_PROMPT = (
    "You are designing the outline for a deep-research report. "
    "Base the outline only on the provided evidence pack. "
    "Every important claim and every direction must be tied to supporting paper ids. "
    "Each main direction must be supported by at least two papers. "
    "If a potential direction only has one supporting paper, either merge it into a broader direction or downgrade it into an evidence gap instead of making it a main direction. "
    "Prefer cross-paper structure over conference-by-conference summaries. "
    "Explicitly identify relationships between papers, including extension, contrast, complementarity, same-method-family clustering, attack-defense pairing, and evaluation links. "
    "Do not treat papers as isolated bullets. "
    "paper_analysis_order must contain every fully-read paper id from the evidence pack exactly once. "
    "Be explicit about evidence gaps and maturity level."
)

REPORT_SYSTEM_PROMPT = (
    "You are writing a detailed deep-research report in Chinese. "
    "Base the report only on the provided brief, evidence pack, and report outline. "
    "Never invent experiments, numbers, methods, or conclusions. "
    "Never expose raw paper_id values, UUIDs, or internal identifiers in visible report text, headings, or bullets. "
    "When referring to a paper, always use its human-readable title. "
    "Every substantive claim must carry an explicit evidence citation using paper titles. "
    "Use the citation format '(evidence: Title A; Title B)' with 1-3 supporting paper titles. "
    "Every Executive Summary bullet must end with an evidence citation. "
    "In Direction Map, Detailed Paper Analyses, and Cross-Paper Synthesis, every paragraph that makes a claim must end with an evidence citation. "
    "If a statement is only weakly supported by retrieval-only signals, mark it explicitly as weak signal and still attach a citation. "
    "Do not leave uncited analytical claims in the report. "
    "Treat evidence cards as high-confidence evidence and weak signals as low-confidence context. "
    "Write the report in Markdown with exactly these top-level sections: "
    "1. 核心结论 "
    "2. 研究方向全景 "
    "3. 逐篇精读 "
    "4. 跨论文关系与综合分析 "
    "5. 证据不足与局限 "
    "6. 建议阅读顺序 "
    "7. 值得继续追的问题. "
    "In 核心结论, give 5-8 high-signal bullets with concrete evidence binding. "
    "In 研究方向全景, organize by distinct directions rather than by conference, and explain why each direction matters, what evidence supports it, how mature it is, and how the key papers within that direction relate to one another. Each direction should clearly mention at least two supporting papers. "
    "In 逐篇精读, only analyze fully read papers. You must include one clearly labeled subsection for every paper listed in report_outline.paper_analysis_order, and each subsection heading must use the paper title rather than any internal id. For each paper cover the problem, method, strongest evidence, limitations, why it matters for the user query, and how it connects to at least one other paper in the report. Avoid one-line summaries. "
    "In 跨论文关系与综合分析, compare methods, strengths, limitations, unresolved tensions, and explicit relationships across papers. You should clearly state which papers extend each other, which papers contradict or challenge each other, which papers are complementary, and which papers form attack-defense or method-evaluation pairs. "
    "Make the paper-to-paper relationships a central part of the analysis, not an afterthought. "
    "In 证据不足与局限, clearly separate high-confidence conclusions from weak signals."
)

REPORT_REPAIR_SYSTEM_PROMPT = (
    "You are repairing a deep-research report draft in Chinese. "
    "The draft failed formatting or citation requirements. "
    "Rewrite the report so it strictly follows the required structure and evidence rules. "
    "Use exactly these top-level Markdown sections and these Chinese titles only: "
    "1. 核心结论 "
    "2. 研究方向全景 "
    "3. 逐篇精读 "
    "4. 跨论文关系与综合分析 "
    "5. 证据不足与局限 "
    "6. 建议阅读顺序 "
    "7. 值得继续追的问题. "
    "Never expose raw paper_id values, UUIDs, or internal identifiers in visible text. "
    "Always use human-readable paper titles. "
    "Every substantive bullet or paragraph must end with an evidence citation in the exact format '(evidence: Title A; Title B)'. "
    "Use 1-3 titles per citation. "
    "Keep the content analytical and detailed, not summary-only."
)


@dataclass(frozen=True)
class ResearchBrief:
    research_goal: str
    search_axes: list[str]
    initial_queries: list[str]
    rerank_query: str
    reading_prompts: list[str]
    target_conferences: list[str]
    target_years: list[int]


@dataclass(frozen=True)
class SelectedPaper:
    title: str
    conference: str
    year: int
    paper_id: str
    axis: str
    reason: str
    priority: int


@dataclass(frozen=True)
class CandidateAdmissionDecision:
    title: str
    conference: str
    year: int
    paper_id: str
    should_read: bool
    axis: str
    reason: str
    priority: int
    rerank_score: float
    coarse_score: float


@dataclass(frozen=True)
class SearchRoundDecision:
    continue_search: bool
    rationale: str
    additional_queries: list[str]
    missing_axes: list[str]


@dataclass(frozen=True)
class SearchRoundResult:
    round_index: int
    queries: list[str]
    coarse_results: list[dict[str, Any]]
    merged_candidates: list[dict[str, Any]]
    reranked_results: list[dict[str, Any]]
    decision: SearchRoundDecision
    selected_papers: list[SelectedPaper]
    candidate_admissions: list[CandidateAdmissionDecision]


@dataclass(frozen=True)
class BoundedSelectionResult:
    brief: ResearchBrief
    rounds: list[SearchRoundResult]
    selected_papers: list[dict[str, Any]]
    detail_results: list[dict[str, Any]]


@dataclass(frozen=True)
class BoundedRunResult:
    brief: ResearchBrief
    rounds: list[SearchRoundResult]
    selected_papers: list[dict[str, Any]]
    detail_results: list[dict[str, Any]]
    reading_results: list[dict[str, Any]]
    evidence_pack: dict[str, Any]
    report_outline: dict[str, Any]
    final_text: str


class BoundedResearchRunner:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_GEMINI_MODEL,
        search_tools: SearchTools | None = None,
        paper_reader: PaperReader | None = None,
    ) -> None:
        api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        self.client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
        self.model = model
        self.search_tools = search_tools or SearchTools()
        self.paper_reader = paper_reader or PaperReader()

    def _extract_json(self, text: str) -> dict[str, Any]:
        value = text.strip()
        if not value:
            raise ValueError("Empty model response")

        fenced = JSON_BLOCK_RE.search(value)
        if fenced:
            value = fenced.group(1).strip()

        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        decoder = json.JSONDecoder()
        for idx, char in enumerate(value):
            if char not in "{[":
                continue
            try:
                parsed, _ = decoder.raw_decode(value[idx:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        raise ValueError(f"Could not extract JSON object from model response: {text[:400]}")

    def _generate_json_dict(
        self,
        *,
        system_instruction: str,
        payload: dict[str, Any],
        schema: dict[str, Any],
        max_output_tokens: int = 4096,
        retries: int = 2,
    ) -> dict[str, Any]:
        schema_text = json.dumps(schema, ensure_ascii=False)
        contents = json.dumps(payload, ensure_ascii=False)
        last_error: Exception | None = None
        for attempt in range(1, retries + 1):
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=(
                        f"{system_instruction} "
                        "Return exactly one JSON object and nothing else. "
                        "Do not add markdown fences, prefaces, explanations, or trailing commentary. "
                        f"The required JSON schema is: {schema_text}"
                    ),
                    max_output_tokens=max_output_tokens,
                ),
            )
            try:
                return self._extract_json(response.text or "")
            except Exception as exc:
                last_error = exc
                contents = json.dumps(
                    {
                        "original_payload": payload,
                        "previous_response": response.text or "",
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                )
        raise ValueError(f"Structured JSON generation failed after {retries} attempts: {last_error}")

    def make_brief(
        self,
        user_query: str,
        conferences: list[str] | None = None,
        effective_years: list[int] | None = None,
        max_search_rounds: int = DEFAULT_MAX_SEARCH_ROUNDS,
        reading_prompts_override: list[str] | None = None,
    ) -> ResearchBrief:
        effective_years = effective_years or []
        brief_conferences = [item.lower() for item in (conferences or []) if str(item).strip()]
        brief_years = [int(item) for item in effective_years]
        explicit_scope = bool(brief_conferences or brief_years)
        axis_count_instruction = (
            "Return exactly 1 distinct research axis. "
            if max_search_rounds <= 1
            else f"Return 2-{max_search_rounds} distinct research axes that together cover the topic broadly. "
        )
        base_payload = {
            "user_query": user_query,
            "preferred_conferences": brief_conferences,
            "preferred_years": brief_years,
        }
        research_goal = self._generate_json_dict(
            system_instruction=(
                "You are generating the research goal for a deep-research paper search workflow. "
                "Return one concise sentence that states what the user is trying to understand or collect. "
                "Assume deep research is always coverage-first and comprehensive."
            ),
            payload=base_payload,
            schema=RESEARCH_GOAL_SCHEMA,
            max_output_tokens=512,
        )["research_goal"].strip()
        search_axes = [
            item.strip()
            for item in self._generate_json_dict(
                system_instruction=(
                    "You are generating search axes for a comprehensive deep-research workflow. "
                    f"{axis_count_instruction}"
                    "Each axis should itself be a usable retrieval phrase. "
                    "Do not include conference names or years in the axes. "
                    "The number of axes must not exceed the maximum search rounds."
                ),
                payload={
                    **base_payload,
                    "research_goal": research_goal,
                    "max_search_rounds": max_search_rounds,
                },
                schema=SEARCH_AXES_SCHEMA,
                max_output_tokens=1024,
            )["search_axes"]
            if item.strip()
        ]
        initial_queries = [
            item.strip()
            for item in self._generate_json_dict(
                system_instruction=(
                    "You are generating initial retrieval queries for deep-research paper search. "
                    "Return 2-10 short retrieval-oriented queries that maximize topical coverage. "
                    "Each query should be a search phrase, not a full sentence. "
                    "If conference/year scope is already fixed outside retrieval, do not include venue names or explicit years in the queries."
                ),
                payload={
                    **base_payload,
                    "research_goal": research_goal,
                    "search_axes": search_axes,
                },
                schema=INITIAL_QUERIES_SCHEMA,
                max_output_tokens=1024,
            )["initial_queries"]
            if item.strip()
        ]
        rerank_query = self._generate_json_dict(
            system_instruction=(
                "You are generating the rerank query for a paper reranker. "
                "Return one task-oriented question or instruction sentence, not a keyword list. "
                "It should describe what papers are most relevant to the user's research goal. "
                "If conference/year scope is already fixed outside retrieval, do not include venue names or explicit years."
            ),
            payload={
                **base_payload,
                "research_goal": research_goal,
                "search_axes": search_axes,
                "initial_queries": initial_queries,
            },
            schema=RERANK_QUERY_SCHEMA,
            max_output_tokens=768,
        )["rerank_query"].strip()
        reading_prompts = [item.strip() for item in (reading_prompts_override or []) if item.strip()]
        if not reading_prompts:
            reading_prompts = list(DEFAULT_READING_PROMPTS)

        search_axes = self._dedupe_queries(
            self._sanitize_queries_for_scope(
                queries=search_axes,
                conferences=brief_conferences,
                years=brief_years,
            )
        )[:max_search_rounds]
        initial_queries = self._dedupe_queries(
            self._sanitize_queries_for_scope(
                queries=initial_queries,
                conferences=brief_conferences,
                years=brief_years,
            )
        )
        if explicit_scope:
            rerank_query = self._sanitize_query_for_scope(
                query=rerank_query,
                conferences=brief_conferences,
                years=brief_years,
            )
        return ResearchBrief(
            research_goal=research_goal,
            search_axes=search_axes,
            initial_queries=initial_queries,
            rerank_query=rerank_query,
            reading_prompts=reading_prompts,
            target_conferences=brief_conferences,
            target_years=brief_years,
        )

    def run(
        self,
        user_query: str,
        conferences: list[str] | None = None,
        years: list[int] | None = None,
        top_k_per_asset: int = 8,
        top_k_global: int = 15,
        rerank_top_n: int = 20,
        details_top_n: int = 12,
        max_search_rounds: int = DEFAULT_MAX_SEARCH_ROUNDS,
        max_queries_per_round: int = DEFAULT_MAX_QUERIES_PER_ROUND,
        max_candidate_pool: int = DEFAULT_MAX_CANDIDATE_POOL,
        max_full_reads: int = DEFAULT_MAX_FULL_READS,
        min_full_reads: int = DEFAULT_MIN_FULL_READS,
        reading_prompts_override: list[str] | None = None,
    ) -> BoundedRunResult:
        selection = self.run_selection(
            user_query=user_query,
            conferences=conferences,
            years=years,
            top_k_per_asset=top_k_per_asset,
            top_k_global=top_k_global,
            rerank_top_n=rerank_top_n,
            details_top_n=details_top_n,
            max_search_rounds=max_search_rounds,
            max_queries_per_round=max_queries_per_round,
            max_candidate_pool=max_candidate_pool,
            max_full_reads=max_full_reads,
            min_full_reads=min_full_reads,
            reading_prompts_override=reading_prompts_override,
        )
        detail_lookup = {
            (item["conference"], int(item["year"]), item["paper_id"]): item
            for item in selection.detail_results
        }
        reading_inputs = [
            detail_lookup[key]
            for key in [
                (item["conference"], int(item["year"]), item["paper_id"])
                for item in selection.selected_papers
            ]
            if key in detail_lookup
        ]
        reading_results = [
            self._reading_result_to_dict(item)
            for item in self.paper_reader.read_papers(
                papers=reading_inputs,
                user_query=user_query,
                template_prompts=selection.brief.reading_prompts,
            )
        ]

        weak_signals = self._build_weak_signals(rounds=selection.rounds, selected_papers=selection.selected_papers)
        evidence_pack = self._build_evidence_pack(
            user_query=user_query,
            brief=selection.brief,
            selected_papers=selection.selected_papers,
            reading_results=reading_results,
            weak_signals=weak_signals,
        )
        report_outline = self._build_report_outline(
            user_query=user_query,
            brief=selection.brief,
            evidence_pack=evidence_pack,
        )
        final_text = self._summarize(
            user_query=user_query,
            brief=selection.brief,
            evidence_pack=evidence_pack,
            report_outline=report_outline,
        )
        return BoundedRunResult(
            brief=selection.brief,
            rounds=selection.rounds,
            selected_papers=selection.selected_papers,
            detail_results=selection.detail_results,
            reading_results=reading_results,
            evidence_pack=evidence_pack,
            report_outline=report_outline,
            final_text=final_text,
        )

    def run_selection(
        self,
        user_query: str,
        conferences: list[str] | None = None,
        years: list[int] | None = None,
        top_k_per_asset: int = 8,
        top_k_global: int = 15,
        rerank_top_n: int = 20,
        details_top_n: int = 12,
        max_search_rounds: int = DEFAULT_MAX_SEARCH_ROUNDS,
        max_queries_per_round: int = DEFAULT_MAX_QUERIES_PER_ROUND,
        max_candidate_pool: int = DEFAULT_MAX_CANDIDATE_POOL,
        max_full_reads: int = DEFAULT_MAX_FULL_READS,
        min_full_reads: int = DEFAULT_MIN_FULL_READS,
        reading_prompts_override: list[str] | None = None,
        trace_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> BoundedSelectionResult:
        effective_years = normalize_target_years(
            years,
            available_years=[asset.year for asset in self.search_tools.assets],
        )
        brief = self.make_brief(
            user_query,
            conferences=conferences,
            effective_years=effective_years,
            max_search_rounds=max_search_rounds,
            reading_prompts_override=reading_prompts_override,
        )
        if trace_callback is not None:
            trace_callback(
                {
                    "type": "brief",
                    "brief": brief,
                    "effective_years": effective_years,
                }
            )
        all_coarse_results: list[dict[str, Any]] = []
        all_queries_seen: list[str] = []
        selected_map: dict[tuple[str, int, str], SelectedPaper] = {}
        rounds: list[SearchRoundResult] = []

        axis_queue = list(brief.search_axes[:max_search_rounds])
        current_queries = [axis_queue.pop(0)] if axis_queue else self._dedupe_queries(brief.initial_queries)[:max_queries_per_round]
        for round_index in range(1, max_search_rounds + 1):
            if not current_queries:
                break

            round_coarse_results: list[dict[str, Any]] = []
            selected_keys = {
                (item.conference, int(item.year), item.paper_id)
                for item in selected_map.values()
            }
            effective_conferences = conferences or brief.target_conferences or None
            for query in current_queries:
                if query in all_queries_seen:
                    continue
                all_queries_seen.append(query)
                coarse = self.search_tools.coarse_search(
                    query=query,
                    conferences=effective_conferences,
                    years=effective_years,
                    top_k_per_asset=top_k_per_asset,
                    top_k_global=top_k_global,
                )
                coarse_item = {
                    "sub_query": query,
                    "results": self._filter_search_results_by_selected_keys(
                        coarse["results"],
                        selected_keys=selected_keys,
                    ),
                    "elapsed_sec": coarse["elapsed_sec"],
                }
                round_coarse_results.append(coarse_item)
                all_coarse_results.append(coarse_item)

            merged_candidates = self._filter_candidate_payloads_by_selected_keys(
                self._merge_candidates(all_coarse_results),
                selected_keys=selected_keys,
            )[:max_candidate_pool]
            reranked = self.search_tools.rerank_search(
                query=brief.rerank_query,
                candidates=merged_candidates,
                top_n=min(rerank_top_n, len(merged_candidates)),
            )
            reranked_results = reranked["results"]
            round_selected_papers, round_candidate_admissions = self._evaluate_candidates_for_reading(
                user_query=user_query,
                brief=brief,
                reranked_results=reranked_results,
                selected_papers=list(selected_map.values()),
                max_full_reads=max_full_reads,
            )
            decision = self._decide_search_control(
                user_query=user_query,
                brief=brief,
                round_index=round_index,
                queries_this_round=current_queries,
                searched_queries=all_queries_seen,
                selected_papers=list(selected_map.values()),
                selected_this_round=round_selected_papers,
                coarse_hit_count=sum(len(item["results"]) for item in round_coarse_results),
                merged_candidate_count=len(merged_candidates),
                reranked_candidate_count=len(reranked_results),
                max_full_reads=max_full_reads,
                remaining_search_rounds=max_search_rounds - round_index,
            )
            fallback_queries: list[str] = []
            if not axis_queue and self._should_force_fallback_round(
                decision=decision,
                selected_so_far=selected_map,
                selected_this_round_count=len(round_selected_papers),
                max_full_reads=max_full_reads,
                remaining_search_rounds=max_search_rounds - round_index,
            ):
                fallback_queries = self._build_fallback_queries(
                    brief=brief,
                    searched_queries=all_queries_seen,
                    max_queries_per_round=max_queries_per_round,
                )
                if fallback_queries:
                    decision = replace(
                        decision,
                        continue_search=True,
                        rationale=(
                            "The model returned an empty stop decision before the reading budget was used. "
                            "Continue with fallback queries derived from the research brief to improve coverage."
                        ),
                        additional_queries=fallback_queries,
                        missing_axes=brief.search_axes[: min(3, len(brief.search_axes))],
                    )
            round_result = SearchRoundResult(
                round_index=round_index,
                queries=list(current_queries),
                coarse_results=round_coarse_results,
                merged_candidates=merged_candidates,
                reranked_results=reranked_results,
                decision=decision,
                selected_papers=round_selected_papers,
                candidate_admissions=round_candidate_admissions,
            )
            rounds.append(round_result)

            for item in round_selected_papers:
                key = (item.conference, item.year, item.paper_id)
                existing = selected_map.get(key)
                if existing is None or item.priority < existing.priority:
                    selected_map[key] = item

            if trace_callback is not None:
                trace_callback(
                    {
                        "type": "round",
                        "brief": brief,
                        "round": round_result,
                        "selected_papers": list(selected_map.values()),
                    }
                )

            if len(selected_map) >= max_full_reads:
                break
            if axis_queue:
                current_queries = [axis_queue.pop(0)]
                continue
            if not decision.continue_search:
                break
            current_queries = [
                query
                for query in self._dedupe_queries(decision.additional_queries)
                if query not in all_queries_seen
            ][:max_queries_per_round]

        final_reranked_results = self._merge_reranked_results(rounds)
        selected_records = self._materialize_selected_papers(
            selected_map=selected_map,
            reranked_results=final_reranked_results,
            min_full_reads=min_full_reads,
            max_full_reads=max_full_reads,
        )

        detail_refs = [
            {
                "conference": item["conference"],
                "year": item["year"],
                "paper_id": item["paper_id"],
            }
            for item in selected_records[:details_top_n]
        ]
        detail_results = self.search_tools.get_paper_details(detail_refs)["results"]
        if trace_callback is not None:
            trace_callback(
                {
                    "type": "final",
                    "brief": brief,
                    "rounds": rounds,
                    "selected_papers": selected_records,
                    "detail_results": detail_results,
                }
            )
        return BoundedSelectionResult(
            brief=brief,
            rounds=rounds,
            selected_papers=selected_records,
            detail_results=detail_results,
        )

    def _decide_search_control(
        self,
        user_query: str,
        brief: ResearchBrief,
        round_index: int,
        queries_this_round: list[str],
        searched_queries: list[str],
        selected_papers: list[SelectedPaper],
        selected_this_round: list[SelectedPaper],
        coarse_hit_count: int,
        merged_candidate_count: int,
        reranked_candidate_count: int,
        max_full_reads: int,
        remaining_search_rounds: int,
    ) -> SearchRoundDecision:
        prompt = (
            "You are controlling the search loop for a comprehensive deep-research workflow. "
            "Your task is only to decide whether another search round is needed. "
            "Do not decide paper admission here. "
            "Use continue_search only when important research axes are still missing and there are search rounds left. "
            "If conference/year scope is already fixed outside retrieval, do not put venue names or explicit years into additional_queries. "
            "If you stop searching, rationale must explicitly explain why current coverage is sufficient."
        )
        payload = {
            "user_query": user_query,
            "brief": {
                "research_goal": brief.research_goal,
                "search_axes": brief.search_axes,
                "rerank_query": brief.rerank_query,
            },
            "round_index": round_index,
            "queries_this_round": queries_this_round,
            "searched_queries": searched_queries,
            "remaining_search_rounds": remaining_search_rounds,
            "max_full_reads": max_full_reads,
            "search_stats": {
                "coarse_hit_count": coarse_hit_count,
                "merged_candidate_count": merged_candidate_count,
                "reranked_candidate_count": reranked_candidate_count,
                "selected_count_total": len(selected_papers),
                "selected_count_this_round": len(selected_this_round),
            },
            "already_selected": [
                {
                    "title": item.title,
                    "conference": item.conference,
                    "year": item.year,
                    "paper_id": item.paper_id,
                     "axis": item.axis,
                    "reason": item.reason,
                    "priority": item.priority,
                }
                for item in selected_papers
            ],
            "selected_this_round": [
                {
                    "title": item.title,
                    "conference": item.conference,
                    "year": item.year,
                    "paper_id": item.paper_id,
                    "axis": item.axis,
                    "reason": item.reason,
                    "priority": item.priority,
                }
                for item in selected_this_round
            ],
        }
        result = self._generate_json_dict(
            system_instruction=prompt,
            payload=payload,
            schema=SEARCH_CONTROL_SCHEMA,
            max_output_tokens=2048,
        )
        return SearchRoundDecision(
            continue_search=bool(result.get("continue_search")) and remaining_search_rounds > 0,
            rationale=str(result.get("rationale") or "").strip(),
            additional_queries=self._sanitize_queries_for_scope(
                queries=[
                    str(item).strip()
                    for item in (result.get("additional_queries") or [])
                    if str(item).strip()
                ],
                conferences=brief.target_conferences,
                years=brief.target_years,
            ),
            missing_axes=[
                str(item).strip()
                for item in (result.get("missing_axes") or [])
                if str(item).strip()
            ],
        )

    def _evaluate_candidates_for_reading(
        self,
        *,
        user_query: str,
        brief: ResearchBrief,
        reranked_results: list[dict[str, Any]],
        selected_papers: list[SelectedPaper],
        max_full_reads: int,
    ) -> tuple[list[SelectedPaper], list[CandidateAdmissionDecision]]:
        accepted: list[SelectedPaper] = []
        decisions: list[CandidateAdmissionDecision] = []
        selected_keys = {
            (item.conference, int(item.year), item.paper_id)
            for item in selected_papers
        }
        for item in reranked_results:
            if len(selected_keys) + len(accepted) >= max_full_reads:
                break
            paper = item["paper"]
            key = (paper["conference"], int(paper["year"]), paper["paper_id"])
            if key in selected_keys:
                continue
            decision = self._evaluate_candidate_for_reading(
                user_query=user_query,
                brief=brief,
                candidate=item,
                selected_papers=selected_papers + accepted,
                max_full_reads=max_full_reads,
            )
            decisions.append(
                CandidateAdmissionDecision(
                    title=paper["title"],
                    conference=paper["conference"],
                    year=int(paper["year"]),
                    paper_id=paper["paper_id"],
                    should_read=bool(decision["should_read"]),
                    axis=str(decision["axis"]).strip() or "selected",
                    reason=str(decision["reason"]).strip(),
                    priority=int(decision["priority"]),
                    rerank_score=float(item["rerank_score"]),
                    coarse_score=float(item["coarse_score"]),
                )
            )
            if not decision["should_read"]:
                continue
            accepted.append(
                SelectedPaper(
                    title=paper["title"],
                    conference=paper["conference"],
                    year=int(paper["year"]),
                    paper_id=paper["paper_id"],
                    axis=str(decision["axis"]).strip() or "selected",
                    reason=str(decision["reason"]).strip(),
                    priority=int(decision["priority"]),
                )
            )
        return accepted, decisions

    def _evaluate_candidate_for_reading(
        self,
        *,
        user_query: str,
        brief: ResearchBrief,
        candidate: dict[str, Any],
        selected_papers: list[SelectedPaper],
        max_full_reads: int,
    ) -> dict[str, Any]:
        paper = candidate["paper"]
        prompt = (
            "You are deciding whether a single academic paper should enter the full-reading list for a deep-research workflow. "
            "Coverage is more important than compression. "
            "Do not reject a paper merely because another selected paper is in the same direction. "
            "Accept any paper that appears genuinely relevant and potentially useful for the final research report. "
            "Return JSON only."
        )
        payload = {
            "user_query": user_query,
            "brief": {
                "research_goal": brief.research_goal,
                "search_axes": brief.search_axes,
                "rerank_query": brief.rerank_query,
            },
            "max_full_reads": max_full_reads,
            "selected_count": len(selected_papers),
            "already_selected": [
                {
                    "title": item.title,
                    "conference": item.conference,
                    "year": item.year,
                    "axis": item.axis,
                    "reason": item.reason,
                    "priority": item.priority,
                }
                for item in selected_papers
            ],
            "candidate_paper": {
                "conference": paper["conference"],
                "year": int(paper["year"]),
                "paper_id": paper["paper_id"],
                "title": paper["title"],
                "abstract": paper["abstract"],
                "rerank_score": candidate["rerank_score"],
                "coarse_score": candidate["coarse_score"],
            },
        }
        return self._generate_json_dict(
            system_instruction=prompt,
            payload=payload,
            schema=PAPER_ADMISSION_SCHEMA,
            max_output_tokens=1024,
        )

    @staticmethod
    def _should_force_fallback_round(
        *,
        decision: SearchRoundDecision,
        selected_so_far: dict[tuple[str, int, str], SelectedPaper],
        selected_this_round_count: int,
        max_full_reads: int,
        remaining_search_rounds: int,
    ) -> bool:
        if remaining_search_rounds <= 0:
            return False
        if len(selected_so_far) >= max_full_reads:
            return False
        if decision.continue_search:
            return False
        if selected_this_round_count > 0:
            return False
        if decision.rationale.strip():
            return False
        if decision.additional_queries:
            return False
        if decision.missing_axes:
            return False
        return True

    def _build_fallback_queries(
        self,
        *,
        brief: ResearchBrief,
        searched_queries: list[str],
        max_queries_per_round: int,
    ) -> list[str]:
        candidates = self._sanitize_queries_for_scope(
            queries=(
                brief.search_axes
                + [brief.research_goal, brief.rerank_query]
            ),
            conferences=brief.target_conferences,
            years=brief.target_years,
        )
        searched_keys = {item.strip().lower() for item in searched_queries if item.strip()}
        fallback_queries = [
            item
            for item in self._dedupe_queries(candidates)
            if item.strip().lower() not in searched_keys
        ]
        return fallback_queries[:max_queries_per_round]

    def _materialize_selected_papers(
        self,
        selected_map: dict[tuple[str, int, str], SelectedPaper],
        reranked_results: list[dict[str, Any]],
        min_full_reads: int,
        max_full_reads: int,
    ) -> list[dict[str, Any]]:
        selected_records: list[dict[str, Any]] = []
        reranked_lookup = {
            (item["paper"]["conference"], int(item["paper"]["year"]), item["paper"]["paper_id"]): item
            for item in reranked_results
        }
        for item in sorted(selected_map.values(), key=lambda x: (x.priority, x.conference, x.year, x.paper_id)):
            key = (item.conference, item.year, item.paper_id)
            reranked = reranked_lookup.get(key)
            if reranked is None:
                continue
            selected_records.append(
                {
                    "conference": item.conference,
                    "year": item.year,
                    "paper_id": item.paper_id,
                    "axis": item.axis,
                    "reason": item.reason,
                    "priority": item.priority,
                    "paper": reranked["paper"],
                    "coarse_score": reranked["coarse_score"],
                    "rerank_score": reranked["rerank_score"],
                }
            )
            if len(selected_records) >= max_full_reads:
                return selected_records

        selected_keys = {
            (item["conference"], int(item["year"]), item["paper_id"])
            for item in selected_records
        }
        for reranked in reranked_results:
            key = (
                reranked["paper"]["conference"],
                int(reranked["paper"]["year"]),
                reranked["paper"]["paper_id"],
            )
            if key in selected_keys:
                continue
            selected_records.append(
                {
                    "conference": key[0],
                    "year": key[1],
                    "paper_id": key[2],
                    "axis": "fallback",
                    "reason": "Fallback selection to satisfy minimum reading budget.",
                    "priority": len(selected_records) + 1,
                    "paper": reranked["paper"],
                    "coarse_score": reranked["coarse_score"],
                    "rerank_score": reranked["rerank_score"],
                }
            )
            selected_keys.add(key)
            if len(selected_records) >= min_full_reads or len(selected_records) >= max_full_reads:
                break
        return selected_records[:max_full_reads]

    @staticmethod
    def _filter_search_results_by_selected_keys(
        results: list[dict[str, Any]],
        *,
        selected_keys: set[tuple[str, int, str]],
    ) -> list[dict[str, Any]]:
        if not selected_keys:
            return results
        filtered: list[dict[str, Any]] = []
        for item in results:
            paper = item["paper"]
            key = (paper["conference"], int(paper["year"]), paper["paper_id"])
            if key in selected_keys:
                continue
            filtered.append(item)
        return filtered

    @staticmethod
    def _filter_candidate_payloads_by_selected_keys(
        candidates: list[dict[str, Any]],
        *,
        selected_keys: set[tuple[str, int, str]],
    ) -> list[dict[str, Any]]:
        if not selected_keys:
            return candidates
        filtered: list[dict[str, Any]] = []
        for item in candidates:
            paper = item["paper"]
            key = (paper["conference"], int(paper["year"]), paper["paper_id"])
            if key in selected_keys:
                continue
            filtered.append(item)
        return filtered

    def _merge_candidates(self, coarse_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[tuple[str, int, str], dict[str, Any]] = {}
        for item in coarse_results:
            sub_query = item["sub_query"]
            for result in item["results"]:
                paper = result["paper"]
                key = (paper["conference"], int(paper["year"]), paper["paper_id"])
                existing = merged.get(key)
                if existing is None:
                    merged[key] = {
                        "paper": paper,
                        "coarse_score": float(result["coarse_score"]),
                        "matched_sub_queries": [sub_query],
                    }
                else:
                    existing["coarse_score"] = max(existing["coarse_score"], float(result["coarse_score"]))
                    if sub_query not in existing["matched_sub_queries"]:
                        existing["matched_sub_queries"].append(sub_query)
        values = list(merged.values())
        values.sort(key=lambda item: item["coarse_score"], reverse=True)
        return values

    def _merge_reranked_results(self, rounds: list[SearchRoundResult]) -> list[dict[str, Any]]:
        merged: dict[tuple[str, int, str], dict[str, Any]] = {}
        for round_item in rounds:
            for item in round_item.reranked_results:
                paper = item["paper"]
                key = (paper["conference"], int(paper["year"]), paper["paper_id"])
                existing = merged.get(key)
                if existing is None:
                    merged[key] = item
                    continue
                if float(item["rerank_score"]) > float(existing["rerank_score"]):
                    merged[key] = item
        values = list(merged.values())
        values.sort(key=lambda item: float(item["rerank_score"]), reverse=True)
        return values

    def _summarize(
        self,
        user_query: str,
        brief: ResearchBrief,
        evidence_pack: dict[str, Any],
        report_outline: dict[str, Any],
    ) -> str:
        paper_title_map = {
            str(item["paper_id"]): str(item["title"])
            for item in evidence_pack.get("evidence_cards", [])
            if item.get("paper_id") and item.get("title")
        }
        payload = {
            "user_query": user_query,
            "brief": {
                "research_goal": brief.research_goal,
                "search_axes": brief.search_axes,
                "initial_queries": brief.initial_queries,
                "rerank_query": brief.rerank_query,
            },
            "evidence_pack": evidence_pack,
            "report_outline": report_outline,
            "paper_title_map": paper_title_map,
        }
        response = self.client.models.generate_content(
            model=self.model,
            contents=json.dumps(payload, ensure_ascii=False),
            config=types.GenerateContentConfig(
                system_instruction=REPORT_SYSTEM_PROMPT,
                max_output_tokens=12288,
            ),
        )
        return response.text or ""

    def _repair_report(
        self,
        *,
        user_query: str,
        brief: ResearchBrief,
        evidence_pack: dict[str, Any],
        report_outline: dict[str, Any],
        draft_report: str,
    ) -> str:
        paper_title_map = {
            str(item["paper_id"]): str(item["title"])
            for item in evidence_pack.get("evidence_cards", [])
            if item.get("paper_id") and item.get("title")
        }
        payload = {
            "user_query": user_query,
            "brief": {
                "research_goal": brief.research_goal,
                "search_axes": brief.search_axes,
                "initial_queries": brief.initial_queries,
                "rerank_query": brief.rerank_query,
            },
            "evidence_pack": evidence_pack,
            "report_outline": report_outline,
            "paper_title_map": paper_title_map,
            "draft_report": draft_report,
        }
        response = self.client.models.generate_content(
            model=self.model,
            contents=json.dumps(payload, ensure_ascii=False),
            config=types.GenerateContentConfig(
                system_instruction=REPORT_REPAIR_SYSTEM_PROMPT,
                max_output_tokens=12288,
            ),
        )
        return response.text or ""

    def _build_evidence_pack(
        self,
        user_query: str,
        brief: ResearchBrief,
        selected_papers: list[dict[str, Any]],
        reading_results: list[dict[str, Any]],
        weak_signals: list[dict[str, Any]],
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> dict[str, Any]:
        selected_lookup = {
            (item["conference"], int(item["year"]), item["paper_id"]): item
            for item in selected_papers
        }
        full_read_papers: list[dict[str, Any]] = []
        for item in reading_results:
            if item["read_status"] not in {"completed", "cached"} or not item.get("reading_text"):
                continue
            paper = item["paper"]
            key = (paper["conference"], int(paper["year"]), paper["paper_id"])
            selected = selected_lookup.get(key, {})
            full_read_papers.append(
                {
                    "conference": paper["conference"],
                    "year": int(paper["year"]),
                    "paper_id": paper["paper_id"],
                    "title": paper["title"],
                    "abstract": paper.get("abstract", ""),
                    "authors": paper.get("authors", []),
                    "source_url": paper.get("source_url", ""),
                    "selection_axis": selected.get("axis", ""),
                    "selection_reason": selected.get("reason", ""),
                    "priority": selected.get("priority"),
                    "rerank_score": selected.get("rerank_score"),
                    "coarse_score": selected.get("coarse_score"),
                    "reading_text": item["reading_text"],
                }
            )

        full_read_papers.sort(
            key=lambda item: (
                item.get("priority") is None,
                item.get("priority") or 999999,
                -(item.get("rerank_score") or 0.0),
                item["title"],
            )
        )
        evidence_cards = []
        total_papers = len(full_read_papers)
        for index, item in enumerate(full_read_papers, start=1):
            if progress_callback is not None:
                progress_callback(index - 1, total_papers, f"正在提取证据卡：{item['title']}")
            evidence_cards.append(
                self._build_single_evidence_card(
                    user_query=user_query,
                    brief=brief,
                    paper=item,
                )
            )
            if progress_callback is not None:
                progress_callback(index, total_papers, f"已完成证据卡：{item['title']}")

        summary_payload = {
            "user_query": user_query,
            "brief": {
                "research_goal": brief.research_goal,
                "search_axes": brief.search_axes,
                "rerank_query": brief.rerank_query,
            },
            "evidence_cards": evidence_cards,
            "weak_signals": weak_signals,
        }
        summary = self._generate_json_dict(
            system_instruction=EVIDENCE_PACK_SUMMARY_SYSTEM_PROMPT,
            payload=summary_payload,
            schema=EVIDENCE_PACK_SUMMARY_SCHEMA,
            max_output_tokens=4096,
        )
        return {
            "evidence_cards": evidence_cards,
            "weak_signal_summary": summary["weak_signal_summary"],
            "cross_paper_observations": summary["cross_paper_observations"],
            "evidence_gaps": summary["evidence_gaps"],
        }

    def _build_report_outline(
        self,
        user_query: str,
        brief: ResearchBrief,
        evidence_pack: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "user_query": user_query,
            "brief": {
                "research_goal": brief.research_goal,
                "search_axes": brief.search_axes,
            },
            "evidence_pack": evidence_pack,
            "required_paper_ids": [item["paper_id"] for item in evidence_pack.get("evidence_cards", [])],
        }
        outline = self._generate_json_dict(
            system_instruction=REPORT_OUTLINE_SYSTEM_PROMPT,
            payload=payload,
            schema=REPORT_OUTLINE_SCHEMA,
            max_output_tokens=6144,
        )
        required_ids = [item["paper_id"] for item in evidence_pack.get("evidence_cards", [])]
        paper_analysis_order = [str(item) for item in (outline.get("paper_analysis_order") or []) if str(item)]
        seen: set[str] = set()
        normalized_order: list[str] = []
        for paper_id in paper_analysis_order + required_ids:
            if paper_id in seen:
                continue
            seen.add(paper_id)
            normalized_order.append(paper_id)
        outline["paper_analysis_order"] = normalized_order
        return outline

    def _build_single_evidence_card(
        self,
        *,
        user_query: str,
        brief: ResearchBrief,
        paper: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "user_query": user_query,
            "brief": {
                "research_goal": brief.research_goal,
                "search_axes": brief.search_axes,
                "rerank_query": brief.rerank_query,
            },
            "paper": paper,
        }
        return self._generate_json_dict(
            system_instruction=EVIDENCE_PACK_SYSTEM_PROMPT,
            payload=payload,
            schema=PER_PAPER_EVIDENCE_CARD_SCHEMA,
            max_output_tokens=3072,
        )

    @staticmethod
    def _build_weak_signals(
        rounds: list[SearchRoundResult],
        selected_papers: list[dict[str, Any]],
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        selected_keys = {
            (item["conference"], int(item["year"]), item["paper_id"])
            for item in selected_papers
        }
        merged: dict[tuple[str, int, str], dict[str, Any]] = {}
        for round_item in rounds:
            for item in round_item.reranked_results:
                paper = item["paper"]
                key = (paper["conference"], int(paper["year"]), paper["paper_id"])
                if key in selected_keys:
                    continue
                existing = merged.get(key)
                if existing is None or float(item["rerank_score"]) > float(existing["rerank_score"]):
                    merged[key] = {
                        "conference": paper["conference"],
                        "year": int(paper["year"]),
                        "paper_id": paper["paper_id"],
                        "title": paper["title"],
                        "abstract": paper["abstract"],
                        "rerank_score": float(item["rerank_score"]),
                    }
        values = list(merged.values())
        values.sort(key=lambda item: item["rerank_score"], reverse=True)
        return values[:limit]

    @staticmethod
    def _dedupe_queries(queries: list[str]) -> list[str]:
        results: list[str] = []
        seen: set[str] = set()
        for item in queries:
            value = item.strip()
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            results.append(value)
        return results

    @staticmethod
    def _scope_terms(conferences: list[str] | None, years: list[int] | None) -> list[str]:
        terms: list[str] = []
        all_conference_codes = set(CONFERENCE_DISPLAY_NAMES.keys())
        for conference in conferences or []:
            all_conference_codes.add(conference.strip().lower())
        for conference in sorted(all_conference_codes):
            code = conference.strip().lower()
            if not code:
                continue
            terms.append(code)
            display = CONFERENCE_DISPLAY_NAMES.get(code, "")
            if display:
                terms.append(display.lower())
            if code == "nips":
                terms.append("neurips")
            if code == "neurips":
                terms.append("nips")
        for year in years or []:
            year_str = str(int(year))
            terms.append(year_str)
            if len(year_str) == 4:
                terms.append(year_str[2:])
        deduped: list[str] = []
        seen: set[str] = set()
        for item in terms:
            value = item.strip().lower()
            if not value or value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        return deduped

    @classmethod
    def _sanitize_query_for_scope(
        cls,
        query: str,
        conferences: list[str] | None,
        years: list[int] | None,
    ) -> str:
        value = query.strip()
        if not value:
            return value
        sanitized = value
        for term in cls._scope_terms(conferences, years):
            pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
            sanitized = pattern.sub(" ", sanitized)
        sanitized = re.sub(r"\b(?:19|20)\d{2}\b", " ", sanitized)
        sanitized = re.sub(r"\(\s*\)", " ", sanitized)
        sanitized = re.sub(r"\[\s*\]", " ", sanitized)
        sanitized = QUERY_WHITESPACE_RE.sub(" ", sanitized).strip(" ,;:-")
        return sanitized or value

    @classmethod
    def _sanitize_queries_for_scope(
        cls,
        queries: list[str],
        conferences: list[str] | None,
        years: list[int] | None,
    ) -> list[str]:
        sanitized = [
            cls._sanitize_query_for_scope(
                query=item,
                conferences=conferences,
                years=years,
            )
            for item in queries
        ]
        return cls._dedupe_queries(sanitized)

    @staticmethod
    def _reading_result_to_dict(item: Any) -> dict[str, Any]:
        resolved_source = None
        if item.resolved_source is not None:
            resolved_source = {
                "source": item.resolved_source.source,
                "pdf_url": item.resolved_source.pdf_url,
                "source_url": item.resolved_source.source_url,
                "title": item.resolved_source.title,
                "abstract": item.resolved_source.abstract,
                "authors": item.resolved_source.authors,
            }
        return {
            "paper": item.paper,
            "resolve_status": item.resolve_status,
            "download_status": item.download_status,
            "read_status": item.read_status,
            "local_pdf_path": item.local_pdf_path,
            "resolved_source": resolved_source,
            "reading_text": item.reading_text,
            "error": item.error,
        }
