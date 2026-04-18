from __future__ import annotations

import asyncio
import json
import logging
import sys
import traceback
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app_constants import DEFAULT_USER_ID
from database import SessionLocal
import models
from research.agent.bounded import BoundedResearchRunner, ResearchBrief, SearchRoundResult, SelectedPaper
from research.targeting import conference_display_name
from services.template_service import serialize_prompt_list


logger = logging.getLogger(__name__)


def _parse_trace(payload: str | None) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        parsed = json.loads(payload)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _save_trace(db: Session, task: models.Task, trace: dict[str, Any]) -> None:
    task.agent_trace_json = json.dumps(trace, ensure_ascii=False)
    db.commit()


def _config(trace: dict[str, Any]) -> dict[str, Any]:
    value = trace.get("_agent_config")
    return value if isinstance(value, dict) else {}


def _runtime(trace: dict[str, Any]) -> dict[str, Any]:
    value = trace.get("_agent_runtime")
    if not isinstance(value, dict):
        value = {}
        trace["_agent_runtime"] = value
    return value


def _build_brief_trace(brief: ResearchBrief) -> dict[str, Any]:
    return {
        "研究目标": brief.research_goal,
        "范围模式": {"focused": "聚焦", "broad": "宽范围"}.get(brief.breadth_mode, brief.breadth_mode),
        "搜索方向": brief.search_axes,
        "初始查询": brief.initial_queries,
        "精排查询": brief.rerank_query,
        "目标会议": [conference_display_name(code) for code in brief.target_conferences],
        "目标年份": [int(year) for year in brief.target_years],
        "精读提示词": brief.reading_prompts,
    }


def _build_round_selected_trace(round_item: SearchRoundResult, selected: SelectedPaper) -> dict[str, Any]:
    matched = next(
        (
            item for item in round_item.reranked_results
            if item["paper"]["conference"] == selected.conference
            and int(item["paper"]["year"]) == selected.year
            and item["paper"]["paper_id"] == selected.paper_id
        ),
        None,
    )
    return {
        "paper_id": selected.paper_id,
        "论文标题": matched["paper"]["title"] if matched else selected.paper_id,
        "会议": conference_display_name(selected.conference),
        "年份": int(selected.year),
        "方向": selected.axis,
        "选择理由": selected.reason,
        "优先级": int(selected.priority),
        "精排分数": round(float(matched["rerank_score"]), 4) if matched else None,
    }


def _build_round_candidate_trace(item: dict[str, Any]) -> dict[str, Any]:
    paper = item["paper"]
    return {
        "paper_id": paper["paper_id"],
        "论文标题": paper["title"],
        "会议": conference_display_name(paper["conference"]),
        "年份": int(paper["year"]),
        "粗排分数": round(float(item["coarse_score"]), 4),
        "精排分数": round(float(item["rerank_score"]), 4),
    }


def _build_round_summary(round_item: SearchRoundResult) -> str:
    queries = [str(item).strip() for item in round_item.queries if str(item).strip()]
    query_text = "；".join(queries) if queries else "无查询"
    selected_titles = [
        str(item["论文标题"]).strip()
        for item in [_build_round_selected_trace(round_item, selected) for selected in round_item.decision.selected_papers]
        if str(item.get("论文标题", "")).strip()
    ]
    selected_text = "；".join(selected_titles[:3]) if selected_titles else "本轮没有新增重点论文"
    missing_axes = [str(item).strip() for item in round_item.decision.missing_axes if str(item).strip()]
    missing_text = "；".join(missing_axes) if missing_axes else "当前没有明显缺口"
    next_queries = [str(item).strip() for item in round_item.decision.additional_queries if str(item).strip()]
    next_query_text = "；".join(next_queries) if next_queries else "无下一轮补充查询"
    return (
        f"本轮围绕 {query_text} 进行搜索。"
        f"粗排命中 {sum(len(item['results']) for item in round_item.coarse_results)} 条，"
        f"合并后保留 {len(round_item.merged_candidates)} 条候选，"
        f"精排后重点关注 {len(round_item.decision.selected_papers)} 篇。"
        f"模型判断：{round_item.decision.rationale}。"
        f"本轮重点论文：{selected_text}。"
        f"当前缺口：{missing_text}。"
        f"后续查询：{next_query_text}。"
    )


