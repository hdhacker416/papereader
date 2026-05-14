from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker
from fastapi import Request

from app_constants import DEFAULT_USER_ID

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = str(BASE_DIR / "data")
AUTH_DB_PATH = str(BASE_DIR / "data" / "auth.db")
USERS_DIR = str(BASE_DIR / "data" / "users")
LEGACY_DB_PATH = str(BASE_DIR / "data" / "app.db")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(USERS_DIR, exist_ok=True)

Base = declarative_base()

_current_storage_user_id: ContextVar[str | None] = ContextVar("paperreader_storage_user_id", default=None)
_engine_cache: dict[str, Engine] = {}
_sessionmaker_cache: dict[str, sessionmaker] = {}


def _safe_user_id(user_id: str | None) -> str:
    clean = (user_id or DEFAULT_USER_ID).strip()
    if not clean or "/" in clean or "\\" in clean or ".." in clean:
        raise ValueError("Invalid user id")
    return clean


def get_current_storage_user_id() -> str:
    return _safe_user_id(_current_storage_user_id.get() or DEFAULT_USER_ID)


@contextmanager
def user_context(user_id: str):
    token = _current_storage_user_id.set(_safe_user_id(user_id))
    try:
        yield
    finally:
        _current_storage_user_id.reset(token)


def get_user_data_dir(user_id: str | None = None) -> str:
    storage_user_id = _safe_user_id(user_id or _current_storage_user_id.get() or DEFAULT_USER_ID)
    path = Path(USERS_DIR) / storage_user_id
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def get_data_dir() -> str:
    return get_user_data_dir()


def get_user_db_path(user_id: str | None = None) -> str:
    return str(Path(get_user_data_dir(user_id)) / "app.db")


def get_engine(user_id: str | None = None) -> Engine:
    storage_user_id = _safe_user_id(user_id or _current_storage_user_id.get() or DEFAULT_USER_ID)
    cached = _engine_cache.get(storage_user_id)
    if cached is not None:
        return cached

    engine = create_engine(
        f"sqlite:///{get_user_db_path(storage_user_id)}",
        connect_args={"check_same_thread": False},
    )
    _engine_cache[storage_user_id] = engine
    return engine


def SessionLocal(user_id: str | None = None) -> Session:
    storage_user_id = _safe_user_id(user_id or _current_storage_user_id.get() or DEFAULT_USER_ID)
    maker = _sessionmaker_cache.get(storage_user_id)
    if maker is None:
        maker = sessionmaker(autocommit=False, autoflush=False, bind=get_engine(storage_user_id))
        _sessionmaker_cache[storage_user_id] = maker
    return maker()


engine = get_engine(DEFAULT_USER_ID)


def get_db(request: Request):
    storage_user_id = None
    if request is not None and hasattr(request, "state"):
        current_user = getattr(request.state, "current_user", None)
        storage_user_id = getattr(current_user, "id", None)

    db = SessionLocal(storage_user_id or _current_storage_user_id.get() or DEFAULT_USER_ID)
    try:
        yield db
    finally:
        db.close()


