"""unittest suite for scripts.aggregate_benchmark.

Covers calculate_stats, load_run_results (both workspace layouts), aggregate_results,
generate_benchmark and generate_markdown. Pure functions — no network, no subprocess.
"""

import json
import math
import tempfile
import unittest
from pathlib import Path

from scripts.aggregate_benchmark import (
    aggregate_results,
    calculate_stats,
    generate_benchmark,
    generate_markdown,
    load_run_results,
)


def make_grading(pass_rate=0.8, passed=4, total=5, errors=0):
    return {
        "expectations": [
            {"text": "output includes X", "passed": True, "evidence": "saw X"},
            {"text": "output is valid", "passed": False, "evidence": "not valid"},
        ],
        "summary": {
            "passed": passed,
            "failed": total - passed,
            "total": total,
            "pass_rate": pass_rate,
        },
        "execution_metrics": {
            "tool_calls": {"Read": 3},
            "total_tool_calls": 6,
            "errors_encountered": errors,
            "output_chars": 12450,
        },
        "timing": {"total_duration_seconds": 165.0},
        "user_notes_summary": {
            "uncertainties": ["used 2023 data"],
            "needs_review": [],
            "workarounds": ["fell back to overlay"],
        },
    }


def write_grading(run_dir: Path, grading=None):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "grading.json").write_text(
        json.dumps(grading or make_grading()), encoding="utf-8")


class CalculateStatsTest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(calculate_stats([]), {"mean": 0.0, "stddev": 0.0, "min": 0.0, "max": 0.0})

    def test_single_element(self):
        self.assertEqual(calculate_stats([5.0]), {"mean": 5.0, "stddev": 0.0, "min": 5.0, "max": 5.0})

    def test_mean_and_stddev(self):
        s = calculate_stats([1.0, 2.0, 3.0])
        self.assertAlmostEqual(s["mean"], 2.0)
        self.assertAlmostEqual(s["stddev"], 1.0)
        self.assertEqual(s["min"], 1.0)
        self.assertEqual(s["max"], 3.0)

    def test_rounding(self):
        s = calculate_stats([1.0, 1.0, 1.0])
        self.assertEqual(s["mean"], 1.0)


class LoadRunResultsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_flat_workspace_layout(self):
        """eval dirs directly under benchmark_dir (iteration workspace layout)."""
        g = make_grading(pass_rate=0.75, passed=3, total=4)
        write_grading(self.tmp / "eval-0" / "with_skill" / "run-1", g)
        write_grading(self.tmp / "eval-0" / "without_skill" / "run-1", make_grading(pass_rate=0.25, passed=1, total=4))
        (self.tmp / "eval-0" / "eval_metadata.json").write_text(
            json.dumps({"eval_id": 0, "eval_name": "first"}), encoding="utf-8")

        results = load_run_results(self.tmp)
        self.assertIn("with_skill", results)
        self.assertIn("without_skill", results)
        self.assertEqual(len(results["with_skill"]), 1)
        self.assertEqual(results["with_skill"][0]["pass_rate"], 0.75)
        # timing comes from grading.json timing block
        self.assertEqual(results["with_skill"][0]["time_seconds"], 165.0)
        self.assertEqual(results["with_skill"][0]["eval_id"], 0)
        # expectations preserved
        self.assertEqual(len(results["with_skill"][0]["expectations"]), 2)
        # notes from user_notes_summary
        self.assertIn("used 2023 data", results["with_skill"][0]["notes"])

    def test_legacy_runs_subdir_layout(self):
        """eval dirs under runs/ (legacy layout)."""
        write_grading(self.tmp / "runs" / "eval-1" / "with_skill" / "run-1")
        write_grading(self.tmp / "runs" / "eval-1" / "without_skill" / "run-1")

        results = load_run_results(self.tmp)
        self.assertIn("with_skill", results)
        # eval id derived from directory name
        self.assertEqual(results["with_skill"][0]["eval_id"], 1)

    def test_missing_grading_warns_but_continues(self):
        (self.tmp / "eval-0" / "with_skill" / "run-1").mkdir(parents=True)
        results = load_run_results(self.tmp)
        self.assertEqual(results.get("with_skill"), [])

    def test_no_eval_dirs_returns_empty(self):
        (self.tmp / "some_dir").mkdir()
        self.assertEqual(load_run_results(self.tmp), {})

    def test_timing_json_fallback(self):
        """timing.json sibling provides time/tokens when grading has none."""
        g = make_grading(pass_rate=1.0, passed=2, total=2)
        del g["timing"]
        run_dir = self.tmp / "eval-0" / "with_skill" / "run-1"
        write_grading(run_dir, g)
        (run_dir / "timing.json").write_text(
            json.dumps({"total_duration_seconds": 23.3, "total_tokens": 84852}),
            encoding="utf-8")

        results = load_run_results(self.tmp)
        r = results["with_skill"][0]
        self.assertEqual(r["time_seconds"], 23.3)
        self.assertEqual(r["tokens"], 84852)

    def test_multiple_runs_and_configs(self):
        for cfg in ("with_skill", "without_skill"):
            for n in ("run-1", "run-2"):
                write_grading(self.tmp / "eval-0" / cfg / n)
        results = load_run_results(self.tmp)
        self.assertEqual(len(results["with_skill"]), 2)
        self.assertEqual(len(results["without_skill"]), 2)


