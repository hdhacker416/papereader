from __future__ import annotations

from collections import defaultdict
import datetime
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from fastapi import HTTPException
from google import genai
from google.genai import types
import requests
from sqlalchemy.orm import Session

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app_constants import DEFAULT_USER_ID
import models
import schemas
from services.template_service import ensure_default_template
from services.template_service import parse_template_prompts
from services.template_service import serialize_prompt_list
from services import pack_build_service

from research.agent.bounded import BoundedResearchRunner, ResearchBrief
from research.build.build_online_assets import build_online_assets, write_summary
from research.build.packager import Packager
from research.build.paperlists_repo import ensure_paperlists_repo, list_conference_files
from research.pipeline.search_pipeline import load_search_assets
from research.providers.dashscope_embedding import DashScopeEmbeddingClient
from research.targeting import CONFERENCE_DISPLAY_NAMES, conference_display_name, normalize_target_years
from research.tools.search_tools import DEFAULT_SUMMARY_PATH
from research.tools.search_tools import load_default_search_assets
from research.tools.search_tools import SearchTools
from research.runtime.pack_manager import PackManager, RemotePackSpec


TASK_REPORT_PROMPT = (
    "You are writing a deep-research style academic report in Chinese. "
    "The report is for a task that already contains paper-level interpretations. "
    "Base the report only on the provided task papers, interpretations, and metadata. "
    "Do not invent methods, experiments, or conclusions. "
    "Treat papers with full interpretation content as high-confidence evidence. "
    "Write in Markdown with these top-level sections exactly: "
    "1. Executive Summary "
    "2. Directions "
    "3. Paper Analyses "
    "4. Synthesis "
    "5. Limitations."
)
MIN_REPORT_PAPERS = 2
DEFAULT_RELEASE_OWNER = "hdhacker416"
DEFAULT_RELEASE_REPO = "papereader"
TITLE_KEY_RE = re.compile(r"[a-z0-9]+")
EVIDENCE_CLAUSE_RE = re.compile(r"\(evidence:\s*(.*?)\)", re.IGNORECASE | re.DOTALL)
UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)
ENGLISH_REPORT_HEADINGS = [
    "Executive Summary",
    "Direction Map",
    "Detailed Paper Analyses",
    "Cross-Paper Synthesis",
    "Evidence Gaps and Limitations",
    "Suggested Reading Order",
    "Open Questions",
]
CHINESE_REPORT_HEADINGS = [
    "核心结论",
    "研究方向全景",
    "逐篇精读",
    "跨论文关系与综合分析",
    "证据不足与局限",
    "建议阅读顺序",
    "值得继续追的问题",
]
DISPLAY_TO_CONFERENCE = {value.lower(): key for key, value in CONFERENCE_DISPLAY_NAMES.items()}
DISPLAY_TO_CONFERENCE["neurips"] = "nips"


def _get_gemini_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not configured")
    return genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})


def _serialize_report(report: models.DeepResearchReport) -> schemas.DeepResearchReport:
    return schemas.DeepResearchReport.model_validate(report)


def _parse_json_dict(payload: str | None) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        parsed = json.loads(payload)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _title_key(value: str) -> str:
    return " ".join(TITLE_KEY_RE.findall((value or "").lower()))


def _conference_code_from_trace(value: Any) -> str:
    label = str(value or "").strip().lower()
    if not label:
        return "unknown"
    return DISPLAY_TO_CONFERENCE.get(label, label)


def _build_task_report_brief(
    *,
    user_query: str,
    task: models.Task,
    trace: dict[str, Any],
) -> ResearchBrief:
    brief_data = trace.get("研究简报")
    brief = brief_data if isinstance(brief_data, dict) else {}
    reading_prompts = parse_template_prompts(task.custom_reading_prompts_json or "")
    if not reading_prompts:
        reading_prompts = ["请你使用中文总结一下这篇文章的内容，并且举一个例子加以说明。"]
    target_conferences = [
        _conference_code_from_trace(item)
        for item in (brief.get("目标会议") or [])
        if str(item).strip()
    ]
    target_years = []
    for item in brief.get("目标年份") or []:
        try:
            target_years.append(int(item))
        except (TypeError, ValueError):
            continue
    search_axes = [str(item).strip() for item in (brief.get("搜索方向") or []) if str(item).strip()]
    if not search_axes:
        search_axes = ["用户指定主题", "任务内已精读论文综合"]
    initial_queries = [str(item).strip() for item in (brief.get("初始查询") or []) if str(item).strip()]
    if not initial_queries:
        initial_queries = [user_query]
    return ResearchBrief(
        research_goal=str(brief.get("研究目标") or user_query).strip(),
        search_axes=search_axes,
        initial_queries=initial_queries,
        rerank_query=str(brief.get("精排查询") or user_query).strip(),
        reading_prompts=reading_prompts,
        target_conferences=target_conferences,
        target_years=target_years,
    )


