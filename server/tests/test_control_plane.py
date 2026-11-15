from __future__ import annotations

import json
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

from server.adapters import AgentResult
from server.config import COCKPIT_ROOT, Settings
from server.orchestrator import (
    TeamOrchestrator,
    build_plan,
    build_task_spec,
    extract_urls,
    review_passes,
    validate_news_payload,
)
from server.store import TeamStore


class FakeAdapters:
    def run(self, agent_id, prompt, workspace, artifact_path, web=False):
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        output = (
            "PASS\n证据：测试产物"
            if agent_id in ("ke", "bang")
            else f"{agent_id} completed"
        )
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
        if agent_id == "bang":
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


class ShortfallAdapters:
    def __init__(self):
        self.calls = {"dou": 0, "shen": 0, "bang": 0}

    def run(self, agent_id, prompt, workspace, artifact_path, web=False):
        self.calls[agent_id] += 1
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        if agent_id == "bang":
            output = "PASS\n老板已批准不足交付"
        elif agent_id == "dou":
            output = json.dumps(
                {
                    "items": [
                        {
                            "title": "排除项",
                            "event_date": "2026-01-01",
                            "first_disclosed_at": "2026-01-01",
                            "published_at": "2026-01-01",
                            "primary_url": "",
                            "source_tier": "C",
                            "classification": "comment",
                            "evidence_quote": "测试引用",
                        }
                    ],
                    "excluded": [],
                    "summary": "严格筛选后不足5条",
                },
                ensure_ascii=False,
            )
        else:
            output = "严格筛选后只有1条，目标5条，不足5条，缺口4条"
        artifact_path.write_text(output + "\n", encoding="utf-8")
        return AgentResult(agent_id, "success", output, 0.01, 0)


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
        self.assertEqual(
            [task["role"] for task in build_plan("整理新闻格式，不新增事实")],
            ["analyze", "review"],
        )
        self.assertEqual(
            [
                task["role"]
                for task in build_plan(
                    "仅整理格式。草稿1：某模型部署到搜索并改写内核代码。"
                )
            ],
            ["analyze", "review"],
        )

    def test_task_spec_distinguishes_news_modes(self) -> None:
        self.assertEqual(
            build_task_spec("查今天的AI新闻5条")["mode"], "today_published"
        )
        self.assertEqual(
            build_task_spec("查今天发生的AI新闻5条")["mode"], "today_event"
        )
        self.assertEqual(
            build_task_spec("查近24小时AI新闻5条")["window_days"], 1
        )
        natural = build_task_spec("收集最近1星期内3个重大AI行业新闻")
        self.assertEqual(natural["mode"], "last_custom")
        self.assertEqual(natural["window_days"], 7)
        self.assertEqual(natural["required_count"], 3)
        self.assertEqual(
            build_task_spec("查最近两周的三则 AI 新闻")["required_count"], 3
        )

    def test_news_task_without_count_is_rejected_before_execution(self) -> None:
        with self.assertRaisesRegex(ValueError, "必须明确需要多少条"):
            self.orchestrator.create("查今天的 AI 行业新闻", None)

    def test_structured_evidence_validation_counts_only_news(self) -> None:
        spec = {
            "mode": "today_published",
            "required_count": 1,
            "window_days": 0,
        }
        today = time.strftime("%Y-%m-%d")
        payload = {
            "items": [
                {
                    "title": "合格新闻",
                    "event_date": today,
                    "first_disclosed_at": today,
                    "published_at": today,
                    "primary_url": "https://example.com/news",
                    "source_tier": "A",
                    "classification": "news",
                    "evidence_quote": "官方公告原文",
                },
                {
                    "title": "评论",
                    "event_date": today,
                    "first_disclosed_at": today,
                    "published_at": today,
                    "primary_url": "https://example.com/comment",
                    "source_tier": "B",
                    "classification": "comment",
                    "evidence_quote": "评论内容",
                },
            ]
        }
        validation = validate_news_payload(payload, spec, "")
        self.assertEqual(validation["eligible_count"], 1)

    def test_last_24h_requires_timezone_timestamp(self) -> None:
        today = time.strftime("%Y-%m-%d")
        payload = {
            "items": [
                {
                    "title": "日期但无时间",
                    "event_date": today,
                    "first_disclosed_at": today,
                    "published_at": today,
                    "primary_url": "https://example.com/news",
                    "source_tier": "A",
                    "classification": "news",
                    "evidence_quote": "官方公告原文",
                }
            ]
        }
        validation = validate_news_payload(
            payload,
            {"mode": "last_24h", "required_count": 1, "window_days": 1},
            "",
        )
        self.assertEqual(validation["eligible_count"], 0)

    def test_workspace_rejects_parent_path(self) -> None:
        with self.assertRaises(ValueError):
            self.settings.create_workspace("run", "../outside")

    def test_review_verdict_requires_explicit_pass(self) -> None:
        self.assertTrue(review_passes("PASS\n证据：report.md"))
        self.assertFalse(review_passes("RETURN\n证据不足"))
        self.assertFalse(review_passes("看起来可以"))

    def test_extract_urls_deduplicates_and_strips_punctuation(self) -> None:
        text = "来源 https://a.example/x。另见 https://a.example/x，以及 https://b.example/y)"
        self.assertEqual(
            extract_urls(text),
            ["https://a.example/x", "https://b.example/y"],
        )

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
                time.sleep(0.15)
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
                time.sleep(0.15)
                return
            time.sleep(0.02)
        self.fail("复核退回后没有完成上游重试")

    def test_review_return_reruns_research_chain(self) -> None:
        class NewsAdapters:
            def __init__(self):
                self.calls = {"dou": 0, "shen": 0, "bang": 0}

            def run(self, agent_id, prompt, workspace, artifact_path, web=False):
                self.calls[agent_id] += 1
                artifact_path.parent.mkdir(parents=True, exist_ok=True)
                if agent_id == "bang":
                    output = (
                        "RETURN\n补检索一手来源"
                        if self.calls[agent_id] == 1
                        else "PASS\n来源已补齐"
                    )
                elif agent_id == "dou":
                    output = json.dumps(
                        {
                            "items": [
                                {
                                    "title": "测试新闻",
                                    "event_date": "2026-01-01",
                                    "first_disclosed_at": "2026-01-01",
                                    "published_at": "2026-01-01",
                                    "primary_url": "",
                                    "source_tier": "C",
                                    "classification": "comment",
                                    "evidence_quote": "测试引用",
                                }
                            ],
                            "excluded": [],
                            "summary": "没有合格条目",
                        },
                        ensure_ascii=False,
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
                self.assertEqual(adapters.calls, {"dou": 2, "shen": 2, "bang": 2})
                time.sleep(0.15)
                return
            time.sleep(0.02)
        self.fail("新闻复核退回后没有重跑完整检索链")

    def test_shortfall_stops_for_decision_and_accepts_partial(self) -> None:
        adapters = ShortfallAdapters()
        orchestrator = TeamOrchestrator(self.settings, self.store, adapters)
        data = orchestrator.create("查今天的 AI 新闻5条", None)
        run_id = data["run"]["id"]
        deadline = time.time() + 5
        while time.time() < deadline:
            run = orchestrator.state(run_id)["run"]
            if run["status"] == "needs_decision":
                self.assertEqual(adapters.calls, {"dou": 1, "shen": 1, "bang": 0})
                orchestrator.decide(run_id, "accept_shortfall")
                break
            time.sleep(0.02)
        else:
            self.fail("数量不足后没有进入待决策状态")
        deadline = time.time() + 5
        while time.time() < deadline:
            state = orchestrator.state(run_id)
            if state["run"]["status"] == "pending_review":
                self.assertEqual(adapters.calls["bang"], 1)
                self.assertEqual(state["run"]["decision"], "accept_shortfall")
                time.sleep(0.15)
                return
            time.sleep(0.02)
        self.fail("接受不足后没有进入待老板验收")

    def test_shortfall_expand_scope_reruns_research(self) -> None:
        adapters = ShortfallAdapters()
        orchestrator = TeamOrchestrator(self.settings, self.store, adapters)
        data = orchestrator.create("查今天的 AI 新闻5条", None)
        run_id = data["run"]["id"]
        deadline = time.time() + 5
        while time.time() < deadline:
            if orchestrator.state(run_id)["run"]["status"] == "needs_decision":
                orchestrator.decide(run_id, "expand_scope", window_days=3)
                break
            time.sleep(0.02)
        else:
            self.fail("首次数量不足未触发决策")
        deadline = time.time() + 5
        while time.time() < deadline:
            run = orchestrator.state(run_id)["run"]
            if run["status"] == "needs_decision" and adapters.calls["dou"] == 2:
                self.assertEqual(adapters.calls["shen"], 2)
                self.assertEqual(adapters.calls["bang"], 0)
                self.assertEqual(run["decision"], "expand_scope")
                time.sleep(0.15)
                return
            time.sleep(0.02)
        self.fail("扩大时间窗口后没有重新检索")


if __name__ == "__main__":
    unittest.main()
