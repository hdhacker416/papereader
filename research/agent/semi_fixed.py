from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from google import genai
from google.genai import types

from research.reader.paper_reader import PaperReader
from research.targeting import normalize_target_years
from research.tools.search_tools import SearchTools


DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"
REPORT_SYSTEM_PROMPT = (
    "You are writing a deep-research style academic report in Chinese. "
    "Base the report only on the provided retrieval results and paper reading notes. "
    "Treat full-paper reading notes as higher-confidence evidence than title/abstract retrieval results. "
    "Never invent experiments, numbers, methods, or conclusions that are not supported by the inputs. "
    "If only title/abstract evidence is available for a paper, explicitly present it as a weaker signal. "
    "Do not write a detailed subsection for an unread paper. "
    "Write the report in Markdown with exactly these top-level sections: "
    "1. Executive Summary "
    "2. Directions "
    "3. Paper Analyses "
    "4. Synthesis "
    "5. Limitations. "
    "In Executive Summary, give 4-6 high-signal bullets. "
    "In Directions, list 3-5 research directions and, for each one, explain why it matters and which papers support it. "
    "In Paper Analyses, only include papers with full-paper reading notes; for each paper, summarize problem, method, strongest evidence, limitations, and why it matters for the user's question. "
    "In Synthesis, compare attack-side and defense-side trends, note any missing prompt-injection evidence, and explain what appears mature versus early. "
    "In Limitations, state exactly what this report could not verify because some papers were not fully read."
)


PLANNER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "main_goal": {"type": "string"},
        "sub_queries": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 3,
        },
        "rerank_query": {"type": "string"},
        "target_conferences": {
            "type": "array",
            "items": {"type": "string"},
        },
        "target_years": {
            "type": "array",
            "items": {"type": "integer"},
        },
    },
    "required": [
        "main_goal",
        "sub_queries",
        "rerank_query",
        "target_conferences",
        "target_years",
    ],
}


@dataclass(frozen=True)
class SearchPlan:
    main_goal: str
    sub_queries: list[str]
    rerank_query: str
    target_conferences: list[str]
    target_years: list[int]


@dataclass(frozen=True)
class SemiFixedRunResult:
    plan: SearchPlan
    coarse_results: list[dict[str, Any]]
    merged_candidates: list[dict[str, Any]]
    reranked_results: list[dict[str, Any]]
    detail_results: list[dict[str, Any]]
    reading_results: list[dict[str, Any]]
    final_text: str


class SemiFixedResearchRunner:
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

    def plan(
        self,
        user_query: str,
        conferences: list[str] | None = None,
        years: list[int] | None = None,
    ) -> SearchPlan:
        effective_years = normalize_target_years(
            years,
            available_years=[asset.year for asset in self.search_tools.assets],
        )
        prompt = (
            "You are planning an academic paper search. "
            "Return a compact JSON plan for semantic retrieval. "
            "Do not answer the user question. "
            "sub_queries should be short retrieval-oriented queries. "
            "rerank_query should be one unified ranking query. "
            "Prefer the user-specified conferences and years when provided."
        )
        user_payload = {
            "user_query": user_query,
            "preferred_conferences": conferences or [],
            "preferred_years": effective_years,
        }
        response = self.client.models.generate_content(
            model=self.model,
            contents=json.dumps(user_payload, ensure_ascii=False),
            config=types.GenerateContentConfig(
                system_instruction=prompt,
                response_mime_type="application/json",
                response_json_schema=PLANNER_SCHEMA,
            ),
        )
        plan_data = json.loads(response.text)
        return SearchPlan(
            main_goal=plan_data["main_goal"],
            sub_queries=[item.strip() for item in plan_data["sub_queries"] if item.strip()],
            rerank_query=plan_data["rerank_query"].strip(),
            target_conferences=[item.lower() for item in plan_data["target_conferences"]],
            target_years=effective_years if years is None else [int(item) for item in plan_data["target_years"]],
        )

    def run(
        self,
        user_query: str,
        conferences: list[str] | None = None,
        years: list[int] | None = None,
        top_k_per_asset: int = 8,
        top_k_global: int = 15,
        rerank_top_n: int = 12,
        details_top_n: int = 8,
        read_top_n: int = 5,
        reading_prompts_override: list[str] | None = None,
    ) -> SemiFixedRunResult:
        effective_years = normalize_target_years(
            years,
            available_years=[asset.year for asset in self.search_tools.assets],
        )
        plan = self.plan(user_query, conferences=conferences, years=years)

        coarse_results: list[dict[str, Any]] = []
        for sub_query in plan.sub_queries:
            coarse = self.search_tools.coarse_search(
                query=sub_query,
                conferences=plan.target_conferences,
                years=effective_years,
                top_k_per_asset=top_k_per_asset,
                top_k_global=top_k_global,
            )
            coarse_results.append(
                {
                    "sub_query": sub_query,
                    "results": coarse["results"],
                    "elapsed_sec": coarse["elapsed_sec"],
                }
            )

        merged_candidates = self._merge_candidates(coarse_results)
        reranked = self.search_tools.rerank_search(
            query=plan.rerank_query,
            candidates=merged_candidates,
            top_n=rerank_top_n,
        )
        reranked_results = reranked["results"]

        paper_refs = [
            {
                "conference": item["paper"]["conference"],
                "year": item["paper"]["year"],
                "paper_id": item["paper"]["paper_id"],
            }
            for item in reranked_results[:details_top_n]
        ]
        details = self.search_tools.get_paper_details(paper_refs)
        detail_results = details["results"]
        reading_results = [
            self._reading_result_to_dict(item)
            for item in self.paper_reader.read_papers(
                papers=detail_results[:read_top_n],
                user_query=user_query,
                template_prompts=reading_prompts_override,
            )
        ]

        final_text = self._summarize(
            user_query=user_query,
            plan=plan,
            reranked_results=reranked_results,
            detail_results=detail_results,
            reading_results=reading_results,
        )
        return SemiFixedRunResult(
            plan=plan,
            coarse_results=coarse_results,
            merged_candidates=merged_candidates,
            reranked_results=reranked_results,
            detail_results=detail_results,
            reading_results=reading_results,
            final_text=final_text,
        )

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

    def _summarize(
        self,
        user_query: str,
        plan: SearchPlan,
        reranked_results: list[dict[str, Any]],
        detail_results: list[dict[str, Any]],
        reading_results: list[dict[str, Any]],
    ) -> str:
        payload = {
            "user_query": user_query,
            "plan": {
                "main_goal": plan.main_goal,
                "sub_queries": plan.sub_queries,
                "rerank_query": plan.rerank_query,
                "target_conferences": plan.target_conferences,
                "target_years": plan.target_years,
            },
            "reranked_results": reranked_results,
            "detail_results": detail_results,
            "reading_results": reading_results,
        }
        response = self.client.models.generate_content(
            model=self.model,
            contents=json.dumps(payload, ensure_ascii=False),
            config=types.GenerateContentConfig(
                system_instruction=REPORT_SYSTEM_PROMPT,
                max_output_tokens=4096,
            ),
        )
        return response.text or ""

    def _reading_result_to_dict(self, item: Any) -> dict[str, Any]:
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
