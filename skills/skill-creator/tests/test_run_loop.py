"""scripts.run_loop 的 unittest 测试套件。

split_eval_set 是纯函数；run_loop 端到端测试使用与 test_run_eval 相同的
fake-runner 方案（ProcessPoolExecutor -> ThreadPoolExecutor）加 FakeLLM，
不接触网络或 CLI。
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.run_loop import run_loop, split_eval_set


class FakeResult:
    def __init__(self, triggered, error=None):
        self.triggered = triggered
        self.error = error


class FakeRunner:
    """Triggers iff keyword appears in both description and query."""

    name = "fake"

    def __init__(self, keywords):
        self.keywords = tuple(keywords)

    def run_query(self, query, skill_ctx, model, timeout, project_root=None):
        desc = (skill_ctx.description or "").lower()
        q = query.lower()
        matched = any(k.lower() in desc and k.lower() in q for k in self.keywords)
        return FakeResult(matched)


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, prompt, model):
        self.calls.append(prompt)
        return self.responses.pop(0)


def make_skill(root: Path, name: str = "demo") -> Path:
    skill = root / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: 初始描述。\n---\n# 正文\n",
        encoding="utf-8",
    )
    return skill


def make_eval_set():
    return [
        {"query": "做一个PDF", "should_trigger": True},
        {"query": "写一封邮件", "should_trigger": False},
        {"query": "查天气", "should_trigger": False},
        {"query": "转xlsx表格", "should_trigger": True},
    ]


class SplitEvalSetTest(unittest.TestCase):
    def test_split_partitions_all_items(self):
        train, test = split_eval_set(make_eval_set(), holdout=0.4)
        combined = train + test
        self.assertEqual(len(combined), 4)
        # no item lost or duplicated
        self.assertEqual(len({e["query"] for e in combined}), 4)

    def test_split_is_stratified(self):
        train, test = split_eval_set(make_eval_set(), holdout=0.5)
        # each group contributes its should_trigger=False items
        self.assertTrue(any(e["should_trigger"] for e in train))
        self.assertTrue(any(not e["should_trigger"] for e in train))
        self.assertTrue(any(e["should_trigger"] for e in test))
        self.assertTrue(any(not e["should_trigger"] for e in test))

    def test_seed_is_reproducible(self):
        a_train, a_test = split_eval_set(make_eval_set(), 0.4, seed=42)
        b_train, b_test = split_eval_set(make_eval_set(), 0.4, seed=42)
        self.assertEqual(
            [e["query"] for e in a_train + a_test],
            [e["query"] for e in b_train + b_test],
        )

    def test_different_seed_changes_split(self):
        # use a large enough set that different seeds reliably differ
        big = (
            [{"query": f"p{i}", "should_trigger": True} for i in range(20)]
            + [{"query": f"n{i}", "should_trigger": False} for i in range(20)]
        )
        a_train, _ = split_eval_set(big, 0.4, seed=1)
        b_train, _ = split_eval_set(big, 0.4, seed=2)
        self.assertNotEqual([e["query"] for e in a_train], [e["query"] for e in b_train])

    def test_small_set_keeps_one_test_each(self):
        # with only one negative item and holdout, it lands in test -> train still valid
        train, test = split_eval_set(
            [{"query": "q1", "should_trigger": True}, {"query": "q2", "should_trigger": False}],
            holdout=0.4,
        )
        self.assertEqual(len(train) + len(test), 2)
        self.assertTrue(any(not e["should_trigger"] for e in test))

    def test_all_positive(self):
        train, test = split_eval_set(
            [{"query": f"q{i}", "should_trigger": True} for i in range(6)],
            holdout=0.33,
        )
        self.assertEqual(len(train) + len(test), 6)
        self.assertTrue(all(e["should_trigger"] for e in train + test))


class RunLoopTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._pool_patch = patch("scripts.run_loop.run_eval")
        self.fake_run_eval = self._pool_patch.start()

    def tearDown(self):
        self._pool_patch.stop()
        self._tmp.cleanup()

    def _fake_run_eval(self, output):
        def fake_run_eval(eval_set, **kwargs):
            results = []
            for item in eval_set:
                q = item["query"]
                rate = output[q]
                should = item["should_trigger"]
                if should:
                    did_pass = rate >= 0.5
                else:
                    did_pass = rate < 0.5
                results.append({
                    "query": q,
                    "should_trigger": should,
                    "trigger_rate": rate,
                    "triggers": 1 if rate else 0,
                    "runs": 1,
                    "pass": did_pass,
                })
            passed = sum(1 for r in results if r["pass"])
            return {"skill_name": "demo", "description": kwargs["skill_ctx"].description,
                    "results": results,
                    "summary": {"total": len(results), "passed": passed,
                                "failed": len(results) - passed}}

        return fake_run_eval

    def test_loop_early_exit_when_all_pass(self):
        skill = make_skill(self.root)
        eval_set = make_eval_set()
        # description without keywords -> all fail on iteration 1; FakeLLM returns
        # a description with keywords -> all pass on iteration 2.
        def side_effect(eval_set, **kwargs):
            desc = kwargs["skill_ctx"].description
            if "pdf" in desc:
                rates = {"做一个PDF": 1.0, "写一封邮件": 0.0, "查天气": 0.0, "转xlsx表格": 1.0}
            else:
                rates = {"做一个PDF": 0.0, "写一封邮件": 0.0, "查天气": 0.0, "转xlsx表格": 0.0}
            return self._fake_run_eval(rates)(eval_set, **kwargs)

        fake = self.fake_run_eval
        fake.side_effect = side_effect

        llm = FakeLLM(["<new_description>用 pdf 和 xlsx</new_description>"])

        out = run_loop(
            eval_set=eval_set,
            skill_path=skill,
            description_override="初始描述",
            num_workers=2,
            timeout=10,
            max_iterations=3,
            runs_per_query=1,
            trigger_threshold=0.5,
            holdout=0.0,
            model="test-model",
            verbose=False,
            llm_client=llm,
            runner=FakeRunner(keywords=[]),
        )
        self.assertEqual(out["exit_reason"], "all_passed (iteration 2)")
        self.assertEqual(out["iterations_run"], 2)
        self.assertEqual(out["best_description"], "用 pdf 和 xlsx")
        self.assertEqual(out["best_score"], "4/4")
        self.assertEqual(out["best_test_score"], None)

    def test_loop_hits_max_iterations(self):
        skill = make_skill(self.root)
        fake = self.fake_run_eval
        fake.side_effect = self._fake_run_eval(
            {"做一个PDF": 0.0, "写一封邮件": 0.0, "查天气": 0.0, "转xlsx表格": 0.0}
        )
        llm = FakeLLM(["<new_description>还是不行</new_description>"])

        out = run_loop(
            eval_set=make_eval_set(),
            skill_path=skill,
            description_override="初始描述",
            num_workers=2,
            timeout=10,
            max_iterations=2,
            runs_per_query=1,
            trigger_threshold=0.5,
            holdout=0.0,
            model="test-model",
            verbose=False,
            llm_client=llm,
            runner=FakeRunner(keywords=[]),
        )
        self.assertEqual(out["exit_reason"], "max_iterations (2)")
        self.assertEqual(out["iterations_run"], 2)
        self.assertEqual(len(out["history"]), 2)

    def test_loop_with_holdout_reports_test_score(self):
        skill = make_skill(self.root)
        fake = self.fake_run_eval
        fake.side_effect = self._fake_run_eval(
            {"做一个PDF": 0.0, "写一封邮件": 0.0, "查天气": 0.0, "转xlsx表格": 0.0}
        )
        llm = FakeLLM(["<new_description>改进</new_description>"])

        out = run_loop(
            eval_set=make_eval_set(),
            skill_path=skill,
            description_override="初始描述",
            num_workers=2,
            timeout=10,
            max_iterations=1,
            runs_per_query=1,
            trigger_threshold=0.5,
            holdout=0.4,
            model="test-model",
            verbose=False,
            llm_client=llm,
            runner=FakeRunner(keywords=[]),
        )
        self.assertIsNotNone(out["best_test_score"])
        self.assertGreater(out["train_size"], 0)
        self.assertGreater(out["test_size"], 0)
        # holdout split is deterministic
        self.assertEqual(out["train_size"] + out["test_size"], 4)

    def test_loop_errors_on_empty_train_set(self):
        """holdout 过大会把 train 拆成空集，必须显式报错而非静默通过。"""
        skill = make_skill(self.root)
        # 2 条 eval + holdout=0.4 → train 为空
        tiny = [
            {"query": "做一个PDF", "should_trigger": True},
            {"query": "写一封邮件", "should_trigger": False},
        ]
        fake = self.fake_run_eval
        fake.side_effect = self._fake_run_eval(
            {"做一个PDF": 0.0, "写一封邮件": 0.0}
        )
        llm = FakeLLM(["<new_description>x</new_description>"])

        with self.assertRaisesRegex(ValueError, "train 集为空"):
            run_loop(
                eval_set=tiny,
                skill_path=skill,
                description_override="初始描述",
                num_workers=2,
                timeout=10,
                max_iterations=2,
                runs_per_query=1,
                trigger_threshold=0.5,
                holdout=0.4,
                model="test-model",
                verbose=False,
                llm_client=llm,
                runner=FakeRunner(keywords=[]),
            )

    def test_original_description_reported(self):
        skill = make_skill(self.root)
        fake = self.fake_run_eval
        fake.side_effect = self._fake_run_eval(
            {"做一个PDF": 0.0, "写一封邮件": 0.0, "查天气": 0.0, "转xlsx表格": 0.0}
        )
        llm = FakeLLM(["<new_description>x</new_description>"])
        out = run_loop(
            eval_set=make_eval_set(),
            skill_path=skill,
            description_override=None,
            num_workers=2,
            timeout=10,
            max_iterations=1,
            runs_per_query=1,
            trigger_threshold=0.5,
            holdout=0.0,
            model="test-model",
            verbose=False,
            llm_client=llm,
            runner=FakeRunner(keywords=[]),
        )
        self.assertEqual(out["original_description"], "初始描述。")
        self.assertEqual(out["best_description"], "初始描述。")  # no improvement run in history yet

    def test_live_report_written(self):
        skill = make_skill(self.root)
        report_path = self.root / "report.html"
        fake = self.fake_run_eval
        fake.side_effect = self._fake_run_eval(
            {"做一个PDF": 0.0, "写一封邮件": 0.0, "查天气": 0.0, "转xlsx表格": 0.0}
        )
        llm = FakeLLM(["<new_description>x</new_description>"])
        run_loop(
            eval_set=make_eval_set(),
            skill_path=skill,
            description_override="初始描述",
            num_workers=2,
            timeout=10,
            max_iterations=1,
            runs_per_query=1,
            trigger_threshold=0.5,
            holdout=0.0,
            model="test-model",
            verbose=False,
            live_report_path=report_path,
            llm_client=llm,
            runner=FakeRunner(keywords=[]),
        )
        self.assertTrue(report_path.exists())
        content = report_path.read_text(encoding="utf-8")
        self.assertIn("技能描述优化", content)
        self.assertIn("auto", content)

    def test_duplicate_query_position_split(self):
        """重复 query 的两条 eval 条目必须按位置切分 train/test。

        回归测试：run_loop 曾按 query 字符串在 all_results 中过滤拆
        train/test，重复 query 会导致条目丢失或错配。现在 run_eval 按
        eval_set 顺序输出、run_loop 按位置切分，重复 query 也必须各归其位。
        """
        skill = make_skill(self.root)
        # 两条相同 query、should_trigger 相反的条目，都进入 train（holdout=0）
        dup_eval = [
            {"query": "处理pdf文件", "should_trigger": True},
            {"query": "处理pdf文件", "should_trigger": False},
        ]
        fake = self.fake_run_eval
        fake.side_effect = self._fake_run_eval(
            {"处理pdf文件": 0.0}
        )
        llm = FakeLLM(["<new_description>x</new_description>"])
        out = run_loop(
            eval_set=dup_eval,
            skill_path=skill,
            description_override="初始描述",
            num_workers=2,
            timeout=10,
            max_iterations=1,
            runs_per_query=1,
            trigger_threshold=0.5,
            holdout=0.0,
            model="test-model",
            verbose=False,
            llm_client=llm,
            runner=FakeRunner(keywords=[]),
        )
        # 两条条目都保留在 train 结果中（rate 0.0：应触发者失败、不应触发者通过），
        # 未被去重或错配
        self.assertEqual(out["train_size"], 2)
        self.assertEqual(len(out["history"][0]["train_results"]), 2)
        self.assertEqual(out["best_train_score"], "1/2")
        # 两条结果确实对应两条 eval 条目
        self.assertEqual(
            [r["should_trigger"] for r in out["history"][0]["train_results"]],
            [True, False],
        )


if __name__ == "__main__":
    unittest.main()
