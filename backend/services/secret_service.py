from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values, set_key, unset_key

try:
    from database import get_current_storage_user_id, get_user_data_dir
except ModuleNotFoundError:
    from backend.database import get_current_storage_user_id, get_user_data_dir


SecretSource = Literal["user", "server", "missing"]

BACKEND_DIR = Path(__file__).resolve().parents[1]
GLOBAL_ENV_PATH = BACKEND_DIR / ".env"
USER_SECRETS_FILENAME = "secrets.env"


def user_secrets_path(user_id: str | None = None) -> Path:
    return Path(get_user_data_dir(user_id or get_current_storage_user_id())) / USER_SECRETS_FILENAME


def _load_values(path: Path) -> dict[str, str]:
    values = dotenv_values(path) if path.exists() else {}
    return {key: value for key, value in values.items() if value is not None}


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def get_user_secret(env_var: str, *, user_id: str | None = None) -> str | None:
    return _clean(_load_values(user_secrets_path(user_id)).get(env_var))


def get_server_secret(env_var: str) -> str | None:
    return _clean(_load_values(GLOBAL_ENV_PATH).get(env_var)) or _clean(os.getenv(env_var))


def get_secret(env_var: str, *, user_id: str | None = None, allow_server_fallback: bool = True) -> str | None:
    value = get_user_secret(env_var, user_id=user_id)
    if value:
        return value
    if allow_server_fallback:
        return get_server_secret(env_var)
    return None


def get_secret_source(env_var: str, *, user_id: str | None = None, allow_server_fallback: bool = True) -> SecretSource:
    if get_user_secret(env_var, user_id=user_id):
        return "user"
    if allow_server_fallback and get_server_secret(env_var):
        return "server"
    return "missing"


def set_user_secret(env_var: str, value: str, *, user_id: str | None = None) -> None:
    clean_value = _clean(value)
    if not clean_value:
        raise ValueError("Secret value cannot be empty")
    path = user_secrets_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")
    set_key(str(path), env_var, clean_value)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def delete_user_secret(env_var: str, *, user_id: str | None = None) -> None:
    path = user_secrets_path(user_id)
    if path.exists():
        unset_key(str(path), env_var)
