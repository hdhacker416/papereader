from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Union

from openai import OpenAI
from PyPDF2 import PdfReader

try:
    from backend.services.qwen_service import (
        _append_incomplete_notice,
        _raise_if_incomplete_choice,
        _to_openai_messages,
        _to_turn_history,
    )
except ModuleNotFoundError:
    from services.qwen_service import (
        _append_incomplete_notice,
        _raise_if_incomplete_choice,
        _to_openai_messages,
        _to_turn_history,
    )


DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEEPSEEK_MODEL_PREFIXES = ("deepseek",)
DEEPSEEK_CHAT_TIMEOUT_SECONDS = 300.0
DEEPSEEK_RETRY_ATTEMPTS = 3
DEEPSEEK_RETRY_SLEEP_SECONDS = 3.0
DEFAULT_MAX_PAPER_CHARS = 800_000
DEEPSEEK_PRICING_PER_MILLION = {
    "deepseek-v4-flash": {
        "cache_hit_input": 0.0028,
        "cache_miss_input": 0.14,
        "output": 0.28,
    },
    "deepseek-chat": {
        "cache_hit_input": 0.0028,
        "cache_miss_input": 0.14,
        "output": 0.28,
    },
    "deepseek-reasoner": {
        "cache_hit_input": 0.0028,
        "cache_miss_input": 0.14,
        "output": 0.28,
    },
    "deepseek-v4-pro": {
        "cache_hit_input": 0.003625,
        "cache_miss_input": 0.435,
        "output": 0.87,
    },
}

logger = logging.getLogger(__name__)


def is_deepseek_model(model_name: str | None) -> bool:
    value = str(model_name or "").strip().lower()
    return value.startswith(DEEPSEEK_MODEL_PREFIXES)


def _get_client(api_key: str | None = None, base_url: str | None = None) -> OpenAI:
    resolved_key = api_key or os.getenv("DEEPSEEK_API_KEY")
    if not resolved_key:
        raise ValueError("DEEPSEEK_API_KEY is not configured")
    return OpenAI(
        api_key=resolved_key,
        base_url=base_url or os.getenv("DEEPSEEK_BASE_URL") or DEFAULT_DEEPSEEK_BASE_URL,
    )


def _is_retryable_deepseek_exception(exc: Exception) -> bool:
    message = str(exc)
    lowered = message.lower()
    return (
        "requesttimeout" in message
        or "request timed out" in lowered
        or "timed out" in lowered
        or "read timeout" in lowered
        or "connection reset" in lowered
        or "rate limit" in lowered
        or "insufficient_system_resource" in lowered
    )


def _thinking_config(model_name: str) -> dict[str, Any]:
    lowered = str(model_name or "").strip().lower()
    if lowered in {"deepseek-reasoner"}:
        return {"thinking": {"type": "enabled"}}
    value = os.getenv("DEEPSEEK_THINKING", "disabled").strip().lower()
    if value in {"1", "true", "yes", "on", "enabled"}:
        value = "enabled"
    else:
        value = "disabled"
    return {"thinking": {"type": value}}


