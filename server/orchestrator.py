from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
from datetime import datetime
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
                "title": "架构分析与结论",
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


def goal_specific_rules(goal: str) -> str:
    if re.search(r"新闻|资讯|最新|今天|今日", goal):
        count_match = re.search(r"(\d+)\s*条", goal)
        count = count_match.group(1) if count_match else "用户指定数量"
        today = datetime.now().astimezone().strftime("%Y-%m-%d")
        return (
            f"这是新闻检索任务，当前日期为 {today}。"
            f"必须交付 {count} 条符合用户时效要求的条目。"
            "每条必须列明事件发生日、首次披露日、报道日、可访问的一手来源链接、"
            "来源等级和新闻分类。评论、宣传稿、聚合短讯必须单列，不能凑入新闻条数。"
            "数量不足时明确说不足，不得用旧闻、评论或无关条目填充。"
            "全球首个、首例、最大、成本最低等最高级表述必须有独立证据。"
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
    ) -> dict[str, Any]:
        goal = goal.strip()
        if not goal:
            raise ValueError("任务目标不能为空")
        if len(goal) > 12000:
            raise ValueError("任务目标过长")
        run_id = self.run_id()
        workspace = self.settings.create_workspace(run_id, workspace_name)
        plan = build_plan(goal)
        self.store.create_run(run_id, goal, workspace, plan)
        self.store.add_event(
            run_id,
            "run.created",
            "小棒",
            {"goal": goal, "workspace": str(workspace), "plan": plan},
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
            if task["result"].strip():
                chunks.append(f"## {task['title']} / {task['agent_id']}\n{task['result']}")
        return "\n\n".join(chunks)[-30000:]

    def _prompt(self, task: dict[str, Any], goal: str, workspace: Path, prior: str) -> str:
        safe_prior = prior[-12000:]
        rules = goal_specific_rules(goal)
        if task["role"] == "research":
            context = workspace_context(workspace, 5000)
            return (
                "你是团队检索员。只返回可直接引用的事实与来源，不编造。\n"
                f"总目标：{goal}\n\n任务专用验收口径：\n{rules}\n\n"
                f"上一次退回意见与已有材料（如有）：\n{safe_prior or '(无)'}\n\n"
                f"工作区文本：\n{context}\n\n"
                "请联网重新检索并打开可访问来源，优先一手来源。"
                "逐条给出事件发生日、首次披露日、报道日和链接，不得用旧闻冒充今日新闻。"
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
                "只使用以上材料中可见的事实，不要虚构运行数据。"
            )
        if task["role"] == "implement":
            return (
                "你是工程实现者。只允许修改当前工作目录，禁止删除、安装、发布、"
                "上传、修改环境变量或访问密钥。\n"
                f"总目标：{goal}\n工作目录：{workspace}\n\n"
                f"规划与已有材料：\n{safe_prior}\n\n"
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
        goal = run["goal"]
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
                    artifact_path = (
                        self.settings.artifacts_dir
                        / run_id
                        / f"{task['id']}-attempt{attempt}.md"
                    )
                    artifact_path.parent.mkdir(parents=True, exist_ok=True)
                    result: AgentResult = self.adapters.run(
                        task["agent_id"],
                        prompt,
                        workspace,
                        artifact_path,
                        web=task["role"] == "research",
                    )
                    if run_id in self._cancelled:
                        self.store.update_task(task["id"], status="cancelled")
                        self.store.update_run(run_id, status="cancelled")
                        return
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
                                f"{task['id']}-attempt{attempt}-diff.txt",
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
                        )
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

