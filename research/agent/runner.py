from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from google import genai
from google.genai import types

from research.agent.tool_runner import ToolRunner
from research.agent.toolspec import get_gemini_tools


DEFAULT_AGENT_MODEL = "gemini-3-flash-preview"


@dataclass(frozen=True)
class AgentRunResult:
    final_text: str
    tool_calls: list[dict[str, Any]]


class ResearchAgentRunner:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_AGENT_MODEL,
        tool_runner: ToolRunner | None = None,
    ) -> None:
        api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        self.client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
        self.model = model
        self.tool_runner = tool_runner or ToolRunner()

    def run(
        self,
        user_query: str,
        system_prompt: str | None = None,
        max_rounds: int = 8,
    ) -> AgentRunResult:
        contents: list[types.Content] = [
            types.Content(role="user", parts=[types.Part.from_text(text=user_query)])
        ]
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=get_gemini_tools(),
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="AUTO")
            ),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        tool_log: list[dict[str, Any]] = []

        for _ in range(max_rounds):
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )

            candidate = response.candidates[0] if response.candidates else None
            parts = candidate.content.parts if candidate and candidate.content and candidate.content.parts else []
            function_call_parts = [part for part in parts if getattr(part, "function_call", None)]
            function_calls = [part.function_call for part in function_call_parts]

            if not function_calls:
                final_text_parts = [part.text for part in parts if getattr(part, "text", None)]
                final_text = "".join(final_text_parts).strip()
                return AgentRunResult(final_text=final_text, tool_calls=tool_log)

            tool_response_parts = []
            for part, call in zip(function_call_parts, function_calls, strict=True):
                result = self.tool_runner.run(call.name, _json_dump(call.args or {}))
                tool_log.append(
                    {
                        "tool_name": call.name,
                        "arguments": dict(call.args or {}),
                        "output": result.output,
                    }
                )
                tool_response_parts.append(
                    types.Part.from_function_response(
                        name=call.name,
                        response=result.output,
                    )
                )

            contents.append(types.Content(role="model", parts=function_call_parts))
            contents.append(types.Content(role="user", parts=tool_response_parts))

        raise RuntimeError("Agent did not finish within max_rounds")


def _json_dump(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)
