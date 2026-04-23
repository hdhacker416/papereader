from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

load_dotenv(ROOT_DIR / "backend" / ".env")

from app_constants import DEFAULT_USER_ID
from database import SessionLocal, check_and_migrate_database, engine
import models
from services import conference_service, deep_research_service
from services.template_service import ensure_default_template
from research.agent.bounded import BoundedResearchRunner


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


def _json_ready(value: Any) -> Any:
    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    return value


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(_json_ready(value), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Debug the task report pipeline from interpreted papers to final report.",
    )
    parser.add_argument("--task-id", required=True, help="Task id to debug")
    parser.add_argument(
        "--report-model",
        default=None,
        help="Override report model. Defaults to latest report model, then task model.",
    )
    parser.add_argument(
        "--query",
        default=None,
        help="Override report query. Defaults to latest report query, then trace/task fields.",
    )
    parser.add_argument(
        "--stage",
        choices=["brief", "inputs", "evidence", "outline", "report"],
        default="report",
        help="Stop after this stage.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory to write debug artifacts into. Defaults to data/research/runtime/debug_reports/<task_id>/<timestamp>",
    )
    return parser.parse_args()


def _resolve_output_dir(task_id: str, explicit: str | None) -> Path:
    if explicit:
        output_dir = Path(explicit)
    else:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_dir = ROOT_DIR / "data" / "research" / "runtime" / "debug_reports" / task_id / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _print_stage(stage: str, message: str) -> None:
    print(f"[debug-report] {stage}: {message}")


def main() -> None:
    args = _parse_args()
    _bootstrap_db()

    output_dir = _resolve_output_dir(args.task_id, args.output_dir)
    _print_stage("output", str(output_dir))

    db = SessionLocal()
    try:
        task = db.query(models.Task).filter(
            models.Task.id == args.task_id,
            models.Task.user_id == DEFAULT_USER_ID,
        ).first()
        if not task:
            raise SystemExit(f"Task not found: {args.task_id}")

        latest_report = (
            db.query(models.DeepResearchReport)
            .filter(models.DeepResearchReport.task_id == task.id)
            .order_by(models.DeepResearchReport.created_at.desc())
            .first()
        )
        trace = deep_research_service._parse_json_dict(task.agent_trace_json)
        interpreted = deep_research_service._load_interpreted_task_papers(db, task)
        if not interpreted:
            raise SystemExit(f"Task has no interpreted papers: {args.task_id}")

        report_query = (
            args.query
            or (latest_report.query if latest_report and latest_report.query else None)
            or trace.get("用户问题")
            or task.description
            or task.name
        )
        report_model = (
            args.report_model
            or (latest_report.model_name if latest_report and latest_report.model_name else None)
            or task.model_name
            or "gemini-3-flash-preview"
        )

        _write_json(
            output_dir / "task_meta.json",
            {
                "task_id": task.id,
                "task_name": task.name,
                "task_status": task.status,
                "task_model": task.model_name,
                "latest_report_id": latest_report.id if latest_report else None,
                "latest_report_model": latest_report.model_name if latest_report else None,
                "report_query": report_query,
                "report_model": report_model,
                "interpreted_paper_count": len(interpreted),
            },
        )
        _write_json(output_dir / "agent_trace.json", trace)
        _write_json(output_dir / "interpreted.json", interpreted)

        brief = deep_research_service._build_task_report_brief(
            user_query=report_query,
            task=task,
            trace=trace,
        )
        _write_json(output_dir / "01_brief.json", asdict(brief))
        _print_stage("brief", "wrote 01_brief.json")
        if args.stage == "brief":
            return

        selected_records, reading_results, weak_signals = deep_research_service._build_task_report_inputs(
            task=task,
            user_query=report_query,
            interpreted=interpreted,
            trace=trace,
        )
        _write_json(output_dir / "02_selected_records.json", selected_records)
        _write_json(output_dir / "03_reading_results.json", reading_results)
        _write_json(output_dir / "04_weak_signals.json", weak_signals)
        _print_stage(
            "inputs",
            f"selected={len(selected_records)} reading_results={len(reading_results)} weak_signals={len(weak_signals)}",
        )
        if args.stage == "inputs":
            return

        runner = BoundedResearchRunner(model=report_model)

        def progress_callback(completed: int, total: int, message: str) -> None:
            print(f"[debug-report] evidence {completed}/{total}: {message}")

        evidence_pack = runner._build_evidence_pack(
            user_query=report_query,
            brief=brief,
            selected_papers=selected_records,
            reading_results=reading_results,
            weak_signals=weak_signals,
            progress_callback=progress_callback,
        )
        _write_json(output_dir / "05_evidence_pack.json", evidence_pack)
        _print_stage(
            "evidence",
            f"cards={len(evidence_pack.get('evidence_cards', []))}",
        )
        if args.stage == "evidence":
            return

        report_outline = runner._build_report_outline(
            user_query=report_query,
            brief=brief,
            evidence_pack=evidence_pack,
        )
        _write_json(output_dir / "06_report_outline.json", report_outline)
        _print_stage("outline", "wrote 06_report_outline.json")
        if args.stage == "outline":
            return

        draft_report = runner._summarize(
            user_query=report_query,
            brief=brief,
            evidence_pack=evidence_pack,
            report_outline=report_outline,
        )
        _write_text(output_dir / "07_draft_report.md", draft_report)

        final_report = draft_report
        repaired = False
        if deep_research_service._report_needs_repair(draft_report):
            repaired = True
            repaired_report = runner._repair_report(
                user_query=report_query,
                brief=brief,
                evidence_pack=evidence_pack,
                report_outline=report_outline,
                draft_report=draft_report,
            )
            _write_text(output_dir / "08_repaired_report.md", repaired_report)
            final_report = repaired_report

        final_report = deep_research_service._sanitize_report_visible_paper_ids(
            content=final_report,
            reading_results=reading_results,
        )
        rewritten_report, source_meta = deep_research_service._rewrite_report_evidence_links(
            content=final_report,
            task_id=task.id,
            selected_records=selected_records,
            reading_results=reading_results,
            weak_signals=weak_signals,
        )
        _write_text(output_dir / "09_final_report.md", rewritten_report)
        _write_text(output_dir / "10_source_meta.json", source_meta)
        _write_json(
            output_dir / "summary.json",
            {
                "task_id": task.id,
                "report_query": report_query,
                "report_model": report_model,
                "repaired": repaired,
                "output_dir": str(output_dir),
            },
        )
        _print_stage("report", f"done; repaired={repaired}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
