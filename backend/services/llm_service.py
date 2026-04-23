from __future__ import annotations

from typing import Any, Dict, List, Union

try:
    from backend.services import gemini_service, qwen_service
except ModuleNotFoundError:
    from services import gemini_service, qwen_service


def is_qwen_model(model_name: str | None) -> bool:
    return qwen_service.is_qwen_model(model_name)


def is_gemini_model(model_name: str | None) -> bool:
    return qwen_service.is_gemini_model(model_name)


def chat_with_paper(
    pdf_path: str,
    history: Union[List[Dict], Dict],
    message: str,
    model_name: str = "gemini-3-flash-preview",
) -> tuple[str, Dict[str, Any], float, float]:
    if is_qwen_model(model_name):
        return qwen_service.chat_with_paper(pdf_path, history, message, model_name=model_name)
    return gemini_service.chat_with_paper(pdf_path, history, message, model_name=model_name)


def interpret_paper(
    pdf_path: str,
    template_prompts: List[str],
    model_name: str = "gemini-3-flash-preview",
) -> tuple[str, List[Dict]]:
    if is_qwen_model(model_name):
        return qwen_service.interpret_paper(pdf_path, template_prompts, model_name=model_name)
    return gemini_service.interpret_paper(pdf_path, template_prompts, model_name=model_name)
