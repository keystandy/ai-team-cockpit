from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Settings
from .security import CredentialBroker, child_env, redact


AGENTS: dict[str, dict[str, Any]] = {
    "bang": {
        "name": "小棒",
        "role": "协调与终验",
        "engine": "WorkBuddy",
        "capabilities": ["任务拆解", "审批", "汇总", "联网"],
    },
    "shen": {
        "name": "小深",
        "role": "规划与推理",
        "engine": "DeepSeek Harness",
        "capabilities": ["方案拆解", "长链推理", "文件读写"],
    },
    "ku": {
        "name": "小酷",
        "role": "工程实现",
        "engine": "Codex CLI",
        "capabilities": ["代码修改", "命令执行", "测试", "批量文件"],
    },
    "ke": {
        "name": "小克",
        "role": "独立验收",
        "engine": "Claude Code",
        "capabilities": ["代码审查", "逻辑检查", "长文审阅", "对比"],
    },
    "dou": {
        "name": "小豆",
        "role": "检索与多模态",
        "engine": "豆包 · 火山方舟",
        "capabilities": ["联网检索", "中文表达", "图片分析", "长文阅读"],
    },
}


@dataclass
class AgentResult:
    agent_id: str
    status: str
    output: str
    duration_seconds: float
    exit_code: int | None
    error: str = ""


def _creation_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run_process(
    command: list[str],
    *,
    cwd: Path,
    settings: Settings,
    timeout: int,
    env_extra: dict[str, str] | None = None,
    stdout_path: Path | None = None,
) -> tuple[int | None, str, str, float]:
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=child_env(settings, env_extra),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_creation_flags(),
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        stdout, stderr = process.communicate()
    duration = round(time.monotonic() - started, 2)
    if stdout_path:
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text(redact(stdout or ""), encoding="utf-8")
    if timed_out:
        return None, redact(stdout or ""), f"任务超过 {timeout} 秒", duration
    return int(process.returncode), redact(stdout or ""), redact(stderr or ""), duration


class DSHAdapter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.credentials = CredentialBroker(settings)

    def run(self, prompt: str, workspace: Path, artifact_path: Path) -> AgentResult:
        if not self.settings.dsh_exe.exists():
            return AgentResult("shen", "failed", "", 0, None, "DSH 入口不存在")
        command = [
            str(self.settings.dsh_exe),
            str(self.settings.dsh_bin),
            "--profile",
            "headless",
            prompt,
        ]
        code, out, err, duration = run_process(
            command,
            cwd=workspace,
            settings=self.settings,
            timeout=self.settings.task_timeout_seconds,
            env_extra=self.credentials.deepseek_env(),
            stdout_path=artifact_path,
        )
        return AgentResult(
            "shen",
            "success" if code == 0 and out.strip() else "failed",
            out,
            duration,
            code,
            err,
        )


class CodexAdapter:
    def __init__(self, settings: Settings):
        self.settings = settings

    def run(self, prompt: str, workspace: Path, artifact_path: Path) -> AgentResult:
        exe = self.settings.codex_exe
        if not exe or not exe.exists():
            return AgentResult("ku", "failed", "", 0, None, "Codex CLI 不存在")
        command = [
            str(exe),
            "-a",
            "never",
            "exec",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "workspace-write",
            "-C",
            str(workspace),
            "-o",
            str(artifact_path),
            prompt,
        ]
        env = {
            "CODEX_HOME": str(self.settings.codex_home),
            "TEMP": str(self.settings.runtime_dir / "tmp"),
            "TMP": str(self.settings.runtime_dir / "tmp"),
        }
        code, out, err, duration = run_process(
            command,
            cwd=workspace,
            settings=self.settings,
            timeout=max(self.settings.task_timeout_seconds, 600),
            env_extra=env,
            stdout_path=artifact_path.with_suffix(".stdout.log"),
        )
        final = ""
        if artifact_path.exists():
            final = redact(artifact_path.read_text(encoding="utf-8", errors="replace"))
        elif out.strip():
            final = out
            artifact_path.write_text(final, encoding="utf-8")
        if code == 0 and not final.strip():
            err = (err + "\nCodex 没有返回最终消息").strip()
        return AgentResult(
            "ku",
            "success" if code == 0 and final.strip() else "failed",
            final,
            duration,
            code,
            err,
        )


