from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import requests
from dotenv import dotenv_values, set_key, unset_key
from fastapi import APIRouter, HTTPException
from google import genai
from google.genai import types
from pydantic import BaseModel

try:
    from backend.services import deepseek_service
    from research.providers.dashscope_embedding import DashScopeEmbeddingClient
except ModuleNotFoundError:
    from services import deepseek_service
    from research.providers.dashscope_embedding import DashScopeEmbeddingClient


ProviderName = Literal["gemini", "deepseek", "dashscope", "github"]

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
PROVIDERS: dict[str, dict[str, str]] = {
    "gemini": {
        "label": "Gemini",
        "env_var": "GEMINI_API_KEY",
        "hint": "Paper reading, paper chat, task reports, and Deep Research with Gemini models.",
    },
    "deepseek": {
        "label": "DeepSeek",
        "env_var": "DEEPSEEK_API_KEY",
        "hint": "Paper reading, paper chat, task reports, and Deep Research with DeepSeek models.",
    },
    "dashscope": {
        "label": "DashScope",
        "env_var": "DASHSCOPE_API_KEY",
        "hint": "Qwen models, embeddings, rerank, pack build, and research search workflows.",
    },
    "github": {
        "label": "GitHub",
        "env_var": "GITHUB_TOKEN",
        "hint": "Optional token for uploading research packs to GitHub Releases.",
    },
}


class ApiKeyInfo(BaseModel):
    provider: str
    label: str
    env_var: str
    configured: bool
    masked_value: str | None = None
    hint: str | None = None


class ApiKeyListResponse(BaseModel):
    keys: list[ApiKeyInfo]


class ApiKeyUpdateRequest(BaseModel):
    value: str


class ApiKeyUpdateResponse(BaseModel):
    ok: bool
    key: ApiKeyInfo


class ApiKeyCheckResponse(BaseModel):
    provider: str
    status: Literal["ok", "warning", "error"]
    message: str


router = APIRouter(
    prefix="/api/settings",
    tags=["settings"],
)


def _load_env_values() -> dict[str, str]:
    values = dotenv_values(ENV_PATH) if ENV_PATH.exists() else {}
    result: dict[str, str] = {}
    for key, value in values.items():
        if value is not None:
            result[key] = value
    return result


def _provider_config(provider: str) -> dict[str, str]:
    config = PROVIDERS.get(provider)
    if not config:
        raise HTTPException(status_code=404, detail="Unknown API key provider")
    return config


def _mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    clean = value.strip()
    if len(clean) <= 8:
        return f"{clean[:2]}...{clean[-2:]}" if len(clean) > 4 else "****"
    return f"{clean[:4]}...{clean[-4:]}"


def _key_info(provider: str, env_values: dict[str, str] | None = None) -> ApiKeyInfo:
    config = _provider_config(provider)
    env_var = config["env_var"]
    values = env_values if env_values is not None else _load_env_values()
    value = values.get(env_var) or os.getenv(env_var)
    configured = bool(value and value.strip())
    return ApiKeyInfo(
        provider=provider,
        label=config["label"],
        env_var=env_var,
        configured=configured,
        masked_value=_mask_secret(value) if configured else None,
        hint=config.get("hint"),
    )


def _write_key(provider: str, value: str) -> ApiKeyInfo:
    clean_value = value.strip()
    if not clean_value:
        raise HTTPException(status_code=400, detail="API key value cannot be empty")

    config = _provider_config(provider)
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not ENV_PATH.exists():
        ENV_PATH.write_text("", encoding="utf-8")
    set_key(str(ENV_PATH), config["env_var"], clean_value)
    os.environ[config["env_var"]] = clean_value
    return _key_info(provider)


def _delete_key(provider: str) -> ApiKeyInfo:
    config = _provider_config(provider)
    if ENV_PATH.exists():
        unset_key(str(ENV_PATH), config["env_var"])
    os.environ.pop(config["env_var"], None)
    return _key_info(provider)