def check_and_migrate_database(target_engine: Engine | None = None):
    """
    Checks database schema and performs auto-migrations for backward compatibility.
    """
    target_engine = target_engine or get_engine()
    logger.info("Checking database schema...")
    inspector = inspect(target_engine)

    if inspector.has_table("papers"):
        existing_columns = {c["name"] for c in inspector.get_columns("papers")}
        expected_columns = {
            "id", "task_id", "title", "pdf_path", "source", "source_url",
            "status", "failure_reason", "created_at",
            "template_id", "model_name",
        }
        missing_columns = expected_columns - existing_columns
        auto_migratable = {"template_id", "model_name"}
        critical_missing = missing_columns - auto_migratable
        if critical_missing:
            error_msg = f"Database schema mismatch: Table 'papers' is missing critical columns: {critical_missing}. Please check your database version."
            logger.error(error_msg)
            raise Exception(error_msg)

        with target_engine.connect() as conn:
            if "template_id" in missing_columns:
                logger.info("Migrating: Adding template_id to papers table")
                conn.execute(text("ALTER TABLE papers ADD COLUMN template_id VARCHAR"))

            if "model_name" in missing_columns:
                logger.info("Migrating: Adding model_name to papers table")
                conn.execute(text("ALTER TABLE papers ADD COLUMN model_name VARCHAR"))

            logger.info("Checking for legacy absolute PDF paths...")
            result = conn.execute(text("""
                SELECT COUNT(*) FROM papers
                WHERE task_id IS NOT NULL
                AND (pdf_path LIKE '%:%' OR pdf_path LIKE '/%')
            """))
            count = result.scalar()

            if count > 0:
                logger.info("Found %s papers with legacy paths. Migrating to relative format...", count)
                conn.execute(text("""
                    UPDATE papers
                    SET pdf_path = 'pdfs/' || task_id || '/' || id || '.pdf'
                    WHERE task_id IS NOT NULL
                    AND (pdf_path LIKE '%:%' OR pdf_path LIKE '/%')
                """))
                conn.commit()
                logger.info("PDF path migration completed.")
            else:
                logger.info("No legacy PDF paths found.")

            for table_name in ["research_paper_candidates", "research_jobs"]:
                logger.info("Migrating: Dropping deprecated table if it exists: %s", table_name)
                conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))

            conn.commit()

    if inspector.has_table("tasks"):
        with target_engine.connect() as conn:
            task_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(tasks)")).fetchall()}
            if "custom_reading_prompts_json" not in task_columns:
                logger.info("Migrating: Adding custom_reading_prompts_json to tasks table")
                conn.execute(text("ALTER TABLE tasks ADD COLUMN custom_reading_prompts_json TEXT"))
                conn.commit()
            if "agent_trace_json" not in task_columns:
                logger.info("Migrating: Adding agent_trace_json to tasks table")
                conn.execute(text("ALTER TABLE tasks ADD COLUMN agent_trace_json TEXT"))
                conn.commit()

    if inspector.has_table("deep_research_reports"):
        with target_engine.connect() as conn:
            report_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(deep_research_reports)")).fetchall()}
            migrations = [
                ("model_name", "ALTER TABLE deep_research_reports ADD COLUMN model_name VARCHAR"),
                ("progress_stage", "ALTER TABLE deep_research_reports ADD COLUMN progress_stage VARCHAR"),
                ("progress_message", "ALTER TABLE deep_research_reports ADD COLUMN progress_message TEXT"),
                ("progress_completed", "ALTER TABLE deep_research_reports ADD COLUMN progress_completed INTEGER NOT NULL DEFAULT 0"),
                ("progress_total", "ALTER TABLE deep_research_reports ADD COLUMN progress_total INTEGER NOT NULL DEFAULT 0"),
                ("error", "ALTER TABLE deep_research_reports ADD COLUMN error TEXT"),
            ]
            for column, statement in migrations:
                if column not in report_columns:
                    logger.info("Migrating: Adding %s to deep_research_reports table", column)
                    conn.execute(text(statement))
                    conn.commit()

    logger.info("Database check completed.")


def ensure_user_database(user_id: str, *, email: str | None = None, name: str | None = None) -> None:
    import models

    storage_user_id = _safe_user_id(user_id)
    target_engine = get_engine(storage_user_id)
    models.Base.metadata.create_all(bind=target_engine)
    check_and_migrate_database(target_engine)

    db = SessionLocal(storage_user_id)
    try:
        user = db.query(models.User).filter(models.User.id == DEFAULT_USER_ID).first()
        if not user:
            db.add(models.User(
                id=DEFAULT_USER_ID,
                email=email or f"{storage_user_id}@local.paperreader",
                name=name or "PaperReader User",
            ))
            db.commit()

        default_template = db.query(models.Template).filter(
            models.Template.user_id == DEFAULT_USER_ID,
            models.Template.is_default == True,
        ).first()
        if not default_template:
            db.add(models.Template(
                user_id=DEFAULT_USER_ID,
                name="Default Paper Summary",
                content=json.dumps([
                    "请你使用中文总结一下这篇文章的内容，并且举一个例子加以说明。"
                ], ensure_ascii=False),
                is_default=True,
            ))
            db.commit()
    finally:
        db.close()


def iter_user_ids() -> list[str]:
    try:
        from services import auth_service

        user_ids = auth_service.list_user_ids()
        return user_ids or []
    except Exception as exc:
        logger.warning("Failed to list auth users: %s", exc)
        return []
