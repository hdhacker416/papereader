from __future__ import annotations

from google.genai import types


def get_tool_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "name": "coarse_search",
            "description": "Run embedding-based coarse search over the prepared conference paper assets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "conferences": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                    },
                    "years": {
                        "type": ["array", "null"],
                        "items": {"type": "integer"},
                    },
                    "top_k_per_asset": {"type": "integer", "default": 10},
                    "top_k_global": {"type": "integer", "default": 50},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "rerank_search",
            "description": "Run API-based reranking over coarse search candidates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "candidates": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "top_n": {"type": "integer", "default": 20},
                },
                "required": ["query", "candidates"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "get_paper_details",
            "description": "Fetch detailed metadata for specific papers by conference, year, and paper_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "paper_refs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "conference": {"type": "string"},
                                "year": {"type": "integer"},
                                "paper_id": {"type": "string"},
                            },
                            "required": ["conference", "year", "paper_id"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["paper_refs"],
                "additionalProperties": False,
            },
        },
    ]


def get_chat_tool_schemas() -> list[dict]:
    schemas = get_tool_schemas()
    chat_tools = []
    for item in schemas:
        chat_tools.append(
            {
                "type": "function",
                "function": {
                    "name": item["name"],
                    "description": item["description"],
                    "parameters": item["parameters"],
                },
            }
        )
    return chat_tools


def get_gemini_tools() -> list[types.Tool]:
    declarations = []
    for item in get_tool_schemas():
        declarations.append(
            types.FunctionDeclaration(
                name=item["name"],
                description=item["description"],
                parameters_json_schema=item["parameters"],
            )
        )
    return [types.Tool(function_declarations=declarations)]