def _build_task_report_inputs(
    *,
    task: models.Task,
    user_query: str,
    interpreted: list[dict[str, Any]],
    trace: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    final_selected = trace.get("最终选中文章")
    selected_trace = final_selected if isinstance(final_selected, list) else []

    selected_lookup_by_title: dict[str, dict[str, Any]] = {}
    selected_records: list[dict[str, Any]] = []
    for index, item in enumerate(selected_trace, start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("论文标题") or "").strip()
        if not title:
            continue
        conference = _conference_code_from_trace(item.get("会议"))
        try:
            year = int(item.get("年份"))
        except (TypeError, ValueError):
            year = 0
        paper_id = str(item.get("paper_id") or f"{conference}-{year}-{_title_key(title)}").strip()
        record = {
            "conference": conference,
            "year": year,
            "paper_id": paper_id,
            "axis": str(item.get("方向") or "selected").strip(),
            "reason": str(item.get("选择理由") or "").strip(),
            "priority": int(item.get("优先级") or index),
            "paper": {
                "title": title,
                "abstract": "",
                "source_url": str(item.get("链接") or "").strip(),
            },
            "coarse_score": float(item.get("粗排分数") or 0.0),
            "rerank_score": float(item.get("精排分数") or 0.0),
        }
        selected_records.append(record)
        selected_lookup_by_title[_title_key(title)] = record

    if not selected_records:
        for index, item in enumerate(interpreted, start=1):
            paper_id = str(item.get("paper_id") or "").strip()
            title = str(item.get("title") or "").strip()
            source_url = str(item.get("source_url") or "").strip()
            selected_records.append(
                {
                    "conference": "task",
                    "year": 0,
                    "paper_id": paper_id,
                    "axis": "selected",
                    "reason": "Task-level interpreted paper.",
                    "priority": index,
                    "paper": {
                        "title": title,
                        "abstract": "",
                        "source_url": source_url,
                    },
                    "coarse_score": 0.0,
                    "rerank_score": 0.0,
                }
            )
            if title:
                selected_lookup_by_title[_title_key(title)] = selected_records[-1]

    reading_results: list[dict[str, Any]] = []
    selected_search_keys = {
        (str(item["conference"]), int(item["year"]), str(item["paper_id"]))
        for item in selected_records
    }
    for item in interpreted:
        task_paper_id = str(item.get("paper_id") or "").strip()
        title = str(item.get("title") or "").strip()
        source_url = str(item.get("source_url") or "").strip()
        matched = selected_lookup_by_title.get(_title_key(title))
        if matched is None:
            matched = {
                "conference": "task",
                "year": 0,
                "paper_id": task_paper_id,
            }
        reading_results.append(
            {
                "read_status": "completed",
                "paper": {
                    "conference": str(matched["conference"]),
                    "year": int(matched["year"]),
                    "paper_id": task_paper_id,
                    "title": title,
                    "abstract": "",
                    "authors": [],
                    "source_url": source_url,
                },
                "reading_text": item["interpretation"],
            }
        )

    weak_signal_map: dict[tuple[str, int, str], dict[str, Any]] = {}
    rounds = trace.get("搜索轮次")
    for round_item in rounds if isinstance(rounds, list) else []:
        if not isinstance(round_item, dict):
            continue
        candidates = round_item.get("本轮高分候选")
        for candidate in candidates if isinstance(candidates, list) else []:
            if not isinstance(candidate, dict):
                continue
            title = str(candidate.get("论文标题") or "").strip()
            if not title:
                continue
            conference = _conference_code_from_trace(candidate.get("会议"))
            try:
                year = int(candidate.get("年份"))
            except (TypeError, ValueError):
                year = 0
            paper_id = str(candidate.get("paper_id") or f"{conference}-{year}-{_title_key(title)}").strip()
            key = (conference, year, paper_id)
            if key in selected_search_keys:
                continue
            score = float(candidate.get("精排分数") or 0.0)
            existing = weak_signal_map.get(key)
            if existing is None or score > existing["rerank_score"]:
                weak_signal_map[key] = {
                    "conference": conference,
                    "year": year,
                    "paper_id": paper_id,
                    "title": title,
                    "abstract": "",
                    "rerank_score": score,
                }
    weak_signals = sorted(
        weak_signal_map.values(),
        key=lambda item: float(item["rerank_score"]),
        reverse=True,
    )[:12]

    return selected_records, reading_results, weak_signals


def _rewrite_report_evidence_links(
    *,
    content: str,
    task_id: str,
    selected_records: list[dict[str, Any]],
    reading_results: list[dict[str, Any]],
    weak_signals: list[dict[str, Any]],
) -> tuple[str, str]:
    reading_lookup_by_title = {
        _title_key(item["paper"]["title"]): item["paper"]
        for item in reading_results
        if item.get("read_status") in {"completed", "cached"} and item.get("paper")
    }
    registry: list[dict[str, Any]] = []
    lookup_by_title: dict[str, dict[str, Any]] = {}
    seen_titles: set[str] = set()

    def add_item(*, title: str, paper_id: str | None, kind: str) -> None:
        normalized = _title_key(title)
        if not normalized or normalized in seen_titles:
            return
        seen_titles.add(normalized)
        index = len(registry) + 1
        href = None
        if paper_id:
            href = f"/reader/{quote(paper_id)}?fromTask={quote(task_id)}&fromReport=1"
        item = {
            "index": index,
            "title": title,
            "paper_id": paper_id,
            "href": href,
            "kind": kind,
        }
        registry.append(item)
        lookup_by_title[normalized] = item

    for record in selected_records:
        paper = reading_lookup_by_title.get(_title_key(record["paper"]["title"]))
        if paper is None:
            continue
        add_item(
            title=str(paper["title"]),
            paper_id=str(paper["paper_id"]),
            kind="full_read",
        )

    for item in weak_signals:
        add_item(
            title=str(item["title"]),
            paper_id=None,
            kind="weak_signal",
        )

    def replace_clause(match: re.Match[str]) -> str:
        raw = match.group(1)
        parts = [segment.strip() for segment in raw.split(";") if segment.strip()]
        rendered: list[str] = []
        for part in parts:
            item = lookup_by_title.get(_title_key(part))
            if not item:
                continue
            title_attr = str(item["title"]).replace('"', "'")
            if item["href"]:
                rendered.append(f'[{item["index"]}]({item["href"]} "{title_attr}")')
            else:
                rendered.append(f'[{item["index"]}]')
        return f" {''.join(rendered)}" if rendered else ""

    rewritten = EVIDENCE_CLAUSE_RE.sub(replace_clause, content)
    source_meta = json.dumps(
        {
            "citations": registry,
        },
        ensure_ascii=False,
    )
    return rewritten, source_meta


def _sanitize_report_visible_paper_ids(
    *,
    content: str,
    reading_results: list[dict[str, Any]],
) -> str:
    rewritten = content
    title_map = {
        str(item["paper"]["paper_id"]): str(item["paper"]["title"])
        for item in reading_results
        if item.get("paper") and item["paper"].get("paper_id") and item["paper"].get("title")
    }
    for paper_id, title in title_map.items():
        escaped_id = re.escape(paper_id)
        rewritten = re.sub(
            rf"(?<!/reader/){escaped_id}\s*\([^)]+\)",
            title,
            rewritten,
        )
        rewritten = re.sub(
            rf"(?<!/reader/){escaped_id}",
            title,
            rewritten,
        )
    return rewritten


def _report_needs_repair(content: str) -> bool:
    if not content.strip():
        return True
    if UUID_RE.search(content):
        return True
    if any(marker in content for marker in ENGLISH_REPORT_HEADINGS):
        return True
    if not all(marker in content for marker in CHINESE_REPORT_HEADINGS):
        return True
    if content.count("(evidence:") < 8:
        return True
    return False


def _load_interpreted_task_papers(
    db: Session,
    task: models.Task,
) -> list[dict[str, Any]]:
    interpreted = []
    papers = db.query(models.Paper).filter(models.Paper.task_id == task.id).all()
    for paper in papers:
        interpretation = db.query(models.Interpretation).filter(
            models.Interpretation.paper_id == paper.id
        ).first()
        if not interpretation:
            continue
        interpreted.append(
            {
                "paper_id": paper.id,
                "title": paper.title,
                "source": paper.source,
                "source_url": paper.source_url,
                "status": paper.status,
                "interpretation": interpretation.content,
                "template_used": interpretation.template_used,
            }
        )
    return interpreted


def _generate_task_report_content(
    *,
    task: models.Task,
    report_query: str,
    report_model: str,
    interpreted: list[dict[str, Any]],
    trace: dict[str, Any],
    progress_callback: Callable[[str, int, int, str], None] | None = None,
) -> tuple[str, str]:
    brief = _build_task_report_brief(
        user_query=report_query,
        task=task,
        trace=trace,
    )
    selected_records, reading_results, weak_signals = _build_task_report_inputs(
        task=task,
        user_query=report_query,
        interpreted=interpreted,
        trace=trace,
    )
    runner = BoundedResearchRunner(model=report_model)
    evidence_steps = max(len(reading_results), 1)
    base_total_steps = 1 + evidence_steps + 1 + 1
    after_preparing = 1
    after_evidence = after_preparing + evidence_steps
    after_outline = after_evidence + 1
    if progress_callback is not None:
        progress_callback("preparing", after_preparing, base_total_steps, "已整理任务中的精读论文与弱信号")
        progress_callback("evidence", after_preparing, base_total_steps, "开始逐篇提取证据卡")
    evidence_pack = runner._build_evidence_pack(
        user_query=report_query,
        brief=brief,
        selected_papers=selected_records,
        reading_results=reading_results,
        weak_signals=weak_signals,
        progress_callback=(
            (
                lambda completed, total, message: progress_callback(
                    "evidence",
                    after_preparing + min(max(completed, 0), evidence_steps),
                    base_total_steps,
                    message,
                )
            )
            if progress_callback is not None
            else None
        ),
    )
    if progress_callback is not None:
        progress_callback("outline", after_evidence, base_total_steps, "正在构建报告提纲")
    report_outline = runner._build_report_outline(
        user_query=report_query,
        brief=brief,
        evidence_pack=evidence_pack,
    )
    if progress_callback is not None:
        progress_callback("outline", after_outline, base_total_steps, "报告提纲已完成")
        progress_callback("writing", after_outline, base_total_steps, "正在撰写最终报告")
    content = runner._summarize(
        user_query=report_query,
        brief=brief,
        evidence_pack=evidence_pack,
        report_outline=report_outline,
    )
    repaired = False
    if _report_needs_repair(content):
        repaired = True
        if progress_callback is not None:
            progress_callback("repairing", after_outline + 1, base_total_steps + 1, "初稿未满足格式要求，正在修复结构与引用")
        content = runner._repair_report(
            user_query=report_query,
            brief=brief,
            evidence_pack=evidence_pack,
            report_outline=report_outline,
            draft_report=content,
        )
        if progress_callback is not None:
            progress_callback("repairing", base_total_steps + 1, base_total_steps + 1, "报告修复完成")
    content = _sanitize_report_visible_paper_ids(
        content=content,
        reading_results=reading_results,
    )
    if progress_callback is not None:
        final_total = base_total_steps + 1 if repaired else base_total_steps
        final_completed = final_total
        progress_callback("writing", final_completed, final_total, "最终报告已生成")
    return _rewrite_report_evidence_links(
        content=content,
        task_id=task.id,
        selected_records=selected_records,
        reading_results=reading_results,
        weak_signals=weak_signals,
    )


def _get_template_id(db: Session, template_id: str | None) -> str:
    if template_id:
        template = db.query(models.Template).filter(
            models.Template.id == template_id,
            models.Template.user_id == DEFAULT_USER_ID,
        ).first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        return template.id
    return ensure_default_template(db).id


def _load_target_assets():
    if DEFAULT_SUMMARY_PATH.exists():
        return load_search_assets(DEFAULT_SUMMARY_PATH)
    return load_default_search_assets()


def _available_target_years() -> list[int]:
    return sorted({int(asset.year) for asset in _load_target_assets()})


def _effective_target_years(years: list[int] | None) -> list[int]:
    return normalize_target_years(years, available_years=_available_target_years())


def _ensure_search_assets_available() -> None:
    if _load_target_assets():
        return
    raise HTTPException(
        status_code=400,
        detail="No searchable research data is installed on this machine. Download packs from GitHub Releases first.",
    )


def run_self_check() -> schemas.SelfCheckResponse:
    items: list[schemas.SelfCheckItem] = []

    def add_item(
        *,
        key: str,
        label: str,
        status: str,
        severity: str,
        message: str,
        hint: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        items.append(
            schemas.SelfCheckItem(
                key=key,
                label=label,
                status=status,
                severity=severity,
                message=message,
                hint=hint,
                details=details,
            )
        )

    db_path = ROOT_DIR / "data" / "app.db"
    add_item(
        key="project_root",
        label="项目目录",
        status="ok" if ROOT_DIR.exists() else "error",
        severity="required",
        message=f"项目根目录: {ROOT_DIR}",
        details={"path": str(ROOT_DIR)},
    )
    add_item(
        key="database",
        label="本地数据库",
        status="ok" if db_path.exists() else "warning",
        severity="required",
        message="数据库文件已存在" if db_path.exists() else "数据库文件尚未生成",
        hint=None if db_path.exists() else "先启动一次后端，系统会自动创建 data/app.db。",
        details={"path": str(db_path)},
    )

    paperlists_dir = ROOT_DIR / "data" / "resource" / "paperlists"
    paperlists_exists = paperlists_dir.exists()
    add_item(
        key="paperlists",
        label="原始会议资源",
        status="ok" if paperlists_exists else "warning",
        severity="optional",
        message="已找到 paperlists 原始资源" if paperlists_exists else "未找到 paperlists 原始资源",
        hint=None if paperlists_exists else "如果这台机器只负责使用，不负责构建 pack，可以忽略；如果要本地构建 pack，请同步 data/resource/paperlists。",
        details={"path": str(paperlists_dir)},
    )

    installed_packs = PackManager().list_installed()
    add_item(
        key="installed_packs",
        label="已安装搜索数据",
        status="ok" if installed_packs else "warning",
        severity="required",
        message=f"已安装 {len(installed_packs)} 个 pack" if installed_packs else "本机还没有安装任何 research pack",
        hint=None if installed_packs else "先去 Packs 页面，从 GitHub Releases 下载需要的会议包。",
        details={
            "count": len(installed_packs),
            "sample": [
                f"{item.conference}-{item.year}-{item.version}"
                for item in installed_packs[:5]
            ],
        },
    )

    assets = _load_target_assets()
    add_item(
        key="search_assets",
        label="可搜索资产",
        status="ok" if assets else "warning",
        severity="required",
        message=f"当前可搜索资产 {len(assets)} 个" if assets else "当前没有可搜索资产",
        hint=None if assets else "安装 pack 之后，Research 页面才能真正执行搜索。",
        details={
            "count": len(assets),
            "sample": [f"{asset.conference}-{asset.year}" for asset in assets[:8]],
        },
    )

    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        add_item(
            key="gemini_api",
            label="Gemini API",
            status="error",
            severity="required",
            message="GEMINI_API_KEY 未配置",
            hint="在后端环境或 backend/.env 中配置 GEMINI_API_KEY。",
        )
    else:
        try:
            client = genai.Client(api_key=gemini_key, http_options={"api_version": "v1beta"})
            response = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents="ping",
                config=types.GenerateContentConfig(max_output_tokens=1),
            )
            add_item(
                key="gemini_api",
                label="Gemini API",
                status="ok",
                severity="required",
                message="Gemini API 可用",
                details={
                    "model": "gemini-3-flash-preview",
                    "response_preview": (getattr(response, "text", "") or "").strip()[:40],
                },
            )
        except Exception as exc:
            add_item(
                key="gemini_api",
                label="Gemini API",
                status="error",
                severity="required",
                message=f"Gemini API 检查失败: {exc}",
                hint="确认 API key 正确、账户可用，并且目标模型有权限访问。",
            )

    dashscope_key = os.getenv("DASHSCOPE_API_KEY")
    if not dashscope_key:
        add_item(
            key="dashscope_api",
            label="DashScope API",
            status="error",
            severity="required",
            message="DASHSCOPE_API_KEY 未配置",
            hint="在后端环境或 shell 环境中配置 DASHSCOPE_API_KEY。",
        )
    else:
        try:
            embedding_client = DashScopeEmbeddingClient(api_key=dashscope_key, batch_size=1)
            result = embedding_client.embed_text("ping")
            add_item(
                key="dashscope_api",
                label="DashScope API",
                status="ok",
                severity="required",
                message="DashScope embedding API 可用",
                details={"embedding_dim": len(result.embedding)},
            )
        except Exception as exc:
            add_item(
                key="dashscope_api",
                label="DashScope API",
                status="error",
                severity="required",
                message=f"DashScope API 检查失败: {exc}",
                hint="确认百炼 API key 正确，且 embedding 服务已开通。",
            )

    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        add_item(
            key="github_api",
            label="GitHub Release 上传",
            status="warning",
            severity="optional",
            message="GITHUB_TOKEN 未配置",
            hint="如果这台机器只负责搜索和阅读，可以忽略；如果要上传 packs，请配置 GITHUB_TOKEN。",
        )
    else:
        try:
            response = requests.get(
                "https://api.github.com/user",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {github_token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=20,
            )
            if response.status_code == 200:
                payload = response.json()
                add_item(
                    key="github_api",
                    label="GitHub Release 上传",
                    status="ok",
                    severity="optional",
                    message="GitHub token 可用",
                    details={"login": payload.get("login")},
                )
            else:
                add_item(
                    key="github_api",
                    label="GitHub Release 上传",
                    status="warning",
                    severity="optional",
                    message=f"GitHub token 检查失败: HTTP {response.status_code}",
                    hint="如果要上传 pack，请确认 token 仍然有效，并有目标仓库的写权限。",
                )
        except Exception as exc:
            add_item(
                key="github_api",
                label="GitHub Release 上传",
                status="warning",
                severity="optional",
                message=f"GitHub token 检查失败: {exc}",
                hint="如果要上传 pack，请确认网络可用且 token 正确。",
            )

    required_errors = [item for item in items if item.severity == "required" and item.status == "error"]
    required_warnings = [item for item in items if item.severity == "required" and item.status == "warning"]
    optional_warnings = [item for item in items if item.severity == "optional" and item.status != "ok"]

    if required_errors:
        overall_status = "error"
        summary = f"自检发现 {len(required_errors)} 个关键问题，系统还不能完整工作。"
    elif required_warnings or optional_warnings:
        overall_status = "warning"
        summary = "自检通过，但有一些缺失项需要补齐。"
    else:
        overall_status = "ok"
        summary = "自检通过，核心环境和 API 都可用。"

    return schemas.SelfCheckResponse(
        overall_status=overall_status,
        summary=summary,
        checked_at=datetime.datetime.utcnow(),
        items=items,
    )


def _build_agent_trace(selection, *, user_query: str, max_search_rounds: int, max_queries_per_round: int, max_full_reads: int) -> dict[str, Any]:
    detail_lookup = {
        (item["conference"], int(item["year"]), item["paper_id"]): item
        for item in selection.detail_results
    }
    final_selected = []
    for item in selection.selected_papers:
        detail = detail_lookup.get((item["conference"], int(item["year"]), item["paper_id"]), {})
        final_selected.append(
            {
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

    rounds = []
    for round_item in selection.rounds:
        round_selected = []
        for selected in round_item.selected_papers:
            matched = next(
                (
                    item for item in round_item.reranked_results
                    if item["paper"]["conference"] == selected.conference
                    and int(item["paper"]["year"]) == selected.year
                    and item["paper"]["paper_id"] == selected.paper_id
                ),
                None,
            )
            round_selected.append(
                {
                    "论文标题": selected.title or (matched["paper"]["title"] if matched else selected.paper_id),
                    "会议": conference_display_name(selected.conference),
                    "年份": int(selected.year),
                    "方向": selected.axis,
                    "选择理由": selected.reason,
                    "优先级": int(selected.priority),
                    "精排分数": round(float(matched["rerank_score"]), 4) if matched else None,
                }
            )
        rounds.append(
            {
                "轮次": round_item.round_index,
                "本轮查询": round_item.queries,
                "粗排命中数": sum(len(item["results"]) for item in round_item.coarse_results),
                "合并候选数": len(round_item.merged_candidates),
                "精排候选数": len(round_item.reranked_results),
                "继续搜索": bool(round_item.decision.continue_search),
                "本轮判断": round_item.decision.rationale,
                "缺失方向": round_item.decision.missing_axes,
                "下一轮查询": round_item.decision.additional_queries,
                "本轮选中文章": round_selected,
                "本轮候选判断": [
                    {
                        "论文标题": item.title,
                        "会议": conference_display_name(item.conference),
                        "年份": int(item.year),
                        "是否精读": bool(item.should_read),
                        "方向": item.axis,
                        "判断理由": item.reason,
                        "优先级": int(item.priority),
                        "粗排分数": round(float(item.coarse_score), 4),
                        "精排分数": round(float(item.rerank_score), 4),
                    }
                    for item in round_item.candidate_admissions
                ],
            }
        )

    return {
        "用户问题": user_query,
        "预算": {
            "最大搜索轮数": max_search_rounds,
            "每轮最多查询数": max_queries_per_round,
            "最大全文精读数": max_full_reads,
        },
        "研究简报": {
            "研究目标": selection.brief.research_goal,
            "搜索方向": selection.brief.search_axes,
            "初始查询": selection.brief.initial_queries,
            "精排查询": selection.brief.rerank_query,
            "目标会议": [conference_display_name(code) for code in selection.brief.target_conferences],
            "目标年份": [int(year) for year in selection.brief.target_years],
            "精读提示词": selection.brief.reading_prompts,
        },
        "搜索轮次": rounds,
        "最终选中文章": final_selected,
        "汇总": {
            "实际搜索轮数": len(selection.rounds),
            "最终选中文章数": len(final_selected),
        },
    }


def list_target_options() -> schemas.DeepResearchTargetOptionsResponse:
    assets = _load_target_assets()
    years = sorted({int(asset.year) for asset in assets}, reverse=True)
    grouped: dict[str, list[schemas.DeepResearchTargetYearCount]] = defaultdict(list)
    totals: dict[str, int] = defaultdict(int)

    for asset in assets:
        grouped[asset.conference].append(
            schemas.DeepResearchTargetYearCount(
                year=int(asset.year),
                paper_count=int(asset.paper_count),
            )
        )
        totals[asset.conference] += int(asset.paper_count)

    conferences = [
        schemas.DeepResearchTargetConference(
            code=conference,
            label=conference_display_name(conference),
            years=sorted(items, key=lambda item: item.year, reverse=True),
            total_paper_count=totals[conference],
        )
        for conference, items in sorted(grouped.items(), key=lambda entry: conference_display_name(entry[0]))
    ]
    default_years = sorted(_effective_target_years(None), reverse=True)
    return schemas.DeepResearchTargetOptionsResponse(
        conferences=conferences,
        years=years,
        default_years=default_years,
    )


def list_release_packs(
    owner: str = DEFAULT_RELEASE_OWNER,
    repo: str = DEFAULT_RELEASE_REPO,
) -> schemas.ReleaseListResponse:
    url = f"https://api.github.com/repos/{owner}/{repo}/releases"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "paperreader-deep-research",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch GitHub releases: {exc}") from exc

    releases: list[schemas.ReleaseInfo] = []
    for item in payload:
        assets = [
            schemas.ReleaseAsset(
                id=int(asset["id"]),
                name=asset["name"],
                size=int(asset["size"]),
                download_count=int(asset.get("download_count", 0)),
                browser_download_url=asset["browser_download_url"],
                updated_at=asset["updated_at"],
            )
            for asset in item.get("assets", [])
            if str(asset.get("name", "")).endswith(".zip")
        ]
        releases.append(
            schemas.ReleaseInfo(
                id=int(item["id"]),
                tag_name=item["tag_name"],
                name=item.get("name") or item["tag_name"],
                draft=bool(item.get("draft", False)),
                prerelease=bool(item.get("prerelease", False)),
                published_at=item.get("published_at"),
                html_url=item["html_url"],
                assets=assets,
            )
        )
    return schemas.ReleaseListResponse(owner=owner, repo=repo, releases=releases)


def install_release_assets(
    payload: schemas.ReleaseInstallRequest,
) -> schemas.ReleaseInstallResponse:
    manager = PackManager()
    results: list[schemas.ReleaseInstallResult] = []
    installed_count = 0
    for asset in payload.assets:
        try:
            installed = manager.install_from_url(RemotePackSpec(url=asset.download_url))
            results.append(
                schemas.ReleaseInstallResult(
                    release_tag=asset.release_tag,
                    asset_name=asset.asset_name,
                    installed=True,
                    conference=installed.conference,
                    year=installed.year,
                    version=installed.version,
                    install_dir=str(installed.install_dir),
                )
            )
            installed_count += 1
        except Exception as exc:
            results.append(
                schemas.ReleaseInstallResult(
                    release_tag=asset.release_tag,
                    asset_name=asset.asset_name,
                    installed=False,
                    error=str(exc),
                )
            )
    return schemas.ReleaseInstallResponse(
        ok=installed_count == len(results) if results else True,
        installed_count=installed_count,
        results=results,
    )


def list_local_packs() -> list[schemas.ResearchPackInfo]:
    packs_root = ROOT_DIR / "data" / "research" / "packs"
    results: list[schemas.ResearchPackInfo] = []
    if not packs_root.exists():
        return results
    for manifest_path in sorted(packs_root.glob("*/*/*.manifest.json")):
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        pack_path = manifest_path.with_suffix("").with_suffix(".zip")
        sha256_path = manifest_path.with_suffix("").with_suffix(".sha256")
        results.append(
            schemas.ResearchPackInfo(
                conference=str(data["conference"]).lower(),
                year=int(data["year"]),
                version=str(data["version"]),
                pack_name=str(data["pack_name"]),
                pack_path=str(pack_path),
                manifest_path=str(manifest_path),
                sha256_path=str(sha256_path),
                pack_size_bytes=pack_path.stat().st_size if pack_path.exists() else 0,
                exists=pack_path.exists(),
            )
        )
    return results


def list_installed_packs() -> list[schemas.InstalledResearchPackInfo]:
    manager = PackManager()
    results: list[schemas.InstalledResearchPackInfo] = []
    for item in manager.list_installed():
        results.append(
            schemas.InstalledResearchPackInfo(
                conference=item.conference,
                year=item.year,
                version=item.version,
                pack_name=f"{item.conference}-{str(item.year)[-2:]}",
                install_dir=str(item.install_dir),
                manifest_path=str(item.manifest_path),
                normalized_path=str(item.normalized_path),
                embedding_path=str(item.embedding_path),
            )
        )
    return results


def list_pack_target_options() -> schemas.PackTargetOptionsResponse:
    ensure_paperlists_repo()
    files = list_conference_files()
    grouped: dict[str, set[int]] = defaultdict(set)
    all_years: set[int] = set()

    for item in files:
        grouped[item.conference].add(int(item.year))
        all_years.add(int(item.year))

    years = sorted(all_years, reverse=True)
    default_years = years[:3]
    conferences = [
        schemas.PackTargetConference(
            code=conference,
            label=conference_display_name(conference),
            years=sorted(grouped[conference], reverse=True),
        )
        for conference in sorted(grouped.keys(), key=conference_display_name)
    ]
    return schemas.PackTargetOptionsResponse(
        conferences=conferences,
        years=years,
        default_years=default_years,
    )


def create_pack_build_job(
    db: Session,
    payload: schemas.ResearchPackBuildRequest,
) -> schemas.PackBuildJob:
    return pack_build_service.create_pack_build_job(db, payload)


def list_pack_build_jobs(db: Session) -> list[schemas.PackBuildJob]:
    return pack_build_service.list_pack_build_jobs(db)


def resume_pack_build_job(db: Session, job_id: str) -> schemas.PackBuildJob:
    return pack_build_service.resume_pack_build_job(db, job_id)


def build_packs(payload: schemas.ResearchPackBuildRequest) -> schemas.ResearchPackBuildResponse:
    ensure_paperlists_repo()
    available_files = list_conference_files()
    available_conferences = sorted({item.conference for item in available_files})
    available_years = sorted({int(item.year) for item in available_files})

    conferences = payload.conferences or available_conferences
    years = payload.years or available_years
    asset_results, missing = build_online_assets(
        conferences=conferences,
        years=years,
    )
    if not asset_results:
        raise HTTPException(status_code=400, detail="No available conference/year source files for the selected pack targets")

    summary_path = ROOT_DIR / "data" / "research" / "build" / "build_summary_pack_request.json"
    write_summary(asset_results, missing, summary_path)
    packager = Packager(build_summary_path=summary_path)
    results = packager.build_many(
        conferences=[item.conference for item in asset_results],
        years=[int(item.year) for item in asset_results],
        version=payload.version or "v1",
    )
    serialized = [
        schemas.ResearchPackInfo(
            conference=item.conference,
            year=item.year,
            version=item.version,
            pack_name=item.pack_name,
            pack_path=str(item.pack_path),
            manifest_path=str(item.manifest_path),
            sha256_path=str(item.sha256_path),
            pack_size_bytes=item.pack_size_bytes,
            exists=item.pack_path.exists(),
        )
        for item in results
    ]
    return schemas.ResearchPackBuildResponse(ok=True, results=serialized)


def upload_pack_to_github_release(payload: schemas.ResearchPackUploadRequest) -> schemas.ResearchPackUploadResponse:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise HTTPException(status_code=500, detail="GITHUB_TOKEN is not configured")

    built = _resolve_or_build_local_pack(
        conference=payload.conference,
        year=payload.year,
        version=payload.version or "v1",
    )

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "paperreader-deep-research",
    }
    repo_api = f"https://api.github.com/repos/{payload.owner}/{payload.repo}"
    release = _get_or_create_release(
        repo_api=repo_api,
        tag=payload.tag,
        headers=headers,
        release_name=payload.release_name or payload.tag,
        release_body=payload.release_body or "",
        draft=payload.draft,
        prerelease=payload.prerelease,
    )

    upload_url = str(release["upload_url"]).split("{", 1)[0]
    for asset_name in (built.manifest_path.name, built.sha256_path.name):
        _delete_asset_if_exists(release=release, asset_name=asset_name, headers=headers)

    uploaded_assets: list[str] = []
    for path in (built.pack_path,):
        _delete_asset_if_exists(release=release, asset_name=path.name, headers=headers)
        with path.open("rb") as f:
            response = requests.post(
                f"{upload_url}?name={path.name}",
                headers={**headers, "Content-Type": "application/octet-stream"},
                data=f,
                timeout=300,
            )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to upload asset {path.name}: {response.status_code} {response.text}",
            )
        uploaded_assets.append(path.name)

    return schemas.ResearchPackUploadResponse(
        ok=True,
        release_id=int(release["id"]),
        release_url=str(release["html_url"]),
        uploaded_assets=uploaded_assets,
    )


def _get_or_create_release(
    repo_api: str,
    tag: str,
    headers: dict[str, str],
    release_name: str,
    release_body: str,
    draft: bool,
    prerelease: bool,
) -> dict[str, Any]:
    response = requests.get(f"{repo_api}/releases/tags/{tag}", headers=headers, timeout=60)
    if response.status_code == 200:
        return response.json()
    if response.status_code != 404:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to query release tag {tag}: {response.status_code} {response.text}",
        )
    create_response = requests.post(
        f"{repo_api}/releases",
        headers=headers,
        json={
            "tag_name": tag,
            "name": release_name,
            "body": release_body,
            "draft": draft,
            "prerelease": prerelease,
        },
        timeout=60,
    )
    if create_response.status_code >= 400:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create release {tag}: {create_response.status_code} {create_response.text}",
        )
    return create_response.json()