class AggregateResultsTest(unittest.TestCase):
    def test_empty(self):
        summary = aggregate_results({})
        self.assertIn("delta", summary)

    def test_single_config_no_delta_crash(self):
        results = {"with_skill": [
            {"pass_rate": 0.5, "time_seconds": 10.0, "tokens": 1000},
            {"pass_rate": 0.7, "time_seconds": 20.0, "tokens": 2000},
        ]}
        summary = aggregate_results(results)
        self.assertIn("with_skill", summary)
        self.assertAlmostEqual(summary["with_skill"]["pass_rate"]["mean"], 0.6)

    def test_two_configs_delta(self):
        results = {
            "with_skill": [{"pass_rate": 0.8, "time_seconds": 50.0, "tokens": 3000}],
            "without_skill": [{"pass_rate": 0.4, "time_seconds": 30.0, "tokens": 2000}],
        }
        summary = aggregate_results(results)
        self.assertEqual(summary["delta"]["pass_rate"], "+0.40")
        self.assertEqual(summary["delta"]["time_seconds"], "+20.0")
        self.assertEqual(summary["delta"]["tokens"], "+1000")


class GenerateBenchmarkTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_generate_benchmark_structure(self):
        write_grading(self.tmp / "eval-0" / "with_skill" / "run-1")
        write_grading(self.tmp / "eval-0" / "without_skill" / "run-1")

        bench = generate_benchmark(self.tmp, skill_name="pdf")
        self.assertEqual(bench["metadata"]["skill_name"], "pdf")
        self.assertEqual(bench["metadata"]["evals_run"], [0])
        # runs array contains expected keys
        self.assertTrue(bench["runs"])
        run = bench["runs"][0]
        self.assertIn("configuration", run)
        self.assertIn("result", run)
        self.assertIn("expectations", run)
        self.assertIn("notes", run)
        # run_summary + delta present
        self.assertIn("with_skill", bench["run_summary"])
        self.assertIn("delta", bench["run_summary"])

    def test_generate_markdown_has_metric_rows(self):
        write_grading(self.tmp / "eval-0" / "with_skill" / "run-1")
        write_grading(self.tmp / "eval-0" / "without_skill" / "run-1")
        bench = generate_benchmark(self.tmp, skill_name="pdf")
        md = generate_markdown(bench)
        self.assertIn("# Skill Benchmark: pdf", md)
        self.assertIn("Pass Rate", md)
        self.assertIn("Time", md)
        self.assertIn("Tokens", md)
        self.assertIn("With Skill", md)
        self.assertIn("Without Skill", md)


if __name__ == "__main__":
    unittest.main()