def _build_round_trace(round_item: SearchRoundResult) -> dict[str, Any]:
    return {
        "轮次": round_item.round_index,
        "本轮查询": round_item.queries,
        "粗排命中数": sum(len(item["results"]) for item in round_item.coarse_results),
        "合并候选数": len(round_item.merged_candidates),
        "精排候选数": len(round_item.reranked_results),
        "本轮高分候选": [
            _build_round_candidate_trace(item)
            for item in round_item.reranked_results[:10]
        ],
        "本轮结果总结": _build_round_summary(round_item),
        "继续搜索": bool(round_item.decision.continue_search),
        "本轮判断": round_item.decision.rationale,
        "缺失方向": round_item.decision.missing_axes,
        "下一轮查询": round_item.decision.additional_queries,
        "本轮选中文章": [
            _build_round_selected_trace(round_item, item)
            for item in round_item.decision.selected_papers
        ],
    }


def _build_final_selected_trace(selected_records: list[dict[str, Any]], detail_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    detail_lookup = {
        (item["conference"], int(item["year"]), item["paper_id"]): item
        for item in detail_results
    }
    final_selected = []
    for item in selected_records:
        detail = detail_lookup.get((item["conference"], int(item["year"]), item["paper_id"]), {})
        final_selected.append(
            {
                "paper_id": item["paper_id"],
                "论文标题": item["paper"]["title"],
                "会议": conference_display_name(item["conference"]),
                "年份": int(item["year"]),
                "方向": item["axis"],
                "选择理由": item["reason"],
                "优先级": int(item["priority"]),
                "粗排分数": round(float(item["coarse_score"]), 4),
                "精排分数": round(float(item["rerank_score"]), 4),
                "链接": detail.get("source_url") or item["paper"].get("source_url") or "",
            }
        )
    return final_selected


def _apply_trace_event(task_id: str, event: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        task = db.query(models.Task).filter(models.Task.id == task_id, models.Task.user_id == DEFAULT_USER_ID).first()
        if not task:
            return
        trace = _parse_trace(task.agent_trace_json)
        runtime = _runtime(trace)
        event_type = event.get("type")
        if event_type == "brief":
            brief = event["brief"]
            trace["研究简报"] = _build_brief_trace(brief)
            runtime["state"] = "running"
            runtime["current_stage"] = "生成研究简报完成，开始搜索"
        elif event_type == "round":
            round_item = event["round"]
            rounds = trace.setdefault("搜索轮次", [])
            rounds.append(_build_round_trace(round_item))
            trace["汇总"] = {
                "实际搜索轮数": len(rounds),
                "最终选中文章数": len(event.get("selected_papers", [])),
            }
            runtime["state"] = "running"
            runtime["current_stage"] = f"第 {round_item.round_index} 轮搜索完成"
        elif event_type == "final":
            selected_records = event.get("selected_papers", [])
            detail_results = event.get("detail_results", [])
            trace["最终选中文章"] = _build_final_selected_trace(selected_records, detail_results)
            trace["汇总"] = {
                "实际搜索轮数": len(event.get("rounds", [])),
                "最终选中文章数": len(selected_records),
            }
            runtime["state"] = "running"
            runtime["current_stage"] = "搜索完成，准备导入任务"
        _save_trace(db, task, trace)
    except Exception as exc:
        logger.error("Failed to apply auto research trace event for task %s: %s", task_id, exc)
        db.rollback()
    finally:
        db.close()


def _select_by_threshold(reranked_results: list[dict[str, Any]], threshold: float, min_papers: int, max_papers: int) -> list[dict[str, Any]]:
    selected = [item for item in reranked_results if float(item["rerank_score"]) >= threshold]
    if len(selected) < min_papers:
        selected = reranked_results[:min_papers]
    return selected[:max_papers]


def _process_preparing_task(task_id: str) -> None:
    db = SessionLocal()
    try:
        task = db.query(models.Task).filter(
            models.Task.id == task_id,
            models.Task.user_id == DEFAULT_USER_ID,
            models.Task.status == "preparing",
        ).first()
        if not task:
            return

        trace = _parse_trace(task.agent_trace_json)
        config = _config(trace)
        runtime = _runtime(trace)
        if runtime.get("state") == "running":
            return

        runtime["state"] = "running"
        runtime["current_stage"] = "等待生成研究简报"
        _save_trace(db, task, trace)

        runner = BoundedResearchRunner(model=str(config.get("model_name") or "gemini-3-flash-preview"))
        selection = runner.run_selection(
            user_query=str(config.get("query") or ""),
            conferences=config.get("conferences") or None,
            years=config.get("years") or None,
            max_search_rounds=int(config.get("max_search_rounds") or 3),
            max_queries_per_round=int(config.get("max_queries_per_round") or 4),
            max_full_reads=int(config.get("max_full_reads") or 8),
            min_full_reads=1,
            reading_prompts_override=config.get("custom_reading_prompts") or None,
            trace_callback=lambda event: _apply_trace_event(task_id, event),
        )

        selected = _select_by_threshold(
            reranked_results=selection.selected_papers,
            threshold=float(config.get("rerank_score_threshold") or 0.5),
            min_papers=1,
            max_papers=int(config.get("max_full_reads") or 8),
        )
        db.refresh(task)
        trace = _parse_trace(task.agent_trace_json)
        runtime = _runtime(trace)
        if not selected:
            runtime["state"] = "failed"
            runtime["current_stage"] = "没有选出可导入任务的论文"
            runtime["error"] = "Auto research did not select any papers"
            runtime["error_type"] = "NoSelectedPapers"
            trace["错误"] = "Auto research did not select any papers"
            task.status = "failed"
            _save_trace(db, task, trace)
            return

        task_prompts = config.get("custom_reading_prompts") or selection.brief.reading_prompts
        task.custom_reading_prompts_json = serialize_prompt_list(task_prompts)

        detail_lookup = {
            (item["conference"], int(item["year"]), item["paper_id"]): item
            for item in selection.detail_results
        }
        for item in selected:
            paper = item["paper"]
            detail = detail_lookup.get((paper["conference"], int(paper["year"]), paper["paper_id"]), {})
            db.add(
                models.Paper(
                    task_id=task.id,
                    title=paper["title"],
                    source_url=detail.get("source_url") or paper.get("source_url"),
                    status="queued",
                )
            )

        trace["最终选中文章"] = _build_final_selected_trace(selected, selection.detail_results)
        trace["汇总"] = {
            "实际搜索轮数": len(selection.rounds),
            "最终选中文章数": len(selected),
        }
        runtime["state"] = "completed"
        runtime["current_stage"] = "已进入全文精读"
        task.status = "running"
        _save_trace(db, task, trace)
    except Exception as exc:
        logger.error("Auto research task %s failed: %s", task_id, exc)
        db.rollback()
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if task:
            trace = _parse_trace(task.agent_trace_json)
            runtime = _runtime(trace)
            runtime["state"] = "failed"
            runtime["current_stage"] = "执行失败"
            runtime["error"] = str(exc)
            runtime["error_type"] = exc.__class__.__name__
            runtime["error_detail"] = "".join(
                traceback.format_exception_only(type(exc), exc)
            ).strip()
            trace["错误"] = str(exc)
            task.status = "failed"
            task.agent_trace_json = json.dumps(trace, ensure_ascii=False)
            db.commit()
    finally:
        db.close()


def recover_stale_auto_research_tasks() -> None:
    db = SessionLocal()
    try:
        tasks = db.query(models.Task).filter(models.Task.status == "preparing").all()
        changed = False
        for task in tasks:
            trace = _parse_trace(task.agent_trace_json)
            runtime = _runtime(trace)
            if runtime.get("state") == "running":
                runtime["state"] = "queued"
                runtime["current_stage"] = "等待恢复"
                task.agent_trace_json = json.dumps(trace, ensure_ascii=False)
                changed = True
        if changed:
            db.commit()
    except Exception as exc:
        logger.error("Failed to recover stale auto research tasks: %s", exc)
        db.rollback()
    finally:
        db.close()


async def auto_research_task_loop() -> None:
    logger.info("Starting auto research task loop")
    while True:
        db = SessionLocal()
        try:
            queued = (
                db.query(models.Task)
                .filter(models.Task.status == "preparing")
                .order_by(models.Task.created_at.asc())
                .first()
            )
            if queued is None:
                await asyncio.sleep(2)
                continue
            await asyncio.to_thread(_process_preparing_task, queued.id)
        except Exception as exc:
            logger.error("Error in auto research task loop: %s", exc)
            await asyncio.sleep(5)
        finally:
            db.close()
