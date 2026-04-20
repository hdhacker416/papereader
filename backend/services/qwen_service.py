from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from openai import OpenAI
from PyPDF2 import PdfReader


DEFAULT_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_QWEN_MODEL = "qwen-plus"
QWEN_MODEL_PREFIXES = ("qwen", "qwq")
MAX_PAPER_TEXT_CHARS = 80000


def is_qwen_model(model_name: str | None) -> bool:
    value = str(model_name or "").strip().lower()
    return value.startswith(QWEN_MODEL_PREFIXES)


def is_gemini_model(model_name: str | None) -> bool:
    value = str(model_name or "").strip().lower()
    return value.startswith("gemini")


def _get_client(api_key: str | None = None, base_url: str | None = None) -> OpenAI:
    resolved_key = api_key or os.getenv("DASHSCOPE_API_KEY")
    if not resolved_key:
        raise ValueError("DASHSCOPE_API_KEY is not configured")
    return OpenAI(
        api_key=resolved_key,
        base_url=base_url or os.getenv("DASHSCOPE_BASE_URL") or DEFAULT_DASHSCOPE_BASE_URL,
    )


def _extract_pdf_text_with_pdftotext(pdf_path: str) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", pdf_path, "-"],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout


def _extract_pdf_text_with_pypdf(pdf_path: str) -> str:
    reader = PdfReader(pdf_path)
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def extract_pdf_text(pdf_path: str) -> str:
    path = Path(pdf_path)
    cache_path = path.with_suffix(".txt")
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    text = ""
    try:
        text = _extract_pdf_text_with_pdftotext(pdf_path)
    except Exception:
        text = _extract_pdf_text_with_pypdf(pdf_path)

    normalized = text.strip()
    if not normalized:
        raise ValueError(f"Failed to extract text from PDF: {pdf_path}")
    cache_path.write_text(normalized, encoding="utf-8")
    return normalized


def _truncate_paper_text(text: str, limit: int = MAX_PAPER_TEXT_CHARS) -> str:
    normalized = text.strip()
    if len(normalized) <= limit:
        return normalized
    head = normalized[: int(limit * 0.75)]
    tail = normalized[-int(limit * 0.25) :]
    return f"{head}\n\n[...内容已截断...]\n\n{tail}"


def _paper_system_prompt(pdf_path: str) -> str:
    paper_text = _truncate_paper_text(extract_pdf_text(pdf_path))
    return (
        "你是一名学术论文阅读助手。你必须严格基于给定论文内容回答，不要编造不存在的信息。"
        "如果论文内容不足以支持结论，要明确说明不确定。\n\n"
        "下面是论文提取出的文本内容：\n"
        f"{paper_text}"
    )


def _to_openai_messages(history: Union[List[Dict[str, str]], Dict[str, Any], None]) -> list[dict[str, str]]:
    if not history:
        return []
    if isinstance(history, list):
        messages: list[dict[str, str]] = []
        for item in history:
            role = str(item.get("role") or "").strip()
            content = str(item.get("content") or "").strip()
            if role and content:
                messages.append({"role": "assistant" if role == "model" else role, "content": content})
        return messages

    turns = history.get("turns") or []
    messages = []
    for turn in turns:
        user_item = turn.get("user") or {}
        model_item = turn.get("model") or {}
        user_parts = user_item.get("parts") or []
        model_parts = model_item.get("parts") or []
        user_text = str((user_parts[0] or {}).get("text") or "").strip() if user_parts else ""
        model_text = str((model_parts[0] or {}).get("text") or "").strip() if model_parts else ""
        if user_text:
            messages.append({"role": "user", "content": user_text})
        if model_text:
            messages.append({"role": "assistant", "content": model_text})
    return messages


def _to_turn_history(messages: list[dict[str, str]]) -> dict[str, Any]:
    turns: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for message in messages:
        role = message["role"]
        content = message["content"]
        if role == "user":
            if current:
                turns.append(current)
                current = {}
            current["user"] = {"role": "user", "parts": [{"text": content}]}
        elif role == "assistant":
            current["model"] = {"role": "model", "parts": [{"text": content}]}
            turns.append(current)
            current = {}
    if current:
        turns.append(current)
    return {"cache": None, "turns": turns}


def complete_text(
    *,
    model_name: str,
    system_instruction: str,
    user_content: str,
    api_key: str | None = None,
) -> str:
    client = _get_client(api_key=api_key)
    response = client.chat.completions.create(
        model=model_name or DEFAULT_QWEN_MODEL,
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_content},
        ],
    )
    content = response.choices[0].message.content
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)


def complete_json(
    *,
    model_name: str,
    system_instruction: str,
    user_content: str,
    api_key: str | None = None,
) -> str:
    client = _get_client(api_key=api_key)
    response = client.chat.completions.create(
        model=model_name or DEFAULT_QWEN_MODEL,
        messages=[
            {"role": "system", "content": f"{system_instruction}\n请严格输出 JSON。"},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)


def chat_with_paper(
    pdf_path: str,
    history: Union[List[Dict], Dict],
    message: str,
    model_name: str = DEFAULT_QWEN_MODEL,
) -> tuple[str, Dict[str, Any], float, float]:
    t0 = time.time()
    messages = _to_openai_messages(history)
    messages = [
        {"role": "system", "content": _paper_system_prompt(pdf_path)},
        *messages,
        {"role": "user", "content": message},
    ]
    client = _get_client()
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
    )
    content = response.choices[0].message.content
    response_text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    updated_messages = _to_openai_messages(history)
    updated_messages.append({"role": "user", "content": message})
    updated_messages.append({"role": "assistant", "content": response_text})
    updated_history = _to_turn_history(updated_messages)
    return response_text, updated_history, 0.0, time.time() - t0


def interpret_paper(
    pdf_path: str,
    template_prompts: List[str],
    model_name: str = DEFAULT_QWEN_MODEL,
) -> tuple[str, List[Dict]]:
    history: dict[str, Any] = {"cache": None, "turns": []}
    full_response = ""
    for index, prompt_text in enumerate(template_prompts, start=1):
        response_text, history, _, _ = chat_with_paper(
            pdf_path=pdf_path,
            history=history,
            message=prompt_text,
            model_name=model_name,
        )
        full_response += f"## Step {index}\n\n**Prompt:** {prompt_text}\n\n**Response:**\n{response_text}\n\n---\n\n"
    return full_response, history["turns"]