def _create_chat_completion_with_retry(
    client: OpenAI,
    *,
    model: str,
    messages: list[dict[str, str]],
    response_format: dict[str, str] | None = None,
    max_tokens: int | None = None,
):
    last_exc: Exception | None = None
    for attempt in range(1, DEEPSEEK_RETRY_ATTEMPTS + 1):
        try:
            kwargs: dict[str, Any] = {
                "model": model or DEFAULT_DEEPSEEK_MODEL,
                "messages": messages,
                "timeout": DEEPSEEK_CHAT_TIMEOUT_SECONDS,
                "extra_body": _thinking_config(model or DEFAULT_DEEPSEEK_MODEL),
            }
            if response_format is not None:
                kwargs["response_format"] = response_format
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            return client.chat.completions.create(**kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt >= DEEPSEEK_RETRY_ATTEMPTS or not _is_retryable_deepseek_exception(exc):
                raise
            sleep_seconds = DEEPSEEK_RETRY_SLEEP_SECONDS * attempt
            logger.warning(
                "Retryable DeepSeek completion error on attempt %s/%s for model %s: %s. Sleeping %.1fs before retry.",
                attempt,
                DEEPSEEK_RETRY_ATTEMPTS,
                model,
                exc,
                sleep_seconds,
            )
            time.sleep(sleep_seconds)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("DeepSeek completion failed without a captured exception")


def _usage_value(usage: Any, key: str) -> int:
    if not usage:
        return 0
    if isinstance(usage, dict):
        value = usage.get(key)
    else:
        value = getattr(usage, key, None)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _calculate_cost(usage: Any, model_name: str) -> float:
    if not usage:
        return 0.0

    lowered = str(model_name or DEFAULT_DEEPSEEK_MODEL).strip().lower()
    pricing = DEEPSEEK_PRICING_PER_MILLION.get(lowered)
    if pricing is None:
        return 0.0

    prompt_tokens = _usage_value(usage, "prompt_tokens")
    cache_hit_tokens = _usage_value(usage, "prompt_cache_hit_tokens")
    cache_miss_tokens = _usage_value(usage, "prompt_cache_miss_tokens")
    completion_tokens = _usage_value(usage, "completion_tokens")

    # Older OpenAI-compatible responses may omit the cache split.
    if prompt_tokens and not cache_hit_tokens and not cache_miss_tokens:
        cache_miss_tokens = prompt_tokens

    return (
        cache_hit_tokens / 1_000_000 * pricing["cache_hit_input"]
        + cache_miss_tokens / 1_000_000 * pricing["cache_miss_input"]
        + completion_tokens / 1_000_000 * pricing["output"]
    )


def _max_paper_chars() -> int:
    raw_value = os.getenv("DEEPSEEK_MAX_PAPER_CHARS")
    if not raw_value:
        return DEFAULT_MAX_PAPER_CHARS
    try:
        return max(20_000, int(raw_value))
    except ValueError:
        return DEFAULT_MAX_PAPER_CHARS


def extract_pdf_text(pdf_path: str, max_chars: int | None = None) -> str:
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {pdf_path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError("Only PDF files are supported")

    limit = max_chars or _max_paper_chars()
    reader = PdfReader(str(path))
    chunks: list[str] = []
    total_chars = 0
    truncated = False
    for page_index, page in enumerate(reader.pages, start=1):
        page_text = (page.extract_text() or "").strip()
        if not page_text:
            continue
        chunk = f"\n\n[Page {page_index}]\n{page_text}"
        remaining = limit - total_chars
        if remaining <= 0:
            truncated = True
            break
        if len(chunk) > remaining:
            chunks.append(chunk[:remaining])
            total_chars += remaining
            truncated = True
            break
        chunks.append(chunk)
        total_chars += len(chunk)

    text = "".join(chunks).strip()
    if not text:
        raise ValueError(
            "Could not extract text from PDF for DeepSeek. "
            "DeepSeek's API does not provide native PDF upload/OCR, so scanned or image-only PDFs are not supported."
        )
    if truncated:
        text += "\n\n[Content truncated because DEEPSEEK_MAX_PAPER_CHARS was reached.]"
    return text


def _paper_context_system_message(pdf_path: str, paper_text: str) -> dict[str, str]:
    return {
        "role": "system",
        "content": (
            "你是一名学术论文阅读助手。你必须严格基于下面从 PDF 抽取出的论文文本回答，"
            "不要编造不存在的信息。如果文本不足以支持结论，要明确说明不确定。\n\n"
            f"PDF 文件名：{Path(pdf_path).name}\n\n"
            "<paper_text>\n"
            f"{paper_text}\n"
            "</paper_text>"
        ),
    }


def _chat_with_pdf_text(
    *,
    client: OpenAI,
    pdf_path: str,
    paper_text: str,
    history: Union[List[Dict], Dict],
    message: str,
    model_name: str,
    max_tokens: int | None = None,
) -> tuple[str, Dict[str, Any], float, float]:
    t0 = time.time()
    prior_messages = _to_openai_messages(history)
    messages = [
        _paper_context_system_message(pdf_path, paper_text),
        *prior_messages,
        {"role": "user", "content": message},
    ]
    response = _create_chat_completion_with_retry(
        client,
        model=model_name or DEFAULT_DEEPSEEK_MODEL,
        messages=messages,
        max_tokens=max_tokens,
    )
    choice = response.choices[0]
    content = choice.message.content
    response_text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    response_text = _append_incomplete_notice(choice, response_text)
    cost = _calculate_cost(getattr(response, "usage", None), model_name)
    time_cost = time.time() - t0
    updated_messages = _to_openai_messages(history)
    updated_messages.append({"role": "user", "content": message})
    updated_messages.append({"role": "assistant", "content": response_text})
    updated_history = _to_turn_history(updated_messages)
    if isinstance(history, dict):
        prior_turns = history.get("turns") or []
        for index, turn in enumerate(updated_history["turns"][: len(prior_turns)]):
            meta = (prior_turns[index] or {}).get("meta")
            if meta:
                turn["meta"] = meta
    if updated_history["turns"]:
        updated_history["turns"][-1]["meta"] = {
            "cost": cost,
            "time_cost": time_cost,
            "model_name": model_name,
        }
    return response_text, updated_history, cost, time_cost


def complete_text(
    *,
    model_name: str,
    system_instruction: str,
    user_content: str,
    api_key: str | None = None,
    max_tokens: int | None = None,
) -> str:
    client = _get_client(api_key=api_key)
    response = _create_chat_completion_with_retry(
        client,
        model=model_name or DEFAULT_DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_content},
        ],
        max_tokens=max_tokens,
    )
    choice = response.choices[0]
    content = choice.message.content
    response_text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    _raise_if_incomplete_choice(choice, response_text)
    return response_text


