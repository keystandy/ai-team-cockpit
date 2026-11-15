from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


COCKPIT_ROOT = Path(__file__).resolve().parent.parent
AI_TEAM_ROOT = COCKPIT_ROOT.parent
CONFIG_PATH = COCKPIT_ROOT / "live.config.json"
EXAMPLE_CONFIG_PATH = COCKPIT_ROOT / "live.config.example.json"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def find_codex() -> Path | None:
    configured = Path(
        r"D:\WindowsApps\OpenAI.Codex_26.1111.2228.0_x64__2p2nqsd0c76g0\app\resources\codex.exe"
    )
    if configured.exists():
        return configured
    command = shutil.which("codex")
    if command:
        return Path(command)
    roots = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI" / "Codex" / "bin",
        Path(r"D:\WindowsApps"),
    ]
    patterns = ("codex.exe", "*/app/resources/codex.exe", "*/*/app/resources/codex.exe")
    for root in roots:
        if not str(root) or not root.exists():
            continue
        for pattern in patterns:
            match = next(root.glob(pattern), None)
            if match and match.is_file():
                return match
    return None


@dataclass(frozen=True)
class Settings:
    cockpit_root: Path
    team_root: Path
    data_dir: Path
    runtime_dir: Path
    workspace_root: Path
    db_path: Path
    artifacts_dir: Path
    dsh_exe: Path
    dsh_bin: Path
    dsh_home: Path
    dsh_credentials: Path
    codex_exe: Path | None
    codex_home: Path
    claude_exe: Path
    doubao_bridge: Path
    node_exe: str
    host: str
    port: int
    task_timeout_seconds: int
    max_attempts: int

    @classmethod
    def load(cls) -> "Settings":
        config: dict[str, Any] = {}
        for candidate in (CONFIG_PATH, EXAMPLE_CONFIG_PATH):
            if candidate.exists():
                config = load_json(candidate)
                break

        def configured_path(key: str, default: str) -> Path:
            return Path(str(config.get(key, default))).expanduser().resolve()

        dsh_exe = configured_path("dshExe", r"D:\Program Files\DSH NEXT\DSH NEXT.exe")
        dsh_bin = configured_path(
            "dshBin",
            str(
                dsh_exe.parent
                / "resources"
                / "app.asar"
                / "node_modules"
                / "@deepseek-ai"
                / "dsh"
                / "lib"
                / "bin.js"
            ),
        )
        fallback_codex = find_codex()
        codex = configured_path("codexExe", str(fallback_codex or ""))
        codex_exe = codex if codex.is_file() else fallback_codex
        data_dir = COCKPIT_ROOT / "data"
        runtime_dir = COCKPIT_ROOT / "runtime"
        workspace_root = COCKPIT_ROOT / "workspaces"
        return cls(
            cockpit_root=COCKPIT_ROOT,
            team_root=AI_TEAM_ROOT,
            data_dir=data_dir,
            runtime_dir=runtime_dir,
            workspace_root=workspace_root,
            db_path=data_dir / "live-team.sqlite3",
            artifacts_dir=runtime_dir / "artifacts",
            dsh_exe=dsh_exe,
            dsh_bin=dsh_bin,
            dsh_home=configured_path("dshHome", r"E:\DSHDockData\dsh-home"),
            dsh_credentials=configured_path(
                "dshCredentials", r"E:\DSHDockData\dsh-home\.credentials.yaml"
            ),
            codex_exe=codex_exe,
            codex_home=configured_path(
                "codexHome",
                str(AI_TEAM_ROOT.parent / "codex-bridge" / "codex-home"),
            ),
            claude_exe=configured_path(
                "claudeExe", r"D:\Programs\claude-code\claude.exe"
            ),
            doubao_bridge=configured_path(
                "doubaoBridge",
                str(AI_TEAM_ROOT / "doubao-bridge" / "doubao.mjs"),
            ),
            node_exe=str(config.get("nodeExe", "node")),
            host=str(config.get("host", "127.0.0.1")),
            port=int(config.get("port", 8765)),
            task_timeout_seconds=int(config.get("taskTimeoutSeconds", 300)),
            max_attempts=max(1, int(config.get("maxAttempts", 2))),
        )

    def ensure_directories(self) -> None:
        for path in (
            self.data_dir,
            self.runtime_dir,
            self.artifacts_dir,
            self.workspace_root,
            self.codex_home,
            self.runtime_dir / "tmp",
        ):
            path.mkdir(parents=True, exist_ok=True)

    def create_workspace(self, run_id: str, requested: str | None = None) -> Path:
        if requested:
            relative = Path(requested)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("workspace 必须是 workspaces 下的相对路径")
            target = (self.workspace_root / relative).resolve()
        else:
            target = (self.workspace_root / run_id).resolve()
        try:
            target.relative_to(self.workspace_root.resolve())
        except ValueError as exc:
            raise ValueError("workspace 越出允许目录") from exc
        target.mkdir(parents=True, exist_ok=True)
        readme = target / "README.md"
        if not readme.exists():
            readme.write_text(
                "# AI Team Workspace\n\n此目录由 AI 团队真实任务创建。\n",
                encoding="utf-8",
            )
        return target

