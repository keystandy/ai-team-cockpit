from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .adapters import AdapterRegistry
from .config import Settings
from .orchestrator import TeamOrchestrator
from .store import TeamStore


def json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


class TeamRequestHandler(BaseHTTPRequestHandler):
    settings: Settings
    store: TeamStore
    orchestrator: TeamOrchestrator
    adapters: AdapterRegistry

    def log_message(self, format: str, *args) -> None:
        return

    def _send_json(self, value: object, status: int = 200) -> None:
        data = json_bytes(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status: int, message: str) -> None:
        self._send_json({"ok": False, "error": message}, status)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1024 * 1024:
            raise ValueError("请求体过大")
        raw = self.rfile.read(length) if length else b"{}"
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return value

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        try:
            if path == "/api/health":
                self._send_json(
                    {
                        "ok": True,
                        "db": "ok",
                        "agents": self.adapters.quick_health(),
                    }
                )
                return
            if path == "/api/agents":
                self._send_json({"ok": True, "agents": self.adapters.quick_health()})
                return
            if path == "/api/runs":
                self._send_json({"ok": True, "runs": self.store.list_runs()})
                return
            if path == "/api/runs/latest":
                latest = self.orchestrator.latest()
                self._send_json({"ok": True, "data": latest})
                return
            prefix = "/api/runs/"
            if path.startswith(prefix):
                rest = path[len(prefix) :].strip("/")
                parts = rest.split("/")
                run_id = parts[0]
                after = int(query.get("after", ["0"])[0])
                if len(parts) == 1:
                    self._send_json({"ok": True, "data": self.orchestrator.state(run_id, after)})
                    return
            if path.startswith("/api/artifacts/"):
                run_id = path[len("/api/artifacts/") :].strip("/")
                self._send_json({"ok": True, "artifacts": self.store.artifacts(run_id)})
                return
            self._serve_static(path)
        except KeyError:
            self._error(404, "对象不存在")
        except Exception as exc:
            self._error(400, f"{type(exc).__name__}: {exc}")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            body = self._body()
            if path == "/api/tasks":
                goal = str(body.get("goal", ""))
                workspace = body.get("workspace")
                data = self.orchestrator.create(
                    goal, str(workspace).strip() if workspace else None
                )
                self._send_json({"ok": True, "data": data}, 201)
                return
            parts = [part for part in path.split("/") if part]
            # /api/tasks/{run_id}/{task_id}/{action}
            if len(parts) == 5 and parts[0:2] == ["api", "tasks"]:
                run_id, task_id, action = parts[2], parts[3], parts[4]
                if action == "accept":
                    data = self.orchestrator.accept(
                        run_id, task_id, str(body.get("accepted_by", "老板"))
                    )
                elif action == "retry":
                    data = self.orchestrator.retry(run_id, task_id)
                else:
                    self._error(404, "未知任务操作")
                    return
                self._send_json({"ok": True, "data": data})
                return
            # /api/runs/{run_id}/cancel
            if len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "cancel":
                self._send_json(
                    {"ok": True, "data": self.orchestrator.cancel(parts[2])}
                )
                return
            self._error(404, "接口不存在")
        except KeyError:
            self._error(404, "对象不存在")
        except Exception as exc:
            self._error(400, f"{type(exc).__name__}: {exc}")

    def _serve_static(self, path: str) -> None:
        relative = "index.html" if path in ("", "/") else path.lstrip("/")
        denied = ("server/", "runtime/", "workspaces/", "data/live-team.sqlite")
        if relative.startswith(denied):
            self._error(403, "路径不允许")
            return
        target = (self.settings.cockpit_root / relative).resolve()
        try:
            target.relative_to(self.settings.cockpit_root.resolve())
        except ValueError:
            self._error(403, "路径不允许")
            return
        if not target.exists() or not target.is_file():
            self._error(404, "文件不存在")
            return
        data = target.read_bytes()
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in (
            "application/javascript",
            "application/json",
        ):
            content_type += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)


def build_server(settings: Settings) -> ThreadingHTTPServer:
    settings.ensure_directories()
    store = TeamStore(settings.db_path)
    store.recover_interrupted()
    adapters = AdapterRegistry(settings)
    orchestrator = TeamOrchestrator(settings, store, adapters)
    handler = type(
        "BoundTeamRequestHandler",
        (TeamRequestHandler,),
        {
            "settings": settings,
            "store": store,
            "adapters": adapters,
            "orchestrator": orchestrator,
        },
    )
    return ThreadingHTTPServer((settings.host, settings.port), handler)

