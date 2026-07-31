"""unittest suite for scripts.improve_description.improve_description.

Pure prompt-building + parsing around a pluggable llm_client — mocked here so
no network/CLI is touched. The llm_client is required (passing None raises).
"""

import tempfile
import unittest
from pathlib import Path

from scripts.improve_description import improve_description


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, prompt, model):
        self.calls.append(prompt)
        return self.responses.pop(0)


def make_eval_results(failed_query=None, false_query=None):
    results = [
        {"query": "做一个PDF", "should_trigger": True, "pass": True, "triggers": 3, "runs": 3},
        {"query": "写邮件", "should_trigger": False, "pass": True, "triggers": 0, "runs": 3},
    ]
    if failed_query:
        results.append({"query": failed_query, "should_trigger": True, "pass": False, "triggers": 0, "runs": 3})
    if false_query:
        results.append({"query": false_query, "should_trigger": False, "pass": False, "triggers": 3, "runs": 3})
    return {
        "skill_name": "demo",
        "description": "当前描述",
        "results": results,
        "summary": {"total": len(results), "passed": len(results) - len([r for r in results if not r["pass"]]),
                    "failed": len([r for r in results if not r["pass"]])},
    }


class ImproveDescriptionTest(unittest.TestCase):
    def test_parses_new_description_tags(self):
        llm = FakeLLM(["<new_description>改进后的描述</new_description>"])
        out = improve_description(
            skill_name="demo",
            skill_content="# 正文",
            current_description="当前描述",
            eval_results=make_eval_results(),
            history=[],
            model="m",
            llm_client=llm,
        )
        self.assertEqual(out, "改进后的描述")

    def test_strips_surrounding_quotes_when_no_tags(self):
        llm = FakeLLM(['"裸文本描述"'])
        out = improve_description(
            skill_name="demo", skill_content="", current_description="旧",
            eval_results=make_eval_results(), history=[], model="m", llm_client=llm,
        )
        self.assertEqual(out, "裸文本描述")

    def test_none_client_raises(self):
        with self.assertRaises(ValueError):
            improve_description(
                skill_name="demo", skill_content="", current_description="旧",
                eval_results=make_eval_results(), history=[], model="m", llm_client=None,
            )

    def test_prompt_contains_scores_and_categories(self):
        llm = FakeLLM(["<new_description>x</new_description>"])
        improve_description(
            skill_name="demo",
            skill_content="# 正文",
            current_description="当前描述",
            eval_results=make_eval_results(failed_query="漏触发", false_query="误触发"),
            history=[],
            model="m",
            llm_client=llm,
        )
        prompt = llm.calls[0]
        self.assertIn('"demo"', prompt)
        self.assertIn("当前描述", prompt)
        self.assertIn("Train: ", prompt)
        self.assertIn("FAILED TO TRIGGER", prompt)
        self.assertIn("漏触发", prompt)
        self.assertIn("FALSE TRIGGERS", prompt)
        self.assertIn("误触发", prompt)
        self.assertIn("<new_description>", prompt)

    def test_history_rendered_with_scores(self):
        llm = FakeLLM(["<new_description>x</new_description>"])
        history = [{
            "iteration": 1,
            "description": "上一版",
            "train_passed": 2, "train_total": 3,
            "test_passed": 1, "test_total": 2,
            "results": [{"query": "q", "pass": False, "triggers": 0, "runs": 3}],
        }]
        improve_description(
            skill_name="demo", skill_content="", current_description="当前",
            eval_results=make_eval_results(), history=history, model="m", llm_client=llm,
        )
        prompt = llm.calls[0]
        self.assertIn("PREVIOUS ATTEMPTS", prompt)
        self.assertIn("上一版", prompt)
        self.assertIn("train=2/3, test=1/2", prompt)

    def test_over_1024_chars_triggers_rewrite(self):
        long_desc = "长" * 1100
        llm = FakeLLM([f"<new_description>{long_desc}</new_description>", "<new_description>精简版</new_description>"])
        out = improve_description(
            skill_name="demo", skill_content="", current_description="旧",
            eval_results=make_eval_results(), history=[], model="m", llm_client=llm,
        )
        self.assertEqual(out, "精简版")
        self.assertEqual(len(llm.calls), 2)  # second call = rewrite
        self.assertIn("1024-character hard limit", llm.calls[1])

    def test_under_limit_no_rewrite(self):
        llm = FakeLLM(["<new_description>正常长度描述</new_description>"])
        improve_description(
            skill_name="demo", skill_content="", current_description="旧",
            eval_results=make_eval_results(), history=[], model="m", llm_client=llm,
        )
        self.assertEqual(len(llm.calls), 1)

    def test_log_dir_writes_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp) / "logs"
            llm = FakeLLM(["<new_description>记录此描述</new_description>"])
            improve_description(
                skill_name="demo", skill_content="", current_description="旧",
                eval_results=make_eval_results(), history=[], model="m",
                log_dir=log_dir, iteration=3, llm_client=llm,
            )
            f = log_dir / "improve_iter_3.json"
            self.assertTrue(f.exists())
            import json
            data = json.loads(f.read_text(encoding="utf-8"))
            self.assertEqual(data["parsed_description"], "记录此描述")
            self.assertEqual(data["final_description"], "记录此描述")
            self.assertIn("prompt", data)

    def test_test_score_included_when_provided(self):
        llm = FakeLLM(["<new_description>x</new_description>"])
        test_results = {
            "summary": {"total": 2, "passed": 1, "failed": 1},
            "results": [],
        }
        improve_description(
            skill_name="demo", skill_content="", current_description="旧",
            eval_results=make_eval_results(), history=[], model="m",
            test_results=test_results, llm_client=llm,
        )
        self.assertIn("Test: 1/2", llm.calls[0])


if __name__ == "__main__":
    unittest.main()
