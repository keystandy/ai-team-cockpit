from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .adapters import AdapterRegistry, AgentResult
from .config import Settings
from .security import redact, sha256_file
from .store import TeamStore


IGNORED_PARTS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    "runtime",
}
TEAM_CONTEXT_FILES = (
    "01-老板开局词.md",
    "02-员工清单.md",
    "03-团队规矩.md",
)
URL_PATTERN = re.compile(
    r"https?://[^\s<>\"')\]，。；：！？、（）【】]+"
)


def workspace_snapshot(workspace: Path) -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    for path in workspace.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(workspace)
        if any(part in IGNORED_PARTS for part in relative.parts):
            continue
        if path.name.endswith((".pyc", ".pyo")):
            continue
        stat = path.stat()
        snapshot[relative.as_posix()] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


def changed_files(
    before: dict[str, tuple[int, int]], after: dict[str, tuple[int, int]]
) -> list[str]:
    result = []
    for path in sorted(set(before) | set(after)):
        if path not in before:
            result.append(f"A {path}")
        elif path not in after:
            result.append(f"D {path}")
        elif before[path] != after[path]:
            result.append(f"M {path}")
    return result


def workspace_context(workspace: Path, max_bytes: int = 18000) -> str:
    chunks = []
    used = 0
    for path in sorted(workspace.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(workspace)
        if any(part in IGNORED_PARTS for part in relative.parts):
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if len(raw) > 12000 or b"\x00" in raw[:2048]:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        block = f'\n<file path="{relative.as_posix()}">\n{text}\n</file>\n'
        size = len(block.encode("utf-8"))
        if used + size > max_bytes:
            break
        chunks.append(block)
        used += size
    return "".join(chunks) or "(工作区当前没有可读取的文本文件)"


def team_context(max_bytes: int = 9000) -> str:
    root = Path(__file__).resolve().parent.parent.parent
    chunks = []
    used = 0
    for name in TEAM_CONTEXT_FILES:
        path = root / name
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        block = f"\n<team-document path=\"{name}\">\n{text}\n</team-document>\n"
        size = len(block.encode("utf-8"))
        if used + size > max_bytes:
            remaining = max_bytes - used
            if remaining > 200:
                chunks.append(block.encode("utf-8")[:remaining].decode("utf-8", errors="ignore"))
            break
        chunks.append(block)
        used += size
    return "".join(chunks) or "(团队文档不可用)"


def extract_urls(text: str, limit: int = 8) -> list[str]:
    result = []
    for match in URL_PATTERN.findall(text):
        url = match.rstrip(".,;:!?)，。；：）]")
        if url not in result:
            result.append(url)
        if len(result) >= limit:
            break
    return result


def _probe_url(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 AI-Team-Link-Audit/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            status = getattr(response, "status", 200)
            final_url = response.geturl()
            raw = response.read(180000)
            content_type = response.headers.get("Content-Type", "")
        title = ""
        published = ""
        if "html" in content_type.lower() or raw.lstrip().startswith(b"<"):
            text = raw.decode("utf-8", errors="replace")
            title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", text)
            if title_match:
                title = re.sub(r"\s+", " ", title_match.group(1)).strip()[:180]
            date_patterns = (
                r'(?is)<meta[^>]+(?:property|name)=["\'](?:article:published_time|datePublished|publish-date|date)["\'][^>]+content=["\']([^"\']+)',
                r'(?is)<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:article:published_time|datePublished|publish-date|date)["\']',
                r'(?is)<time[^>]+datetime=["\']([^"\']+)',
            )
            for pattern in date_patterns:
                match = re.search(pattern, text)
                if match:
                    published = match.group(1)[:100]
                    break
        parts = [f"HTTP {status}", f"final={final_url}"]
        if title:
            parts.append(f"title={title}")
        if published:
            parts.append(f"published={published}")
        return " | ".join(parts)
    except urllib.error.HTTPError as exc:
        return f"HTTP {exc.code} | final={url} | error={exc.reason}"
    except Exception as exc:
        return f"ERROR | final={url} | error={type(exc).__name__}: {exc}"


def audit_links(text: str, limit: int = 8) -> str:
    urls = extract_urls(text, limit)
    if not urls:
        return ""
    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(4, len(urls))) as executor:
        futures = {executor.submit(_probe_url, url): url for url in urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                results[url] = future.result()
            except Exception as exc:
                results[url] = f"ERROR | final={url} | error={type(exc).__name__}: {exc}"
    lines = ["## 自动链接探测", "以下为机器访问结果，仍需判断页面内容是否支持新闻事实。"]
    for url in urls:
        lines.append(f"- {url} -> {results.get(url, 'ERROR')}")
    return "\n".join(lines)


def build_plan(goal: str) -> list[dict[str, Any]]:
    wants_research = bool(re.search(r"查|最新|联网|图片|看图|资料|研究", goal))
    wants_change = bool(
        re.search(
            r"编写|写代码|修改|改代码|实现|修复|开发|新增|删除|重构|安装|部署",
            goal,
        )
    )
    tasks: list[dict[str, Any]] = []
    if wants_research:
        tasks.append(
            {
                "role": "research",
                "agent_id": "dou",
                "title": "检索与资料整理",
                "deps": [],
                "acceptance": "交付带来源的检索结果和关键事实清单",
            }
        )
    plan_deps = [tasks[0]["title"]] if tasks else []
    if wants_change:
        tasks.append(
            {
                "role": "plan",
                "agent_id": "shen",
                "title": "方案拆解与风险分析",
                "deps": plan_deps,
                "acceptance": "输出可执行步骤、依赖、风险和验收标准",
            }
        )
    else:
        tasks.append(
            {
                "role": "analyze",
                "agent_id": "shen",
                "title": "分析与结论",
                "deps": plan_deps,
                "acceptance": "直接交付满足目标的最终分析、证据、风险和改进建议",
            }
        )
    dependent = tasks[-1]["title"]
    if wants_change:
        tasks.append(
            {
                "role": "implement",
                "agent_id": "ku",
                "title": "工程实现",
                "deps": [dependent],
                "acceptance": "实现目标变更，提供文件路径、测试命令和结果",
                "max_attempts": 2,
            }
        )
        dependent = tasks[-1]["title"]
    tasks.append(
        {
            "role": "review",
            "agent_id": "ke",
            "title": "独立复核",
            "deps": [dependent],
            "acceptance": "给出 PASS 或 RETURN，并附具体文件和证据",
        }
    )
    return tasks


def build_task_spec(goal: str, mode_override: str | None = None) -> dict[str, Any]:
    mode = (mode_override or "auto").strip().lower()
    if mode == "auto":
        if re.search(r"近\s*72\s*小时|近\s*3\s*天|三天", goal):
            mode = "last_72h"
        elif re.search(r"近\s*24\s*小时|过去一天|昨天", goal):
            mode = "last_24h"
        elif re.search(r"发生|快讯", goal):
            mode = "today_event"
        elif re.search(r"新闻|资讯|最新|今天|今日", goal):
            mode = "today_published"
        else:
            mode = "general"
    labels = {
        "today_event": "今日发生",
        "today_published": "今日刊发",
        "last_24h": "近24小时",
        "last_72h": "近72小时",
        "last_custom": "自定义时间窗口",
        "general": "通用任务",
    }
    if mode not in labels:
        raise ValueError("未知任务模式")
    windows = {
        "today_event": 0,
        "today_published": 0,
        "last_24h": 1,
        "last_72h": 3,
        "last_custom": None,
        "general": None,
    }
    return {
        "mode": mode,
        "mode_label": labels[mode],
        "required_count": requested_count(goal),
        "window_days": windows[mode],
        "strict_event_date": mode == "today_event",
    }


def goal_specific_rules(goal: str, spec: dict[str, Any] | None = None) -> str:
    spec = spec or build_task_spec(goal)
    mode = spec.get("mode", "general")
    if spec.get("accept_shortfall"):
        return (
            "老板已批准本次接受数量不足。复核重点是是否诚实列出缺口、来源、"
            "不可发布项和风险；不得要求继续补足数量。"
        )
    if mode in (
        "today_event",
        "today_published",
        "last_24h",
        "last_72h",
        "last_custom",
    ):
        count = spec.get("required_count") or "用户指定数量"
        today = datetime.now().astimezone().strftime("%Y-%m-%d")
        mode_requirements = {
            "today_event": f"事件发生日必须是 {today}。",
            "today_published": f"报道或首次公开发布日必须是 {today}，事件本身可早于今天。",
            "last_24h": f"报道或首次公开发布必须在截至 {today} 的近24小时内。",
            "last_72h": f"报道或首次公开发布必须在截至 {today} 的近72小时内。",
            "last_custom": (
                f"报道或首次公开发布必须在截至 {today} 的近"
                f"{spec.get('window_days', 3)}天内。"
            ),
        }[mode]
        return (
            f"这是{mode}模式资讯任务。{mode_requirements}"
            f"必须交付 {count} 条符合该时效模式的条目。"
            "每条必须列明事件发生日、首次披露日、报道日、可访问的一手来源链接、"
            "来源等级和新闻分类。评论、宣传稿、聚合短讯必须单列，不能凑入条数。"
            "数量不足时明确说不足，不得用旧闻或无关条目填充。"
        )
    if re.search(r"架构|优点|缺点|改进|方案|设计", goal):
        return (
            "交付最终分析，不交后续计划。列出有依据的优点、缺点和一个最重要的改进方向；"
            "每条结论标注事实或推断，不得虚构运行数据。"
        )
    return (
        "直接满足用户目标；先结论后依据；不确定内容明确标注，"
        "不得用与目标无关的模板段落代替交付。"
    )


def requested_count(goal: str) -> int | None:
    match = re.search(r"(\d+)\s*条", goal)
    return int(match.group(1)) if match else None


def extract_json_object(text: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    candidates: list[dict[str, Any]] = []
    index = 0
    while index < len(text):
        start = text.find("{", index)
        if start < 0:
            break
        try:
            value, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(value, dict):
            candidates.append(value)
        index = start + max(end, 1)
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: len(json.dumps(item, ensure_ascii=False)),
    )


def date_from_text(value: Any) -> date | None:
    match = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", str(value or ""))
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def datetime_from_text(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def source_tier(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text.startswith(("a", "1")) or "一级" in text or "一手" in text:
        return "A"
    if text.startswith(("b", "2")) or "二级" in text:
        return "B"
    if text.startswith(("c", "3")) or "三级" in text:
        return "C"
    return "unknown"


def link_statuses(report: str) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for line in report.splitlines():
        if not line.startswith("- http"):
            continue
        match = re.match(r"- (\S+) -> (?:HTTP (\d+)|ERROR)", line)
        if match:
            statuses[match.group(1)] = match.group(2) or "ERROR"
    return statuses


def validate_news_payload(
    payload: dict[str, Any] | None,
    spec: dict[str, Any],
    link_report: str,
) -> dict[str, Any]:
    if not payload:
        return {
            "structured": False,
            "eligible_count": 0,
            "items": [],
            "error": "未返回结构化 JSON",
        }
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        return {
            "structured": False,
            "eligible_count": 0,
            "items": [],
            "error": "JSON 缺少 items 数组",
        }
    today = datetime.now().astimezone().date()
    mode = spec.get("mode", "general")
    window_days = spec.get("window_days")
    statuses = link_statuses(link_report)
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    checked = []
    eligible_count = 0
    for index, raw in enumerate(raw_items, 1):
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title", "")).strip()
        url = str(raw.get("primary_url") or raw.get("url") or "").strip()
        classification = str(raw.get("classification", "")).strip().lower()
        tier = source_tier(raw.get("source_tier"))
        event_day = date_from_text(raw.get("event_date"))
        first_day = date_from_text(raw.get("first_disclosed_at"))
        published_day = date_from_text(
            raw.get("published_at") or raw.get("report_date")
        )
        published_at = datetime_from_text(
            raw.get("published_at") or raw.get("report_date")
        )
        reasons = []
        if not title:
            reasons.append("缺少标题")
        if not url.startswith(("http://", "https://")):
            reasons.append("缺少可访问 URL")
        if classification not in ("news", "硬新闻", "新闻"):
            reasons.append("不是新闻分类")
        if tier not in ("A", "B"):
            reasons.append("来源等级不足")
        if statuses.get(url) in ("ERROR", "403", "404", "410", "500", "502", "503", "504"):
            reasons.append(f"链接探测失败: HTTP {statuses.get(url)}")
        canonical_url = re.sub(r"[?#].*$", "", url).rstrip("/")
        normalized_title = re.sub(r"\W+", "", title).lower()
        if canonical_url and canonical_url in seen_urls:
            reasons.append("URL 重复")
        if normalized_title and normalized_title in seen_titles:
            reasons.append("标题重复")
        if mode == "today_event":
            if event_day != today:
                reasons.append("事件发生日不是今天")
            if tier != "A":
                reasons.append("今日发生模式要求一手来源")
        elif mode == "last_24h":
            now = datetime.now().astimezone()
            if not published_at or published_at.tzinfo is None:
                reasons.append("近24小时模式要求带时区的 ISO 发布时间")
            elif published_at < now - timedelta(hours=24):
                reasons.append("不在最近24小时窗口")
        elif mode in ("today_published", "last_72h", "last_custom"):
            effective_day = published_day or first_day
            if mode == "today_published":
                if effective_day != today:
                    reasons.append("报道或首次披露日不是今天")
            else:
                days = int(window_days or (1 if mode == "last_24h" else 3))
                if not effective_day or effective_day < today - timedelta(days=days):
                    reasons.append(f"不在最近 {days} 天窗口")
        if not str(raw.get("event_date", "")).strip():
            reasons.append("缺少事件发生日")
        if not str(raw.get("first_disclosed_at", "")).strip():
            reasons.append("缺少首次披露日")
        if not str(raw.get("published_at") or raw.get("report_date") or "").strip():
            reasons.append("缺少报道日")
        eligible = not reasons
        if canonical_url:
            seen_urls.add(canonical_url)
        if normalized_title:
            seen_titles.add(normalized_title)
        if eligible:
            eligible_count += 1
        checked.append(
            {
                "index": index,
                "title": title,
                "url": url,
                "classification": classification,
                "source_tier": tier,
                "eligible": eligible,
                "reasons": reasons,
            }
        )
    return {
        "structured": True,
        "eligible_count": eligible_count,
        "required_count": spec.get("required_count"),
        "mode": mode,
        "items": checked,
        "excluded": payload.get("excluded", []),
    }


def reports_shortfall(text: str) -> bool:
    patterns = (
        r"不足\s*\d*\s*条",
        r"缺\s*\d+\s*条",
        r"缺口\s*\d+",
        r"数量(?:硬)?不达标",
        r"无法交付\s*\d+\s*条",
        r"未完成\s*\d+\s*条",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def review_passes(output: str) -> bool:
    for line in output.splitlines():
        value = line.strip().upper()
        if not value:
            continue
        return value.startswith("PASS")
    return False


class TeamOrchestrator:
    def __init__(self, settings: Settings, store: TeamStore, adapters: AdapterRegistry):
        self.settings = settings
        self.store = store
        self.adapters = adapters
        self._workers: dict[str, threading.Thread] = {}
        self._cancelled: set[str] = set()
        self._lock = threading.Lock()

    @staticmethod
    def run_id() -> str:
        return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"

    def create(
        self,
        goal: str,
        workspace_name: str | None = None,
        mode_override: str | None = None,
    ) -> dict[str, Any]:
        goal = goal.strip()
        if not goal:
            raise ValueError("任务目标不能为空")
        if len(goal) > 12000:
            raise ValueError("任务目标过长")
        run_id = self.run_id()
        workspace = self.settings.create_workspace(run_id, workspace_name)
        spec = build_task_spec(goal, mode_override)
        plan = build_plan(goal)
        self.store.create_run(run_id, goal, workspace, plan, spec)
        self.store.add_event(
            run_id,
            "run.created",
            "小棒",
            {"goal": goal, "workspace": str(workspace), "plan": plan, "spec": spec},
        )
        worker = threading.Thread(
            target=self._execute_run,
            args=(run_id,),
            daemon=True,
            name=f"team-run-{run_id}",
        )
        with self._lock:
            self._workers[run_id] = worker
        worker.start()
        return self.state(run_id)

    def state(self, run_id: str, after_event: int = 0) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        return {
            "run": run,
            "tasks": self.store.list_tasks(run_id),
            "events": self.store.events(run_id, after_event),
            "artifacts": self.store.artifacts(run_id),
        }

    def latest(self) -> dict[str, Any] | None:
        run_id = self.store.latest_run_id()
        return self.state(run_id) if run_id else None

    def _effective_goal(self, run: dict[str, Any]) -> str:
        goal = run["goal"]
        decision = run.get("decision")
        try:
            payload = json.loads(run.get("decision_json") or "{}")
        except json.JSONDecodeError:
            payload = {}
        if decision == "accept_shortfall":
            return (
                goal
                + "\n\n老板已批准本次接受数量不足。"
                "复核时评价是否诚实列出缺口、来源、风险和不可发布项，"
                "不得要求继续补足数量。"
            )
        if decision == "expand_scope":
            days = int(payload.get("window_days", 3))
            return (
                goal
                + f"\n\n老板已批准把检索时间窗口扩大为最近 {days} 天（含今天）。"
                f"标题和交付中必须写明“近 {days} 天”，不得继续声称“今天”。"
                "事件发生日、首次披露日和报道日仍须逐条列明。"
            )
        return goal

    def decide(
        self,
        run_id: str,
        decision: str,
        *,
        window_days: int = 3,
    ) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        if run["status"] != "needs_decision":
            raise ValueError("当前运行不在待决策状态")
        if decision == "cancel":
            self.store.set_decision(run_id, decision, {})
            self.store.add_event(run_id, "run.decision", "老板", {"decision": decision})
            return self.cancel(run_id)
        if decision == "accept_shortfall":
            self.store.set_decision(run_id, decision, {})
            spec = dict(run.get("spec") or {})
            spec["accept_shortfall"] = True
            self.store.set_spec(run_id, spec)
            self.store.add_event(
                run_id,
                "run.decision",
                "老板",
                {"decision": decision, "label": "接受数量不足"},
            )
            self.store.update_run(run_id, status="running", error="")
            self._start_worker(run_id)
            return self.state(run_id)
        if decision == "expand_scope":
            if not 1 <= window_days <= 30:
                raise ValueError("时间窗口必须在 1 到 30 天之间")
            payload = {"window_days": window_days}
            self.store.set_decision(run_id, decision, payload)
            spec = dict(run.get("spec") or {})
            spec.update(
                {
                    "mode": "last_custom",
                    "mode_label": f"近{window_days}天",
                    "window_days": window_days,
                    "strict_event_date": False,
                    "accept_shortfall": False,
                }
            )
            self.store.set_spec(run_id, spec)
            for task in self.store.list_tasks(run_id):
                self.store.update_task(
                    task["id"],
                    status="waiting",
                    attempt=0,
                    result="",
                    evidence="",
                    error="老板批准扩大检索时间窗口",
                    accepted_by=None,
                      meta={},
                )
            self.store.update_run(run_id, status="running", error="")
            self.store.add_event(
                run_id,
                "run.decision",
                "老板",
                {
                    "decision": decision,
                    "label": f"扩大到最近 {window_days} 天",
                    "window_days": window_days,
                },
            )
            self._start_worker(run_id)
            return self.state(run_id)
        raise ValueError("未知决策，必须是 accept_shortfall、expand_scope 或 cancel")

    def accept(self, run_id: str, task_id: str, accepted_by: str = "老板") -> dict[str, Any]:
        task = self.store.get_task(task_id)
        if not task or task["run_id"] != run_id:
            raise KeyError(task_id)
        if task["status"] != "pending_review":
            raise ValueError("只有待验收任务可以验收")
        if not task["evidence"].strip():
            raise ValueError("没有证据，不能通过验收")
        if task["role"] == "review" and not review_passes(task["result"]):
            raise ValueError("复核结论不是 PASS，不能通过验收")
        self.store.update_task(
            task_id,
            status="accepted",
            accepted_by=accepted_by,
        )
        self.store.update_run(run_id, status="accepted")
        self.store.add_event(
            run_id,
            "task.accepted",
            accepted_by,
            {"title": task["title"], "evidence": task["evidence"]},
            task_id,
        )
        return self.state(run_id)

    def retry(self, run_id: str, task_id: str) -> dict[str, Any]:
        task = self.store.get_task(task_id)
        if not task or task["run_id"] != run_id:
            raise KeyError(task_id)
        if task["status"] not in ("failed", "blocked", "pending_review"):
            raise ValueError("当前任务状态不可重试")
        if task["role"] == "review":
            for upstream in self.store.list_tasks(run_id):
                if upstream["seq"] >= task["seq"]:
                    continue
                self.store.update_task(
                    upstream["id"],
                    status="waiting",
                    attempt=0,
                    result="",
                    evidence="",
                    error="老板要求重试，整条上游链需要重做",
                    accepted_by=None,
                      meta={},
                )
        self.store.update_task(
            task_id,
            status="waiting",
            error="",
            attempt=0,
            accepted_by=None,
        )
        self.store.update_run(run_id, status="running", error="")
        self.store.add_event(
            run_id, "task.retry_requested", "老板", {"title": task["title"]}, task_id
        )
        self._start_worker(run_id)
        return self.state(run_id)

    def cancel(self, run_id: str) -> dict[str, Any]:
        self._cancelled.add(run_id)
        self.store.update_run(run_id, status="cancelled")
        for task in self.store.list_tasks(run_id):
            if task["status"] in ("waiting", "running", "pending_review"):
                self.store.update_task(task["id"], status="cancelled")
        self.store.add_event(run_id, "run.cancelled", "老板")
        return self.state(run_id)

    def _start_worker(self, run_id: str) -> None:
        with self._lock:
            current = self._workers.get(run_id)
            if current and current.is_alive():
                return
            worker = threading.Thread(
                target=self._execute_run,
                args=(run_id,),
                daemon=True,
                name=f"team-run-{run_id}",
            )
            self._workers[run_id] = worker
        worker.start()

    def _next_ready(self, run_id: str) -> dict[str, Any] | None:
        tasks = self.store.list_tasks(run_id)
        by_title = {task["title"]: task for task in tasks}
        for task in tasks:
            if task["status"] != "waiting":
                continue
            dependencies = [by_title.get(title) for title in task["deps"]]
            if all(dep and dep["status"] == "accepted" for dep in dependencies):
                return task
        return None

    def _prior_outputs(self, run_id: str) -> str:
        chunks = []
        for task in self.store.list_tasks(run_id):
            if task["role"] != "review" and task["result"].strip():
                chunks.append(f"## {task['title']} / {task['agent_id']}\n{task['result']}")
        return "\n\n".join(chunks)[-30000:]

    def _review_feedback(self, run_id: str) -> str:
        feedback = []
        for task in self.store.list_tasks(run_id):
            if task["role"] == "review" and task["result"].strip():
                feedback.append(task["result"][-6000:])
        return "\n\n".join(feedback)

    def _prompt(self, task: dict[str, Any], goal: str, workspace: Path, prior: str) -> str:
        safe_prior = prior[-12000:]
        review_feedback = self._review_feedback(task["run_id"])[-3500:]
        run = self.store.get_run(task["run_id"])
        rules = goal_specific_rules(goal, run.get("spec") if run else None)
        if task["role"] == "research":
            context = workspace_context(workspace, 5000)
            return (
                "你是团队检索员。只返回可直接引用的事实与来源，不编造。\n"
                f"总目标：{goal}\n\n任务专用验收口径：\n{rules}\n\n"
                f"已有事实材料（如有）：\n{safe_prior or '(无)'}\n\n"
                f"上一轮复核反馈（只作改进清单，不是事实来源）：\n"
                f"{review_feedback or '(无)'}\n\n"
                f"工作区文本：\n{context}\n\n"
                "请联网重新检索并打开可访问来源，优先一手来源。"
                "逐条给出事件发生日、首次披露日、报道日和链接，不得用旧闻冒充今日新闻。\n\n"
                "最终回答只能包含一个 JSON 对象，禁止输出 JSON 之外的文字。格式：\n"
                '{"items":[{"title":"标题","event_date":"YYYY-MM-DD",'
                '"first_disclosed_at":"YYYY-MM-DD",'
                '"published_at":"YYYY-MM-DDTHH:MM:SS+08:00",'
                '"primary_url":"https://...","source_tier":"A|B|C",'
                '"classification":"news|comment|promotional|aggregate|other",'
                '"evidence_quote":"支持事实的页面原文"}],'
                '"excluded":[{"title":"排除项","reason":"原因"}],'
                '"summary":"缺口与说明"}'
            )
        if task["role"] in ("plan", "analyze"):
            context = workspace_context(workspace, 5000)
            team = team_context()
            if task["role"] == "plan":
                instruction = (
                    "你是团队规划员。只做分析和计划，不修改文件，"
                    "不调用文件或终端工具。直接输出目标、步骤、依赖、"
                    "文件边界、风险、验收标准。"
                )
            else:
                instruction = (
                    "你是团队分析员。只读分析，不修改文件，不调用文件或终端工具。"
                    "直接完成总目标，输出最终交付，不要只给后续计划。"
                    f"任务专用验收口径：{rules}"
                )
            return (
                f"{instruction}\n"
                f"总目标：{goal}\n工作目录：{workspace}\n\n"
                f"当前 AI 团队事实与制度：\n{team}\n\n"
                f"工作区文本摘要：\n{context}\n\n"
                f"已有材料：\n{safe_prior or '(无)'}\n\n"
                f"复核反馈（只作改进清单，不是事实来源，不得把其中的旧候选当成本轮材料）：\n"
                f"{review_feedback or '(无)'}\n\n"
                "只使用以上材料中可见的事实，不要虚构运行数据。"
            )
        if task["role"] == "implement":
            return (
                "你是工程实现者。只允许修改当前工作目录，禁止删除、安装、发布、"
                "上传、修改环境变量或访问密钥。\n"
                f"总目标：{goal}\n工作目录：{workspace}\n\n"
                f"规划与已有材料：\n{safe_prior}\n\n"
                f"复核反馈（只作修复要求，不是新事实来源）：\n"
                f"{review_feedback or '(无)'}\n\n"
                "完成最小必要修改；运行可用的测试；最终报告修改文件、测试结果、"
                "未完成项和风险。不要声称完成，等待独立复核。"
            )
        return (
            "你是独立验收员。不要修改文件，不要相信实现者自述。\n"
            f"总目标：{goal}\n工作目录：{workspace}\n\n"
            f"任务专用验收口径：\n{rules}\n\n"
            f"当前 AI 团队关键制度：\n{team_context(3500)}\n\n"
            f"全部上游结果：\n{safe_prior}\n\n"
            "只根据以上材料做只读审查，不要调用工具。"
            "第一行必须是 PASS 或 RETURN。"
            "之后用不超过 800 字列出检查项、证据、未解决风险和最终建议。"
        )

    def _save_artifact(
        self,
        run_id: str,
        task_id: str,
        kind: str,
        name: str,
        text: str,
    ) -> Path:
        directory = self.settings.artifacts_dir / run_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        path.write_text(redact(text), encoding="utf-8")
        data = path.read_bytes()
        self.store.add_artifact(
            run_id,
            task_id,
            kind,
            path,
            hashlib.sha256(data).hexdigest(),
            len(data),
        )
        return path

    def _execute_run(self, run_id: str) -> None:
        run = self.store.get_run(run_id)
        if not run:
            return
        workspace = Path(run["workspace"])
        goal = self._effective_goal(run)
        self.store.update_run(run_id, status="running")
        before = workspace_snapshot(workspace)
        try:
            while run_id not in self._cancelled:
                task = self._next_ready(run_id)
                if not task:
                    tasks = self.store.list_tasks(run_id)
                    if any(task["status"] in ("failed", "blocked") for task in tasks):
                        self.store.update_run(run_id, status="failed")
                    elif any(task["status"] == "pending_review" for task in tasks):
                        self.store.update_run(run_id, status="pending_review")
                    elif all(task["status"] == "accepted" for task in tasks):
                        self.store.update_run(run_id, status="accepted")
                    else:
                        self.store.update_run(
                            run_id, status="blocked", error="没有可执行的后续任务"
                        )
                    return

                while task["attempt"] < task["max_attempts"]:
                    attempt = task["attempt"] + 1
                    task["attempt"] = attempt
                    self.store.update_task(task["id"], status="running", attempt=attempt)
                    self.store.add_event(
                        run_id,
                        "task.started",
                        task["agent_id"],
                        {"title": task["title"], "attempt": attempt},
                        task["id"],
                    )
                    prior = self._prior_outputs(run_id)
                    prompt = self._prompt(task, goal, workspace, prior)
                    self.store.update_task(task["id"], prompt=prompt)
                    execution_token = secrets.token_hex(2)
                    artifact_path = (
                        self.settings.artifacts_dir
                        / run_id
                        / f"{task['id']}-attempt{attempt}-{execution_token}.md"
                    )
                    artifact_path.parent.mkdir(parents=True, exist_ok=True)
                    result: AgentResult = self.adapters.run(
                        task["agent_id"],
                        prompt,
                        workspace,
                        artifact_path,
                        web=task["role"] == "research",
                    )
                    task_meta = dict(task.get("meta") or {})
                    if run_id in self._cancelled:
                        self.store.update_task(task["id"], status="cancelled")
                        self.store.update_run(run_id, status="cancelled")
                        return
                    if result.status == "success":
                        if task["role"] == "research":
                            evidence_payload = extract_json_object(result.output)
                            link_report = audit_links(result.output)
                            validation = validate_news_payload(
                                evidence_payload,
                                (self.store.get_run(run_id) or {}).get("spec", {}),
                                link_report,
                            )
                            task_meta["evidence_validation"] = validation
                            task_meta["link_report"] = link_report
                            if not validation["structured"]:
                                result.status = "failed"
                                result.error = (
                                    "检索结果未按结构化协议交付："
                                    + validation.get("error", "JSON 无效")
                                )
                            else:
                                result.output = (
                                    result.output.rstrip()
                                    + "\n\n## 机器证据校验\n"
                                    + json.dumps(validation, ensure_ascii=False, indent=2)
                                    + ("\n\n" + link_report if link_report else "")
                                )
                    if result.status == "success":
                        output_path = self._save_artifact(
                            run_id,
                            task["id"],
                            f"{task['role']}_output",
                            artifact_path.name,
                            result.output,
                        )
                        if task["role"] in ("review", "research", "analyze"):
                            evidence = str(output_path)
                        else:
                            after = workspace_snapshot(workspace)
                            changes = changed_files(before, after)
                            diff_text = "\n".join(changes) or "(无文件变化)"
                            diff_path = self._save_artifact(
                                run_id,
                                task["id"],
                                "workspace_diff",
                                f"{task['id']}-attempt{attempt}-{execution_token}-diff.txt",
                                diff_text,
                            )
                            evidence = f"{output_path}; {diff_path}"
                        if task["role"] == "review" and not review_passes(result.output):
                            reason = result.output.strip()[:2000] or "复核退回"
                            if task["attempt"] < task["max_attempts"]:
                                self.store.update_task(
                                    task["id"],
                                    status="waiting",
                                    result=result.output[:30000],
                                    evidence=str(output_path),
                                    error=f"复核退回：{reason}",
                                )
                                for upstream in self.store.list_tasks(run_id):
                                    if upstream["seq"] >= task["seq"]:
                                        continue
                                    self.store.update_task(
                                        upstream["id"],
                                        status="waiting",
                                        attempt=0,
                                        result="",
                                        evidence="",
                                        error="独立复核退回，整条上游链需要重做",
                                        accepted_by=None,
                                        meta={},
                                    )
                                self.store.add_event(
                                    run_id,
                                    "review.returned",
                                    task["agent_id"],
                                    {
                                        "title": task["title"],
                                        "reason": reason,
                                        "evidence": str(output_path),
                                    },
                                    task["id"],
                                )
                                break
                            self.store.update_task(
                                task["id"],
                                status="failed",
                                result=result.output[:30000],
                                evidence=str(output_path),
                                error=f"复核多次退回：{reason}",
                            )
                            self.store.add_event(
                                run_id,
                                "review.failed",
                                task["agent_id"],
                                {"title": task["title"], "reason": reason},
                                task["id"],
                            )
                            self.store.update_run(
                                run_id, status="failed", error="复核多次退回"
                            )
                            return
                        status = (
                            "pending_review"
                            if task["role"] == "review"
                            else "accepted"
                        )
                        accepted_by = None if status == "pending_review" else "Orchestrator"
                        self.store.update_task(
                            task["id"],
                            status=status,
                            result=result.output[:30000],
                            evidence=evidence,
                            error="",
                            accepted_by=accepted_by,
                            meta=task_meta,
                        )
                        if task["role"] == "analyze":
                            tasks = self.store.list_tasks(run_id)
                            research_task = next(
                                (item for item in tasks if item["role"] == "research"),
                                None,
                            )
                            analyze_text = result.output
                            run_spec = (self.store.get_run(run_id) or {}).get("spec", {})
                            expected = run_spec.get("required_count") or requested_count(goal)
                            validation = (
                                (research_task or {}).get("meta", {}).get(
                                    "evidence_validation", {}
                                )
                            )
                            eligible = validation.get("eligible_count")
                            if (
                                expected
                                and eligible is not None
                                and int(eligible) < int(expected)
                                and reports_shortfall(analyze_text)
                            ):
                                reason = (
                                    f"机器证据校验仅认定 {eligible} 条，目标 {expected} 条；"
                                    "分析角色也确认数量不足。"
                                )
                                self.store.update_run(
                                    run_id,
                                    status="needs_decision",
                                    output=reason,
                                )
                                self.store.add_event(
                                    run_id,
                                    "run.needs_decision",
                                    "Orchestrator",
                                    {
                                        "reason": reason,
                                        "expected_count": expected,
                                        "eligible_count": eligible,
                                        "validation": validation,
                                        "options": [
                                            "accept_shortfall",
                                            "expand_scope",
                                            "cancel",
                                        ],
                                    },
                                    task["id"],
                                )
                                return
                        self.store.add_event(
                            run_id,
                            "task.completed",
                            task["agent_id"],
                            {
                                "title": task["title"],
                                "status": status,
                                "duration_seconds": result.duration_seconds,
                                "evidence": evidence,
                            },
                            task["id"],
                        )
                        break

                    self.store.update_task(
                        task["id"],
                        error=redact(result.error or result.output or "执行失败"),
                    )
                    self.store.add_event(
                        run_id,
                        "task.attempt_failed",
                        task["agent_id"],
                        {
                            "title": task["title"],
                            "attempt": attempt,
                            "error": redact(result.error or result.output)[-2000:],
                        },
                        task["id"],
                    )
                else:
                    self.store.update_task(task["id"], status="failed")
                    self.store.add_event(
                        run_id,
                        "task.failed",
                        task["agent_id"],
                        {"title": task["title"]},
                        task["id"],
                    )
                    self.store.update_run(run_id, status="failed", error="任务执行失败")
                    return
            if run_id in self._cancelled:
                self.store.update_run(run_id, status="cancelled")
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            self.store.update_run(run_id, status="failed", error=message)
            self.store.add_event(run_id, "run.exception", "Orchestrator", {"error": message})