class ClaudeAdapter:
    def __init__(self, settings: Settings):
        self.settings = settings

    def run(self, prompt: str, workspace: Path, artifact_path: Path) -> AgentResult:
        if not self.settings.claude_exe.exists():
            return AgentResult("ke", "failed", "", 0, None, "Claude Code 不存在")
        command = [
            str(self.settings.claude_exe),
            "-p",
            "--permission-mode",
            "plan",
            "--tools",
            "",
            "--output-format",
            "text",
            prompt,
        ]
        code, out, err, duration = run_process(
            command,
            cwd=workspace,
            settings=self.settings,
            timeout=self.settings.task_timeout_seconds,
            stdout_path=artifact_path,
        )
        return AgentResult(
            "ke",
            "success" if code == 0 and out.strip() else "failed",
            out,
            duration,
            code,
            err,
        )


class DoubaoAdapter:
    def __init__(self, settings: Settings):
        self.settings = settings

    def run(
        self,
        prompt: str,
        workspace: Path,
        artifact_path: Path,
        *,
        web: bool = False,
    ) -> AgentResult:
        if not self.settings.doubao_bridge.exists():
            return AgentResult("dou", "failed", "", 0, None, "豆包桥接脚本不存在")
        command = [
            self.settings.node_exe,
            str(self.settings.doubao_bridge),
            prompt,
            "--quiet",
            "--max",
            "2400",
        ]
        if web:
            command.append("--web")
        code, out, err, duration = run_process(
            command,
            cwd=self.settings.doubao_bridge.parent,
            settings=self.settings,
            timeout=max(self.settings.task_timeout_seconds, 300),
            stdout_path=artifact_path,
        )
        return AgentResult(
            "dou",
            "success" if code == 0 and out.strip() else "failed",
            out,
            duration,
            code,
            err,
        )


class BangReviewAdapter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.endpoint = settings.review_base_url.rstrip("/") + "/responses"
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @staticmethod
    def _extract_text(payload: dict[str, Any]) -> str:
        direct = payload.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        chunks = []
        for item in payload.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    chunks.append(str(content["text"]))
        return "\n".join(chunks).strip()

    def run(self, prompt: str, workspace: Path, artifact_path: Path) -> AgentResult:
        body = json.dumps(
            {
                "model": self.settings.review_model,
                "input": prompt,
                "max_output_tokens": 3500,
                "store": False,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        started = time.monotonic()
        last_error = ""
        for attempt in range(3):
            request = urllib.request.Request(
                self.endpoint,
                data=body,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "AI-Team-Bang-Review/1.0",
                },
            )
            try:
                with self.opener.open(
                    request, timeout=self.settings.task_timeout_seconds
                ) as response:
                    raw = response.read().decode("utf-8", errors="replace")
                parsed = json.loads(raw)
                output = self._extract_text(parsed)
                if not output:
                    raise ValueError("小棒审核没有返回文本")
                artifact_path.parent.mkdir(parents=True, exist_ok=True)
                artifact_path.write_text(redact(output), encoding="utf-8")
                duration = round(time.monotonic() - started, 2)
                return AgentResult("bang", "success", redact(output), duration, 0)
            except urllib.error.HTTPError as exc:
                last_error = f"HTTP {exc.code}: {exc.reason}"
                exc.close()
                if exc.code not in (429, 500, 502, 503, 504):
                    break
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            if attempt < 2:
                time.sleep(1 + attempt)
        duration = round(time.monotonic() - started, 2)
        return AgentResult("bang", "failed", "", duration, None, last_error)


class AdapterRegistry:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.adapters: dict[str, Any] = {
            "shen": DSHAdapter(settings),
            "ku": CodexAdapter(settings),
            "ke": ClaudeAdapter(settings),
            "dou": DoubaoAdapter(settings),
            "bang": BangReviewAdapter(settings),
        }

    def run(
        self,
        agent_id: str,
        prompt: str,
        workspace: Path,
        artifact_path: Path,
        *,
        web: bool = False,
    ) -> AgentResult:
        adapter = self.adapters.get(agent_id)
        if not adapter:
            return AgentResult(agent_id, "failed", "", 0, None, "未注册 Adapter")
        if agent_id == "dou":
            return adapter.run(
                prompt, workspace, artifact_path, web=web
            )
        return adapter.run(prompt, workspace, artifact_path)

    def quick_health(self) -> list[dict[str, Any]]:
        paths = {
            "shen": self.settings.dsh_exe,
            "ku": self.settings.codex_exe,
            "ke": self.settings.claude_exe,
            "dou": self.settings.doubao_bridge,
        }
        result = []
        for agent_id, data in AGENTS.items():
            if agent_id == "bang":
                online = True
                detail = "本地控制面在线"
            else:
                path = paths.get(agent_id)
                online = bool(path and Path(path).exists())
                detail = str(path) if path else "入口不存在"
            result.append(
                {
                    "id": agent_id,
                    **data,
                    "status": "online" if online else "offline",
                    "detail": detail,
                }
            )
        return result

