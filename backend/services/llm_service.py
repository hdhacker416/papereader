from __future__ import annotations

from typing import Any, Dict, List, Union

try:
    from backend.services import qwen_service
except ModuleNotFoundError:
    from services import qwen_service


def is_qwen_model(model_name: str | None) -> bool:
    return qwen_service.is_qwen_model(model_name)


def is_gemini_model(model_name: str | None) -> bool:
    return qwen_service.is_gemini_model(model_name)


def is_deepseek_model(model_name: str | None) -> bool:
    return False


def _qwen_model_or_default(model_name: str | None) -> str:
    return model_name if qwen_service.is_qwen_model(model_name) else qwen_service.DEFAULT_QWEN_MODEL


def chat_with_paper(
    pdf_path: str,
    history: Union[List[Dict], Dict],
    message: str,
    model_name: str = "qwen-plus",
) -> tuple[str, Dict[str, Any], float, float]:
    return qwen_service.chat_with_paper(pdf_path, history, message, model_name=_qwen_model_or_default(model_name))


def interpret_paper(
    pdf_path: str,
    template_prompts: List[str],
    model_name: str = "qwen-plus",
) -> tuple[str, List[Dict]]:
    return qwen_service.interpret_paper(pdf_path, template_prompts, model_name=_qwen_model_or_default(model_name))
