from __future__ import annotations

import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

from server.adapters import AgentResult
from server.config import COCKPIT_ROOT, Settings
from server.orchestrator import TeamOrchestrator, build_plan, review_passes
from server.store import TeamStore


class FakeAdapters:
    def run(self, agent_id, prompt, workspace, artifact_path, web=False):
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        output = "PASS\n证据：测试产物" if agent_id == "ke" else f"{agent_id} completed"
        artifact_path.write_text(output + "\n", encoding="utf-8")
        return AgentResult(
            agent_id=agent_id,
            status="success",
            output=output,
            duration_seconds=0.01,
            exit_code=0,
        )


class ReturnOnceAdapters:
    def __init__(self):
        self.review_calls = 0

    def run(self, agent_id, prompt, workspace, artifact_path, web=False):
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        if agent_id == "ke":
            self.review_calls += 1
            output = "RETURN\n证据不足" if self.review_calls == 1 else "PASS\n证据完成"
        else:
            output = f"{agent_id} analysis"
        artifact_path.write_text(output + "\n", encoding="utf-8")
        return AgentResult(
            agent_id=agent_id,
            status="success",
            output=output,
            duration_seconds=0.01,
            exit_code=0,
        )


class ControlPlaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=COCKPIT_ROOT)
        root = Path(self.temp.name)
        base = Settings.load()
        self.settings = replace(
            base,
            data_dir=root / "data",
            runtime_dir=root / "runtime",
            workspace_root=root / "workspaces",
            db_path=root / "data" / "team.sqlite3",
            artifacts_dir=root / "runtime" / "artifacts",
        )
        self.settings.ensure_directories()
        self.store = TeamStore(self.settings.db_path)
        self.orchestrator = TeamOrchestrator(
            self.settings, self.store, FakeAdapters()
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_plan_adds_research_and_implementation_only_when_needed(self) -> None:
        self.assertEqual(
            [task["role"] for task in build_plan("总结团队架构")],
            ["analyze", "review"],
        )
        self.assertEqual(
            [task["role"] for task in build_plan("总结架构并指出一个改进点")],
            ["analyze", "review"],
        )
        self.assertEqual(
            [task["role"] for task in build_plan("联网查最新资料并给出方案")],
            ["research", "analyze", "review"],
        )
        self.assertEqual(
            [task["role"] for task in build_plan("修复代码并运行测试")],
            ["plan", "implement", "review"],
        )

    def test_workspace_rejects_parent_path(self) -> None:
        with self.assertRaises(ValueError):
            self.settings.create_workspace("run", "../outside")

    def test_review_verdict_requires_explicit_pass(self) -> None:
        self.assertTrue(review_passes("PASS\n证据：report.md"))
        self.assertFalse(review_passes("RETURN\n证据不足"))
        self.assertFalse(review_passes("看起来可以"))

    def test_real_state_machine_reaches_human_acceptance(self) -> None:
        data = self.orchestrator.create("总结当前团队架构", None)
        run_id = data["run"]["id"]
        deadline = time.time() + 5
        while time.time() < deadline:
            state = self.orchestrator.state(run_id)
            pending = [
                task for task in state["tasks"] if task["status"] == "pending_review"
            ]
            if pending:
                result = self.orchestrator.accept(run_id, pending[-1]["id"], "测试老板")
                self.assertEqual(result["run"]["status"], "accepted")
                self.assertTrue(
                    all(task["status"] == "accepted" for task in result["tasks"])
                )
                return
            time.sleep(0.02)
        self.fail("任务未到达待验收状态")

    def test_review_return_reopens_upstream_and_requires_retry(self) -> None:
        adapters = ReturnOnceAdapters()
        orchestrator = TeamOrchestrator(self.settings, self.store, adapters)
        data = orchestrator.create("分析团队架构", None)
        run_id = data["run"]["id"]
        deadline = time.time() + 5
        while time.time() < deadline:
            state = orchestrator.state(run_id)
            if state["run"]["status"] == "pending_review":
                self.assertEqual(adapters.review_calls, 2)
                self.assertIn("review.returned", [
                    event["type"] for event in state["events"]
                ])
                return
            time.sleep(0.02)
        self.fail("复核退回后没有完成上游重试")

    def test_review_return_reruns_research_chain(self) -> None:
        class NewsAdapters:
            def __init__(self):
                self.calls = {"dou": 0, "shen": 0, "ke": 0}

            def run(self, agent_id, prompt, workspace, artifact_path, web=False):
                self.calls[agent_id] += 1
                artifact_path.parent.mkdir(parents=True, exist_ok=True)
                if agent_id == "ke":
                    output = (
                        "RETURN\n补检索一手来源"
                        if self.calls[agent_id] == 1
                        else "PASS\n来源已补齐"
                    )
                else:
                    output = f"{agent_id} output"
                artifact_path.write_text(output + "\n", encoding="utf-8")
                return AgentResult(agent_id, "success", output, 0.01, 0)

        adapters = NewsAdapters()
        orchestrator = TeamOrchestrator(self.settings, self.store, adapters)
        data = orchestrator.create("查今天的 AI 新闻 1 条", None)
        run_id = data["run"]["id"]
        deadline = time.time() + 5
        while time.time() < deadline:
            state = orchestrator.state(run_id)
            if state["run"]["status"] == "pending_review":
                self.assertEqual(adapters.calls, {"dou": 2, "shen": 2, "ke": 2})
                return
            time.sleep(0.02)
        self.fail("新闻复核退回后没有重跑完整检索链")


if __name__ == "__main__":
    unittest.main()
