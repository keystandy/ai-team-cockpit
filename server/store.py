from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    workspace TEXT NOT NULL,
    status TEXT NOT NULL,
    output TEXT NOT NULL DEFAULT '',
    error TEXT,
    spec_json TEXT NOT NULL DEFAULT '{}',
    decision TEXT,
    decision_json TEXT,
    decision_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    role TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    deps_json TEXT NOT NULL,
    acceptance TEXT NOT NULL,
    prompt TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT '',
    meta_json TEXT NOT NULL DEFAULT '{}',
    evidence TEXT NOT NULL DEFAULT '',
    error TEXT,
    attempt INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 2,
    accepted_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    accepted_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    task_id TEXT,
    type TEXT NOT NULL,
    actor TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    task_id TEXT,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_run ON tasks(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, id);
"""


class TeamStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(SCHEMA)
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(runs)").fetchall()
            }
            for column, definition in (
                ("spec_json", "TEXT NOT NULL DEFAULT '{}'"),
                ("decision", "TEXT"),
                ("decision_json", "TEXT"),
                ("decision_at", "TEXT"),
            ):
                if column not in columns:
                    connection.execute(
                        f"ALTER TABLE runs ADD COLUMN {column} {definition}"
                    )
            task_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(tasks)").fetchall()
            }
            if "meta_json" not in task_columns:
                connection.execute(
                    "ALTER TABLE tasks ADD COLUMN meta_json TEXT NOT NULL DEFAULT '{}'"
                )

    def create_run(
        self,
        run_id: str,
        goal: str,
        workspace: Path,
        tasks: list[dict],
        spec: dict[str, Any] | None = None,
    ) -> None:
        stamp = now_iso()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO runs(
                    id, goal, workspace, spec_json, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'waiting', ?, ?)
                """,
                (
                    run_id,
                    goal,
                    str(workspace),
                    json.dumps(spec or {}, ensure_ascii=False),
                    stamp,
                    stamp,
                ),
            )
            for seq, task in enumerate(tasks, 1):
                connection.execute(
                    """
                    INSERT INTO tasks(
                        id, run_id, seq, role, agent_id, title, status, deps_json,
                        acceptance, max_attempts, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'waiting', ?, ?, ?, ?, ?)
                    """,
                    (
                        f"{run_id}-T{seq}",
                        run_id,
                        seq,
                        task["role"],
                        task["agent_id"],
                        task["title"],
                        json.dumps(task.get("deps", []), ensure_ascii=False),
                        task["acceptance"],
                        task.get("max_attempts", 2),
                        stamp,
                        stamp,
                    ),
                )

    def latest_run_id(self) -> str | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT id FROM runs ORDER BY created_at DESC, rowid DESC LIMIT 1"
            ).fetchone()
        return str(row["id"]) if row else None

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        run = dict(row)
        run["spec"] = json.loads(run.pop("spec_json") or "{}")
        return run

    def list_runs(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM runs ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        result = []
        for row in rows:
            run = dict(row)
            run["spec"] = json.loads(run.pop("spec_json") or "{}")
            result.append(run)
        return result

    def update_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        output: str | None = None,
        error: str | None = None,
    ) -> None:
        run = self.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE runs SET status = ?, output = ?, error = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    status if status is not None else run["status"],
                    output if output is not None else run["output"],
                    error if error is not None else run["error"],
                    now_iso(),
                    run_id,
                ),
            )

    def set_decision(self, run_id: str, decision: str, payload: dict[str, Any]) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE runs SET decision = ?, decision_json = ?, decision_at = ?,
                    updated_at = ? WHERE id = ?
                """,
                (
                    decision,
                    json.dumps(payload, ensure_ascii=False),
                    now_iso(),
                    now_iso(),
                    run_id,
                ),
            )

    def set_spec(self, run_id: str, spec: dict[str, Any]) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE runs SET spec_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(spec, ensure_ascii=False), now_iso(), run_id),
            )

    def list_tasks(self, run_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM tasks WHERE run_id = ? ORDER BY seq", (run_id,)
            ).fetchall()
        result = []
        for row in rows:
            task = dict(row)
            task["deps"] = json.loads(task.pop("deps_json"))
            task["meta"] = json.loads(task.pop("meta_json") or "{}")
            result.append(task)
        return result

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return None
        task = dict(row)
        task["deps"] = json.loads(task.pop("deps_json"))
        task["meta"] = json.loads(task.pop("meta_json") or "{}")
        return task

    def update_task(
        self,
        task_id: str,
        *,
        status: str | None = None,
        prompt: str | None = None,
        result: str | None = None,
        evidence: str | None = None,
        error: str | None = None,
        attempt: int | None = None,
        accepted_by: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        task = self.get_task(task_id)
        if not task:
            raise KeyError(task_id)
        stamp = now_iso()
        started_at = task["started_at"] or (stamp if status == "running" else None)
        finished_at = task["finished_at"]
        accepted_at = task["accepted_at"]
        if status in ("pending_review", "failed", "blocked", "cancelled"):
            finished_at = stamp
        if status in ("waiting", "running"):
            finished_at = None
        if status in ("waiting", "running", "failed", "blocked", "cancelled"):
            accepted_at = None
        if status == "accepted":
            accepted_at = stamp
        next_meta = meta if meta is not None else task["meta"]
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE tasks SET
                    status = ?, prompt = ?, result = ?, evidence = ?, error = ?,
                    attempt = ?, accepted_by = ?, updated_at = ?,
                    started_at = ?, finished_at = ?, accepted_at = ?, meta_json = ?
                WHERE id = ?
                """,
                (
                    status if status is not None else task["status"],
                    prompt if prompt is not None else task["prompt"],
                    result if result is not None else task["result"],
                    evidence if evidence is not None else task["evidence"],
                    error if error is not None else task["error"],
                    attempt if attempt is not None else task["attempt"],
                    accepted_by if accepted_by is not None else task["accepted_by"],
                    stamp,
                    started_at,
                    finished_at,
                    accepted_at,
                    json.dumps(next_meta, ensure_ascii=False),
                    task_id,
                ),
            )

    def add_event(
        self,
        run_id: str,
        event_type: str,
        actor: str,
        payload: dict[str, Any] | None = None,
        task_id: str | None = None,
    ) -> int:
        stamp = now_iso()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO events(run_id, task_id, type, actor, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    task_id,
                    event_type,
                    actor,
                    json.dumps(payload or {}, ensure_ascii=False),
                    stamp,
                ),
            )
            return int(cursor.lastrowid)

    def events(self, run_id: str, after: int = 0) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE run_id = ? AND id > ? ORDER BY id",
                (run_id, after),
            ).fetchall()
        result = []
        for row in rows:
            event = dict(row)
            event["payload"] = json.loads(event.pop("payload_json"))
            result.append(event)
        return result

    def add_artifact(
        self,
        run_id: str,
        task_id: str | None,
        kind: str,
        path: Path,
        sha256: str,
        size: int,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO artifacts(run_id, task_id, kind, path, sha256, size, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, task_id, kind, str(path), sha256, size, now_iso()),
            )

    def artifacts(self, run_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM artifacts WHERE run_id = ? ORDER BY id", (run_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def integrity_check(self) -> str:
        with self._connection() as connection:
            row = connection.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "unknown"

    def metrics(self) -> dict[str, Any]:
        runs = self.list_runs(limit=1000)
        run_counts: dict[str, int] = {}
        agent_counts: dict[str, dict[str, float]] = {}
        for run in runs:
            run_counts[run["status"]] = run_counts.get(run["status"], 0) + 1
            for task in self.list_tasks(run["id"]):
                stats = agent_counts.setdefault(
                    task["agent_id"],
                    {"total": 0, "accepted": 0, "failed": 0, "duration_seconds": 0.0},
                )
                stats["total"] += 1
                if task["status"] == "accepted":
                    stats["accepted"] += 1
                if task["status"] in ("failed", "blocked", "cancelled"):
                    stats["failed"] += 1
                if task["started_at"] and task["finished_at"]:
                    try:
                        started = datetime.fromisoformat(task["started_at"])
                        finished = datetime.fromisoformat(task["finished_at"])
                        stats["duration_seconds"] += max(
                            0.0, (finished - started).total_seconds()
                        )
                    except ValueError:
                        pass
        for stats in agent_counts.values():
            stats["success_rate"] = (
                round(stats["accepted"] / stats["total"], 3)
                if stats["total"]
                else 0
            )
            stats["avg_duration_seconds"] = (
                round(stats["duration_seconds"] / stats["total"], 2)
                if stats["total"]
                else 0
            )
        return {
            "runs": len(runs),
            "run_status": run_counts,
            "agents": agent_counts,
        }

    def recover_interrupted(self) -> None:
        stamp = now_iso()
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE tasks SET status = 'blocked', error = '服务重启，任务中断',
                    updated_at = ?
                WHERE status = 'running'
                """,
                (stamp,),
            )
            connection.execute(
                """
                UPDATE runs SET status = 'blocked',
                    error = '服务重启，任务中断，可手动重试',
                    updated_at = ?
                WHERE status IN ('running', 'waiting')
                """,
                (stamp,),
            )