def _delete_asset_if_exists(release: dict[str, Any], asset_name: str, headers: dict[str, str]) -> None:
    for asset in release.get("assets", []):
        if asset.get("name") != asset_name:
            continue
        response = requests.delete(asset["url"], headers=headers, timeout=60)
        if response.status_code not in (204, 404):
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete existing asset {asset_name}: {response.status_code} {response.text}",
            )


def _resolve_or_build_local_pack(
    conference: str,
    year: int,
    version: str,
):
    normalized_conference = conference.lower().strip()
    local_pack = next(
        (
            item
            for item in list_local_packs()
            if item.conference == normalized_conference and int(item.year) == int(year) and item.version == version and item.exists
        ),
        None,
    )
    if local_pack is not None:
        class _LocalBuiltPack:
            pack_path = Path(local_pack.pack_path)
            manifest_path = Path(local_pack.manifest_path)
            sha256_path = Path(local_pack.sha256_path)
        return _LocalBuiltPack()

    packager = Packager()
    return packager.build_pack(
        conference=normalized_conference,
        year=year,
        version=version,
    )


def search_conference_papers(payload: schemas.ConferenceSearchRequest) -> schemas.ConferenceSearchResponse:
    _ensure_search_assets_available()
    tools = SearchTools()
    effective_years = _effective_target_years(payload.years)
    result = tools.coarse_search(
        query=payload.query,
        conferences=payload.conferences,
        years=effective_years,
        top_k_per_asset=payload.top_k_per_asset,
        top_k_global=payload.top_k_global,
    )
    hits = [
        schemas.ConferenceSearchHit(
            **item["paper"],
            coarse_score=float(item["coarse_score"]),
        )
        for item in result["results"]
    ]
    return schemas.ConferenceSearchResponse(
        query=result["query"],
        asset_count=result["asset_count"],
        elapsed_sec=float(result["elapsed_sec"]),
        results=hits,
    )


