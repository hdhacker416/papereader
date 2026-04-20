from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Union

from openai import OpenAI


DEFAULT_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_QWEN_MODEL = "qwen-plus"
DEFAULT_QWEN_PAPER_MODEL = "qwen-long"
QWEN_MODEL_PREFIXES = ("qwen", "qwq")
QWEN_FILE_CAPABLE_MODELS = {"qwen-long", "qwen-doc-turbo"}
QWEN_PAPER_MODEL_ALIASES = {
    "qwen-flash": DEFAULT_QWEN_PAPER_MODEL,
    "qwen-plus": DEFAULT_QWEN_PAPER_MODEL,
    "qwen-max": DEFAULT_QWEN_PAPER_MODEL,
}
FILE_PROCESSING_POLL_SECONDS = 2.0
FILE_PROCESSING_TIMEOUT_SECONDS = 120.0

logger = logging.getLogger(__name__)


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


def _resolve_qwen_paper_model(model_name: str | None) -> str:
    resolved = str(model_name or "").strip().lower()
    if resolved in QWEN_FILE_CAPABLE_MODELS:
        return resolved
    return QWEN_PAPER_MODEL_ALIASES.get(resolved, DEFAULT_QWEN_PAPER_MODEL)


def _upload_file_for_extract(client: OpenAI, pdf_path: str) -> str:
    file_object = client.files.create(file=Path(pdf_path), purpose="file-extract")
    file_id = getattr(file_object, "id", None)
    if not file_id:
        raise ValueError(f"DashScope file upload did not return a file id for {pdf_path}")
    return str(file_id)


def _wait_until_file_processed(client: OpenAI, file_id: str) -> None:
    deadline = time.time() + FILE_PROCESSING_TIMEOUT_SECONDS
    last_status = None
    while time.time() < deadline:
        file_object = client.files.retrieve(file_id=file_id)
        status = str(getattr(file_object, "status", "") or "").strip().lower()
        if status == "processed":
            return
        if status in {"failed", "error"}:
            details = getattr(file_object, "status_details", None)
            raise ValueError(f"DashScope file parsing failed for {file_id}: {details or status}")
        last_status = status or "unknown"
        time.sleep(FILE_PROCESSING_POLL_SECONDS)
    raise ValueError(
        f"DashScope file parsing timed out for {file_id} after {FILE_PROCESSING_TIMEOUT_SECONDS:.0f}s"
        f" (last status: {last_status or 'unknown'})"
    )


def _delete_uploaded_file(client: OpenAI, file_id: str) -> None:
    try:
        client.files.delete(file_id)
    except Exception as exc:
        logger.warning("Failed to delete DashScope uploaded file %s: %s", file_id, exc)


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


def _chat_with_uploaded_file(
    *,
    client: OpenAI,
    file_id: str,
    history: Union[List[Dict], Dict],
    message: str,
    model_name: str,
) -> tuple[str, Dict[str, Any], float, float]:
    t0 = time.time()
    prior_messages = _to_openai_messages(history)
    messages = [
        {"role": "system", "content": "你是一名学术论文阅读助手。你必须严格基于上传的论文内容回答，不要编造不存在的信息。如果论文内容不足以支持结论，要明确说明不确定。"},
        {"role": "system", "content": f"fileid://{file_id}"},
        *prior_messages,
        {"role": "user", "content": message},
    ]
    effective_model = _resolve_qwen_paper_model(model_name)
    response = client.chat.completions.create(
        model=effective_model,
        messages=messages,
    )
    content = response.choices[0].message.content
    response_text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    updated_messages = _to_openai_messages(history)
    updated_messages.append({"role": "user", "content": message})
    updated_messages.append({"role": "assistant", "content": response_text})
    updated_history = _to_turn_history(updated_messages)
    return response_text, updated_history, 0.0, time.time() - t0


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
    client = _get_client()
    file_id = _upload_file_for_extract(client, pdf_path)
    try:
        _wait_until_file_processed(client, file_id)
        return _chat_with_uploaded_file(
            client=client,
            file_id=file_id,
            history=history,
            message=message,
            model_name=model_name,
        )
    finally:
        _delete_uploaded_file(client, file_id)


def interpret_paper(
    pdf_path: str,
    template_prompts: List[str],
    model_name: str = DEFAULT_QWEN_MODEL,
) -> tuple[str, List[Dict]]:
    client = _get_client()
    file_id = _upload_file_for_extract(client, pdf_path)
    history: dict[str, Any] = {"cache": None, "turns": []}
    full_response = ""
    try:
        _wait_until_file_processed(client, file_id)
        for index, prompt_text in enumerate(template_prompts, start=1):
            response_text, history, _, _ = _chat_with_uploaded_file(
                client=client,
                file_id=file_id,
                history=history,
                message=prompt_text,
                model_name=model_name,
            )
            full_response += f"## Step {index}\n\n**Prompt:** {prompt_text}\n\n**Response:**\n{response_text}\n\n---\n\n"
        return full_response, history["turns"]
    finally:
        _delete_uploaded_file(client, file_id)
