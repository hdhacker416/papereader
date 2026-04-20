from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

load_dotenv(ROOT_DIR / "backend" / ".env")

from app_constants import DEFAULT_USER_ID
from database import SessionLocal, check_and_migrate_database, engine
import models
import schemas
from services import conference_service, deep_research_service
from services.auto_research_task_service import _process_preparing_task
from services.template_service import ensure_default_template


def _parse_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or None


def _parse_years(value: str | None) -> list[int] | None:
    if not value:
        return None
    years: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        years.append(int(item))
    return years or None


def _bootstrap_db() -> None:
    models.Base.metadata.create_all(bind=engine)
    check_and_migrate_database()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == DEFAULT_USER_ID).first()
        if not user:
            user = models.User(
                id=DEFAULT_USER_ID,
                email="user@example.com",
                name="Default User",
            )
            db.add(user)
            db.commit()
        ensure_default_template(db)
        conference_service.ensure_seed_data(db)
    finally:
        db.close()


def main() -> None:
    _bootstrap_db()

    query = os.getenv(
        "DEBUG_RESEARCH_QUERY",
        "请你帮我看看，大模型对齐技术和后训练技术有什么新的进展",
    )
    name = os.getenv("DEBUG_RESEARCH_NAME", "Debug Research Task")
    conferences = _parse_csv(os.getenv("DEBUG_RESEARCH_CONFERENCES", "iclr,icml,nips"))
    years = _parse_years(os.getenv("DEBUG_RESEARCH_YEARS", "2026,2025"))
    model_name = os.getenv("DEBUG_RESEARCH_MODEL", "gemini-3-flash-preview")
    max_search_rounds = int(os.getenv("DEBUG_RESEARCH_MAX_SEARCH_ROUNDS", "5"))
    max_queries_per_round = int(os.getenv("DEBUG_RESEARCH_MAX_QUERIES_PER_ROUND", "5"))
    max_full_reads = int(os.getenv("DEBUG_RESEARCH_MAX_FULL_READS", "12"))

    payload = schemas.AutoResearchTaskCreate(
        query=query,
        name=name,
        conferences=conferences,
        years=years,
        model_name=model_name,
        max_search_rounds=max_search_rounds,
        max_queries_per_round=max_queries_per_round,
        max_full_reads=max_full_reads,
    )

    db = SessionLocal()
    try:
        created = deep_research_service.create_task_from_auto_research(db, payload)
        task_id = created.task_id
        print(f"[debug] created task_id={task_id} name={created.task_name}")
    finally:
        db.close()

    _process_preparing_task(task_id)

    db = SessionLocal()
    try:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        papers = (
            db.query(models.Paper)
            .filter(models.Paper.task_id == task_id)
            .order_by(models.Paper.created_at.asc())
            .all()
        )
        trace = {}
        if task and task.agent_trace_json:
            try:
                trace = json.loads(task.agent_trace_json)
            except json.JSONDecodeError:
                trace = {}

        print(f"[debug] final task status={task.status if task else 'missing'}")
        print(f"[debug] imported papers={len(papers)}")
        print("[debug] trace runtime:")
        print(json.dumps(trace.get("_agent_runtime", {}), ensure_ascii=False, indent=2))
        print("[debug] brief:")
        print(json.dumps(trace.get("研究简报", {}), ensure_ascii=False, indent=2))
        print("[debug] summary:")
        print(json.dumps(trace.get("汇总", {}), ensure_ascii=False, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