def create_task_from_selection(
    db: Session,
    payload: schemas.TaskFromSelectionCreate,
) -> schemas.DeepResearchTaskCreateResponse:
    if not payload.selected_papers:
        raise HTTPException(status_code=400, detail="selected_papers is required")

    template_id = _get_template_id(db, payload.template_id)
    _ensure_search_assets_available()
    tools = SearchTools()
    paper_refs = [item.model_dump() for item in payload.selected_papers]
    details = tools.get_paper_details(paper_refs)
    selected = details["results"]
    if not selected:
        raise HTTPException(status_code=400, detail="No selected papers were resolved")

    task = models.Task(
        user_id=DEFAULT_USER_ID,
        name=payload.name.strip(),
        description=(payload.description or "Created from conference search selection").strip(),
        template_id=template_id,
        custom_reading_prompts_json=serialize_prompt_list(payload.custom_reading_prompts),
        model_name=payload.model_name or "gemini-3-flash-preview",
        status="running",
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    imported_count = 0
    for item in selected:
        db.add(
            models.Paper(
                task_id=task.id,
                title=item["title"],
                source_url=item.get("source_url"),
                status="queued",
            )
        )
        imported_count += 1

    db.commit()
    return schemas.DeepResearchTaskCreateResponse(
        ok=True,
        task_id=task.id,
        task_name=task.name,
        imported_count=imported_count,
    )


def create_task_from_auto_research(
    db: Session,
    payload: schemas.AutoResearchTaskCreate,
) -> schemas.DeepResearchTaskCreateResponse:
    _ensure_search_assets_available()
    template_id = _get_template_id(db, payload.template_id)
    effective_max_search_rounds = min(20, max(1, int(payload.max_search_rounds or 3)))
    effective_max_queries_per_round = min(10, max(1, int(payload.max_queries_per_round or 4)))
    effective_max_full_reads = max(1, int(payload.max_full_reads or 8))
    effective_years = _effective_target_years(payload.years)
    initial_trace = {
        "_agent_config": {
            "query": payload.query,
            "conferences": payload.conferences or [],
            "years": effective_years,
            "template_id": template_id,
            "model_name": payload.model_name or "gemini-3-flash-preview",
            "custom_reading_prompts": payload.custom_reading_prompts or [],
            "max_search_rounds": effective_max_search_rounds,
            "max_queries_per_round": effective_max_queries_per_round,
            "max_full_reads": effective_max_full_reads,
        },
        "_agent_runtime": {
            "state": "queued",
            "current_stage": "等待开始",
        },
        "用户问题": payload.query,
        "预算": {
            "最大搜索轮数": effective_max_search_rounds,
            "每轮最多查询数": effective_max_queries_per_round,
            "最大全文精读数": effective_max_full_reads,
        },
        "研究简报": None,
        "搜索轮次": [],
        "最终选中文章": [],
        "汇总": {
            "实际搜索轮数": 0,
            "最终选中文章数": 0,
        },
    }

    task = models.Task(
        user_id=DEFAULT_USER_ID,
        name=(payload.name or f"Deep Research: {payload.query[:48]}").strip(),
        description=(payload.description or f"Agent-selected from query: {payload.query}").strip(),
        template_id=template_id,
        custom_reading_prompts_json=serialize_prompt_list(payload.custom_reading_prompts),
        agent_trace_json=json.dumps(initial_trace, ensure_ascii=False),
        model_name=payload.model_name or "gemini-3-flash-preview",
        status="preparing",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return schemas.DeepResearchTaskCreateResponse(
        ok=True,
        task_id=task.id,
        task_name=task.name,
        imported_count=0,
    )
def generate_task_report(
    db: Session,
    task_id: str,
    payload: schemas.TaskReportGenerateRequest,
) -> schemas.DeepResearchReport:
    task = db.query(models.Task).filter(
        models.Task.id == task_id,
        models.Task.user_id == DEFAULT_USER_ID,
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    interpreted = _load_interpreted_task_papers(db, task)

    if not interpreted:
        raise HTTPException(status_code=400, detail="Task has no interpreted papers yet")
    if len(interpreted) < MIN_REPORT_PAPERS:
        raise HTTPException(
            status_code=400,
            detail=f"Task needs at least {MIN_REPORT_PAPERS} interpreted papers before generating a report",
        )

    trace = _parse_json_dict(task.agent_trace_json)
    report_query = payload.query or trace.get("用户问题") or task.description or task.name
    report_model = payload.model_name or task.model_name or "gemini-3-flash-preview"
    content, generated_source_meta = _generate_task_report_content(
        task=task,
        report_query=report_query,
        report_model=report_model,
        interpreted=interpreted,
        trace=trace,
    )
    if not content.strip():
        raise HTTPException(status_code=500, detail="Empty report response from model")

    report = db.query(models.DeepResearchReport).filter(
        models.DeepResearchReport.task_id == task.id
    ).first()
    if report is None:
        report = models.DeepResearchReport(
            task_id=task.id,
            query=report_query,
            source_type=payload.source_type or "task",
            source_meta=generated_source_meta,
            model_name=report_model,
            status="completed",
            content=content,
        )
        db.add(report)
    else:
        report.query = report_query
        report.source_type = payload.source_type or report.source_type
        report.source_meta = generated_source_meta
        report.model_name = report_model
        report.status = "completed"
        report.content = content
    db.commit()
    db.refresh(report)
    return _serialize_report(report)


def get_task_report(db: Session, task_id: str) -> schemas.DeepResearchReport | None:
    report = db.query(models.DeepResearchReport).join(models.Task).filter(
        models.DeepResearchReport.task_id == task_id,
        models.Task.user_id == DEFAULT_USER_ID,
    ).first()
    if not report:
        return None
    return _serialize_report(report)
