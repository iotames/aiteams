"""unittest suite for scripts.generate_report.generate_html.

The report renders run_loop output. Pure function — no network, no subprocess.
"""

import unittest

from scripts.generate_report import generate_html


def sample_data():
    return {
        "original_description": "原描述",
        "best_description": "最佳描述",
        "best_score": "3/5 (train)",
        "iterations_run": 2,
        "train_size": 5,
        "test_size": 3,
        "history": [
            {
                "iteration": 1,
                "description": "尝试一",
                "train_passed": 2,
                "train_failed": 3,
                "train_total": 5,
                "train_results": [
                    {"query": "做pdf", "should_trigger": True, "pass": True, "triggers": 3, "runs": 3},
                    {"query": "写邮件", "should_trigger": False, "pass": True, "triggers": 0, "runs": 3},
                ],
                "test_passed": 1,
                "test_failed": 2,
                "test_total": 3,
                "test_results": [
                    {"query": "转xlsx", "should_trigger": True, "pass": False, "triggers": 0, "runs": 3},
                ],
                "passed": 2,
                "failed": 3,
                "total": 5,
                "results": [],
            }
        ],
    }


class GenerateHtmlTest(unittest.TestCase):
    def test_empty_data_renders_basic_page(self):
        out = generate_html({})
        self.assertIn("<!DOCTYPE html>", out)
        self.assertIn("Skill Description Optimization", out)

    def test_skill_name_in_title(self):
        out = generate_html({}, skill_name="my-skill")
        self.assertIn("<title>my-skill — Skill Description Optimization</title>", out)

    def test_skill_name_is_escaped(self):
        out = generate_html({}, skill_name="<script>alert(1)</script>")
        self.assertNotIn("<script>alert(1)</script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_auto_refresh_meta_tag(self):
        out = generate_html({}, auto_refresh=True)
        self.assertIn('<meta http-equiv="refresh" content="5">', out)
        self.assertNotIn('meta http-equiv="refresh"', generate_html({}, auto_refresh=False))

    def test_summary_section_renders(self):
        out = generate_html(sample_data())
        self.assertIn("原描述", out)
        self.assertIn("最佳描述", out)
        self.assertIn("3/5 (train)", out)

    def test_history_rows_and_query_columns(self):
        out = generate_html(sample_data())
        self.assertIn("做pdf", out)      # train query column header
        self.assertIn("写邮件", out)      # train query column header
        self.assertIn("转xlsx", out)      # test query column header
        self.assertIn("尝试一", out)      # description cell
        self.assertIn("6/6", out)         # train score cell (aggregated across runs)
        self.assertIn("0/3", out)         # test score cell

    def test_html_escaping_of_description(self):
        data = sample_data()
        data["history"][0]["description"] = '<b onclick="x()">描述</b>'
        out = generate_html(data)
        self.assertNotIn('<b onclick="x()">描述</b>', out)

    def test_query_text_is_escaped(self):
        data = sample_data()
        data["history"][0]["train_results"][0]["query"] = '<img src=x onerror=alert(1)>'
        out = generate_html(data)
        self.assertNotIn('<img src=x onerror=alert(1)>', out)

    def test_pass_fail_icons(self):
        out = generate_html(sample_data())
        self.assertIn("✓", out)
        self.assertIn("✗", out)

    def test_negative_train_polarity_class(self):
        data = sample_data()
        # 写邮件 should_trigger=False -> negative-col header
        out = generate_html(data)
        self.assertIn("negative-col", out)
        self.assertIn("positive-col", out)


if __name__ == "__main__":
    unittest.main()