def _check_gemini() -> ApiKeyCheckResponse:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return ApiKeyCheckResponse(provider="gemini", status="warning", message="GEMINI_API_KEY is not configured")
    try:
        client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
        client.models.generate_content(
            model="gemini-3-flash-preview",
            contents="ping",
            config=types.GenerateContentConfig(max_output_tokens=1),
        )
        return ApiKeyCheckResponse(provider="gemini", status="ok", message="Gemini API is available")
    except Exception as exc:
        return ApiKeyCheckResponse(provider="gemini", status="error", message=f"Gemini API check failed: {exc}")


def _check_deepseek() -> ApiKeyCheckResponse:
    if not os.getenv("DEEPSEEK_API_KEY"):
        return ApiKeyCheckResponse(provider="deepseek", status="warning", message="DEEPSEEK_API_KEY is not configured")
    try:
        deepseek_service.complete_text(
            model_name="deepseek-v4-flash",
            system_instruction="Return a short pong.",
            user_content="ping",
            max_tokens=4,
        )
        return ApiKeyCheckResponse(provider="deepseek", status="ok", message="DeepSeek API is available")
    except Exception as exc:
        return ApiKeyCheckResponse(provider="deepseek", status="error", message=f"DeepSeek API check failed: {exc}")


def _check_dashscope() -> ApiKeyCheckResponse:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return ApiKeyCheckResponse(provider="dashscope", status="warning", message="DASHSCOPE_API_KEY is not configured")
    try:
        client = DashScopeEmbeddingClient(api_key=api_key, batch_size=1)
        client.embed_text("ping")
        return ApiKeyCheckResponse(provider="dashscope", status="ok", message="DashScope API is available")
    except Exception as exc:
        return ApiKeyCheckResponse(provider="dashscope", status="error", message=f"DashScope API check failed: {exc}")


def _check_github() -> ApiKeyCheckResponse:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return ApiKeyCheckResponse(provider="github", status="warning", message="GITHUB_TOKEN is not configured")
    try:
        response = requests.get(
            "https://api.github.com/user",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=20,
        )
        if response.status_code == 200:
            return ApiKeyCheckResponse(provider="github", status="ok", message="GitHub token is available")
        return ApiKeyCheckResponse(provider="github", status="error", message=f"GitHub check failed: HTTP {response.status_code}")
    except Exception as exc:
        return ApiKeyCheckResponse(provider="github", status="error", message=f"GitHub check failed: {exc}")


CHECKERS = {
    "gemini": _check_gemini,
    "deepseek": _check_deepseek,
    "dashscope": _check_dashscope,
    "github": _check_github,
}


@router.get("/api-keys", response_model=ApiKeyListResponse)
def list_api_keys() -> ApiKeyListResponse:
    env_values = _load_env_values()
    return ApiKeyListResponse(keys=[_key_info(provider, env_values) for provider in PROVIDERS])


@router.put("/api-keys/{provider}", response_model=ApiKeyUpdateResponse)
def update_api_key(provider: ProviderName, payload: ApiKeyUpdateRequest) -> ApiKeyUpdateResponse:
    key = _write_key(provider, payload.value)
    return ApiKeyUpdateResponse(ok=True, key=key)


@router.delete("/api-keys/{provider}", response_model=ApiKeyUpdateResponse)
def delete_api_key(provider: ProviderName) -> ApiKeyUpdateResponse:
    key = _delete_key(provider)
    return ApiKeyUpdateResponse(ok=True, key=key)


@router.post("/api-keys/{provider}/check", response_model=ApiKeyCheckResponse)
def check_api_key(provider: ProviderName) -> ApiKeyCheckResponse:
    checker = CHECKERS.get(provider)
    if checker is None:
        raise HTTPException(status_code=404, detail="Unknown API key provider")
    return checker()
