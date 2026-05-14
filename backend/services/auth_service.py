from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException, Request, Response

from database import AUTH_DB_PATH, ensure_user_database

SESSION_COOKIE_NAME = "paperreader_session"
SESSION_DAYS = 30


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str
    name: str


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _connect() -> sqlite3.Connection:
    Path(AUTH_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(AUTH_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_auth_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)
        conn.commit()


def _normalize_email(email: str) -> str:
    value = email.strip().lower()
    if "@" not in value or len(value) > 254:
        raise HTTPException(status_code=400, detail="Please enter a valid email address")
    return value


def _validate_password(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")


def _hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 200_000)
    return digest.hex()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _row_to_user(row: sqlite3.Row) -> AuthUser:
    return AuthUser(id=str(row["id"]), email=str(row["email"]), name=str(row["name"]))


def register_user(email: str, password: str, name: str | None = None) -> AuthUser:
    init_auth_db()
    clean_email = _normalize_email(email)
    _validate_password(password)
    clean_name = (name or clean_email.split("@", 1)[0] or "PaperReader User").strip()[:120]
    user_id = str(uuid.uuid4())
    salt = secrets.token_hex(16)
    password_hash = _hash_password(password, salt)

    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO users (id, email, name, password_hash, password_salt, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, clean_email, clean_name, password_hash, salt, _utcnow().isoformat()),
            )
            conn.commit()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="This email is already registered") from exc

    ensure_user_database(user_id, email=clean_email, name=clean_name)
    return AuthUser(id=user_id, email=clean_email, name=clean_name)


def authenticate_user(email: str, password: str) -> AuthUser:
    init_auth_db()
    clean_email = _normalize_email(email)
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (clean_email,)).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    expected = str(row["password_hash"])
    actual = _hash_password(password, str(row["password_salt"]))
    if not secrets.compare_digest(expected, actual):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user = _row_to_user(row)
    ensure_user_database(user.id, email=user.email, name=user.name)
    return user


def create_session(user_id: str) -> tuple[str, datetime]:
    init_auth_db()
    token = secrets.token_urlsafe(48)
    token_hash = _hash_token(token)
    expires_at = _utcnow() + timedelta(days=SESSION_DAYS)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (token_hash, user_id, expires_at.isoformat(), _utcnow().isoformat()),
        )
        conn.commit()
    return token, expires_at


def set_session_cookie(response: Response, request: Request, token: str, expires_at: datetime) -> None:
    max_age = max(0, int((expires_at - _utcnow()).total_seconds()))
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=max_age,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


def get_user_by_session_token(token: str | None) -> AuthUser | None:
    if not token:
        return None
    init_auth_db()
    token_hash = _hash_token(token)
    now = _utcnow()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT users.id, users.email, users.name, sessions.expires_at
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
        if row is None:
            return None
        try:
            expires_at = datetime.fromisoformat(str(row["expires_at"]))
        except ValueError:
            expires_at = now - timedelta(seconds=1)
        if expires_at <= now:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
            conn.commit()
            return None
    return _row_to_user(row)


def get_user_from_request(request: Request) -> AuthUser | None:
    return get_user_by_session_token(request.cookies.get(SESSION_COOKIE_NAME))


def require_current_user(request: Request) -> AuthUser:
    user = getattr(request.state, "current_user", None)
    if user is not None:
        return user
    user = get_user_from_request(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    request.state.current_user = user
    return user


def delete_session(token: str | None) -> None:
    if not token:
        return
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token),))
        conn.commit()


def list_user_ids() -> list[str]:
    init_auth_db()
    with _connect() as conn:
        rows = conn.execute("SELECT id FROM users ORDER BY created_at ASC").fetchall()
    return [str(row["id"]) for row in rows]
