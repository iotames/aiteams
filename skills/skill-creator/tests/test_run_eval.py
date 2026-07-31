"""unittest suite for scripts.run_eval.run_eval.

Uses a lightweight FakeRunner so no external CLI or network is touched. The
runner runs inside a ProcessPoolExecutor, so FakeRunner/FakeResult must be
picklable module-level classes with simple attributes.

The FakeRunner triggers iff a keyword appears in BOTH the description and the
query. `partial=True` (only meaningful with num_workers=1, where the worker is
reused across runs) triggers on 1 of every 3 calls to simulate a partial rate.
"""

import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from scripts.run_eval import run_eval
from scripts.runners.base import SkillContext


class FakeResult:
    def __init__(self, triggered, error=None):
        self.triggered = triggered
        self.error = error


class FakeRunner:
    name = "fake"

    def __init__(self, keywords, error_on=None, partial=False):
        self.keywords = tuple(keywords)
        self.error_on = tuple(error_on or ())
        self.partial = partial
        self.counter = 0

    def run_query(self, query, skill_ctx, model, timeout, project_root=None):
        self.counter += 1
        if query in self.error_on:
            return FakeResult(False, error="boom")
        desc = (skill_ctx.description or "").lower()
        q = query.lower()
        matched = any(k.lower() in desc and k.lower() in q for k in self.keywords)
        triggered = matched and (self.partial and self.counter % 3 == 0 or not self.partial)
        return FakeResult(triggered)


EVAL = [
    {"query": "做一个PDF", "should_trigger": True},
    {"query": "把表格转xlsx", "should_trigger": True},
    {"query": "写一封邮件", "should_trigger": False},
    {"query": "查天气", "should_trigger": False},
]


class RunEvalTest(unittest.TestCase):
    def setUp(self):
        # run_eval uses ProcessPoolExecutor; substitute a thread pool so the
        # FakeRunner instance (and its counter) is shared in-process. The two
        # pools share the submit/future/as_completed API.
        self._pool_patch = patch("scripts.run_eval.ProcessPoolExecutor", ThreadPoolExecutor)
        self._pool_patch.start()

    def tearDown(self):
        self._pool_patch.stop()

    def test_all_correct_single_run(self):
        runner = FakeRunner(keywords=["pdf", "xlsx"])
        out = run_eval(
            eval_set=EVAL,
            skill_ctx=SkillContext(skill_name="demo", description="使用于 pdf 和 xlsx 处理"),
            runner=runner,
            num_workers=2,
            timeout=10,
            runs_per_query=1,
            trigger_threshold=0.5,
            model=None,
        )
        self.assertEqual(out["skill_name"], "demo")
        self.assertEqual(out["summary"], {"total": 4, "passed": 4, "failed": 0})
        by_query = {r["query"]: r for r in out["results"]}
        self.assertTrue(by_query["做一个PDF"]["pass"])
        self.assertTrue(by_query["写一封邮件"]["pass"])

    def test_trigger_rate_reported_with_multiple_runs(self):
        runner = FakeRunner(keywords=["pdf"])
        out = run_eval(
            eval_set=EVAL[:1],
            skill_ctx=SkillContext(skill_name="demo", description="pdf"),
            runner=runner,
            num_workers=1,
            timeout=10,
            runs_per_query=3,
            trigger_threshold=0.5,
            model=None,
        )
        r = out["results"][0]
        self.assertEqual(r["triggers"], 3)
        self.assertEqual(r["runs"], 3)
        self.assertEqual(r["trigger_rate"], 1.0)
        self.assertTrue(r["pass"])

    def test_false_trigger_fails(self):
        runner = FakeRunner(keywords=["邮件"])
        out = run_eval(
            eval_set=EVAL[2:3],  # 写一封邮件 should_trigger=False
            skill_ctx=SkillContext(skill_name="demo", description="邮件"),
            runner=runner,
            num_workers=1,
            timeout=10,
            runs_per_query=1,
            trigger_threshold=0.5,
            model=None,
        )
        self.assertEqual(out["summary"]["passed"], 0)
        self.assertFalse(out["results"][0]["pass"])

    def test_missed_trigger_fails(self):
        runner = FakeRunner(keywords=[])  # never triggers
        out = run_eval(
            eval_set=EVAL[:1],
            skill_ctx=SkillContext(skill_name="demo", description="无关键词"),
            runner=runner,
            num_workers=1,
            timeout=10,
            runs_per_query=1,
            trigger_threshold=0.5,
            model=None,
        )
        self.assertFalse(out["results"][0]["pass"])
        self.assertEqual(out["results"][0]["triggers"], 0)

    def test_threshold_blocks_partial_trigger(self):
        # partial runner triggers 1 of 3 runs -> rate 0.33 < 0.5 -> fail
        runner = FakeRunner(keywords=["xlsx"], partial=True)
        out = run_eval(
            eval_set=[{"query": "转xlsx", "should_trigger": True}],
            skill_ctx=SkillContext(skill_name="demo", description="xlsx"),
            runner=runner,
            num_workers=1,
            timeout=10,
            runs_per_query=3,
            trigger_threshold=0.5,
            model=None,
        )
        self.assertFalse(out["results"][0]["pass"])
        self.assertEqual(out["results"][0]["triggers"], 1)
        self.assertEqual(out["results"][0]["runs"], 3)

    def test_threshold_allows_partial_above_cutoff(self):
        # threshold 0.5, 1/3=0.33 below -> still fail even with lower threshold? no:
        # use threshold 0.2 so 0.33 >= 0.2 -> pass
        runner = FakeRunner(keywords=["xlsx"], partial=True)
        out = run_eval(
            eval_set=[{"query": "转xlsx", "should_trigger": True}],
            skill_ctx=SkillContext(skill_name="demo", description="xlsx"),
            runner=runner,
            num_workers=1,
            timeout=10,
            runs_per_query=3,
            trigger_threshold=0.2,
            model=None,
        )
        self.assertTrue(out["results"][0]["pass"])

    def test_query_error_counts_as_no_trigger(self):
        runner = FakeRunner(keywords=["xlsx"], error_on=["转xlsx"])
        out = run_eval(
            eval_set=[{"query": "转xlsx", "should_trigger": True}],
            skill_ctx=SkillContext(skill_name="demo", description="xlsx"),
            runner=runner,
            num_workers=1,
            timeout=10,
            runs_per_query=1,
            trigger_threshold=0.5,
            model=None,
        )
        self.assertEqual(out["summary"]["passed"], 0)
        self.assertEqual(out["results"][0]["triggers"], 0)

    def test_summary_counts_mixed(self):
        runner = FakeRunner(keywords=["pdf"])
        out = run_eval(
            eval_set=EVAL,
            skill_ctx=SkillContext(skill_name="demo", description="pdf 专用"),
            runner=runner,
            num_workers=2,
            timeout=10,
            runs_per_query=1,
            trigger_threshold=0.5,
            model=None,
        )
        # pdf -> pass, xlsx -> fail, 邮件 -> pass, 天气 -> pass
        self.assertEqual(out["summary"], {"total": 4, "passed": 3, "failed": 1})


if __name__ == "__main__":
    unittest.main()
