from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from database import DATA_DIR


SECRET_PATH = Path(DATA_DIR) / "mobile_file_secret"
DEFAULT_TTL_SECONDS = 10 * 60


def _secret() -> bytes:
    env_secret = os.getenv("PAPERREADER_FILE_TOKEN_SECRET")
    if env_secret:
        return env_secret.encode("utf-8")
    SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SECRET_PATH.exists():
        SECRET_PATH.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        try:
            SECRET_PATH.chmod(0o600)
        except OSError:
            pass
    return SECRET_PATH.read_text(encoding="utf-8").strip().encode("utf-8")


def _b64_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


def create_mobile_file_token(payload: dict[str, Any], ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    body = dict(payload)
    body["exp"] = int(time.time()) + ttl_seconds
    raw_body = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(_secret(), raw_body, hashlib.sha256).digest()
    return f"{_b64_encode(raw_body)}.{_b64_encode(signature)}"


def verify_mobile_file_token(token: str) -> dict[str, Any]:
    try:
        body_part, signature_part = token.split(".", 1)
        raw_body = _b64_decode(body_part)
        expected = hmac.new(_secret(), raw_body, hashlib.sha256).digest()
        actual = _b64_decode(signature_part)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid file token") from exc

    if not hmac.compare_digest(expected, actual):
        raise HTTPException(status_code=401, detail="Invalid file token")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=401, detail="Invalid file token") from exc

    if int(payload.get("exp") or 0) < int(time.time()):
        raise HTTPException(status_code=401, detail="File token expired")
    return payload
