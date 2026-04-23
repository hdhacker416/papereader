from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from research.tools.search_tools import SearchTools


@dataclass(frozen=True)
class ToolCallResult:
    tool_name: str
    output: dict[str, Any]


class ToolRunner:
    def __init__(self, search_tools: SearchTools | None = None) -> None:
        self.search_tools = search_tools or SearchTools()

    def run(self, tool_name: str, arguments_json: str) -> ToolCallResult:
        args = json.loads(arguments_json or "{}")
        if tool_name == "coarse_search":
            output = self.search_tools.coarse_search(**args)
        elif tool_name == "rerank_search":
            output = self.search_tools.rerank_search(**args)
        elif tool_name == "get_paper_details":
            output = self.search_tools.get_paper_details(**args)
        else:
            raise ValueError(f"Unknown tool: {tool_name}")
        return ToolCallResult(tool_name=tool_name, output=output)