def complete_json(
    *,
    model_name: str,
    system_instruction: str,
    user_content: str,
    api_key: str | None = None,
    max_tokens: int | None = None,
) -> str:
    client = _get_client(api_key=api_key)
    response = _create_chat_completion_with_retry(
        client,
        model=model_name or DEFAULT_DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": f"{system_instruction}\n请严格输出 JSON。"},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        max_tokens=max_tokens,
    )
    choice = response.choices[0]
    content = choice.message.content
    response_text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    _raise_if_incomplete_choice(choice, response_text)
    return response_text


def chat_with_paper(
    pdf_path: str,
    history: Union[List[Dict], Dict],
    message: str,
    model_name: str = DEFAULT_DEEPSEEK_MODEL,
) -> tuple[str, Dict[str, Any], float, float]:
    client = _get_client()
    paper_text = extract_pdf_text(pdf_path)
    return _chat_with_pdf_text(
        client=client,
        pdf_path=pdf_path,
        paper_text=paper_text,
        history=history,
        message=message,
        model_name=model_name,
    )


def interpret_paper(
    pdf_path: str,
    template_prompts: List[str],
    model_name: str = DEFAULT_DEEPSEEK_MODEL,
) -> tuple[str, List[Dict]]:
    client = _get_client()
    paper_text = extract_pdf_text(pdf_path)
    history: dict[str, Any] = {"cache": None, "turns": []}
    full_response = ""
    for index, prompt_text in enumerate(template_prompts, start=1):
        response_text, history, _, _ = _chat_with_pdf_text(
            client=client,
            pdf_path=pdf_path,
            paper_text=paper_text,
            history=history,
            message=prompt_text,
            model_name=model_name,
        )
        full_response += f"## 第 {index} 步\n\n**提示词：** {prompt_text}\n\n**回答：**\n{response_text}\n\n---\n\n"
    return full_response, history["turns"]
