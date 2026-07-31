"""scripts.runners.openai（请求构建 + 响应解码）与 scripts.llm（客户端选择）
的 unittest 测试套件。不发任何网络请求。"""

import json
import unittest
from unittest import mock

from scripts.runners.base import SkillContext
from scripts.runners.openai import (
    OpenAICompatRunner,
    TOOL_NAME,
    build_chat_body,
    triggered_by_response,
)
from scripts.llm import get_llm_client, detect_available_llms
from scripts.runners import get_runner, detect_available_runners


CTX = SkillContext(skill_name="pdf-processing", description="Extract PDF text and merge files.")


class BuildChatBodyTest(unittest.TestCase):
    def test_body_structure(self):
        body = build_chat_body("帮我转个PDF", CTX, "gpt-4o-mini")
        self.assertEqual(body["model"], "gpt-4o-mini")
        self.assertEqual(body["messages"][1]["role"], "user")
        self.assertEqual(body["messages"][1]["content"], "帮我转个PDF")
        # system prompt carries the skill description
        self.assertIn("pdf-processing", body["messages"][0]["content"])
        self.assertIn("Extract PDF text", body["messages"][0]["content"])
        # tools carries the skill trigger tool
        tools = body["tools"]
        self.assertEqual(tools[0]["type"], "function")
        self.assertEqual(tools[0]["function"]["name"], TOOL_NAME)

    def test_tool_description_includes_skill(self):
        body = build_chat_body("q", CTX, "m")
        desc = body["tools"][0]["function"]["description"]
        self.assertIn("pdf-processing", desc)
        self.assertIn("Extract PDF text", desc)


class TriggeredByResponseTest(unittest.TestCase):
    def test_matching_tool_call_returns_true(self):
        payload = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {"id": "c1", "type": "function",
                         "function": {"name": TOOL_NAME,
                                      "arguments": json.dumps({"skill": "pdf-processing"})}},
                    ],
                }
            }]
        }
        triggered, evidence = triggered_by_response(payload, "pdf-processing")
        self.assertTrue(triggered)
        self.assertIn("pdf-processing", evidence)

    def test_no_tool_call_returns_false(self):
        payload = {"choices": [{"message": {"role": "assistant", "content": "no."}}]}
        triggered, _ = triggered_by_response(payload, "pdf-processing")
        self.assertFalse(triggered)

    def test_other_tool_call_returns_false(self):
        payload = {
            "choices": [{
                "message": {
                    "tool_calls": [
                        {"function": {"name": "search_web", "arguments": "{}"}},
                    ],
                }
            }]
        }
        triggered, _ = triggered_by_response(payload, "pdf-processing")
        self.assertFalse(triggered)

    def test_malformed_payload_returns_false(self):
        triggered, evidence = triggered_by_response({}, "pdf-processing")
        self.assertFalse(triggered)
        self.assertIn("响应格式异常", evidence)


class OpenAICompatRunnerTest(unittest.TestCase):
    def test_missing_model_reports_error(self):
        runner = OpenAICompatRunner(base_url="http://x", api_key="k")
        r = runner.run_query("q", CTX, model=None, timeout=10)
        self.assertFalse(r.triggered)
        self.assertTrue(r.error)

    def test_missing_api_key_reports_error(self):
        runner = OpenAICompatRunner(base_url="http://x", api_key="")
        r = runner.run_query("q", CTX, model="m", timeout=10)
        self.assertFalse(r.triggered)
        self.assertIn("api key", r.error.lower())

    @mock.patch("urllib.request.urlopen")
    def test_success_path_returns_triggered(self, mock_open):
        payload = {
            "choices": [{
                "message": {
                    "tool_calls": [
                        {"function": {"name": TOOL_NAME,
                                      "arguments": json.dumps({"skill": "pdf-processing"})}},
                    ],
                }
            }]
        }
        resp = mock.MagicMock()
        resp.read.return_value = json.dumps(payload).encode("utf-8")
        mock_open.return_value.__enter__.return_value = resp

        runner = OpenAICompatRunner(base_url="http://fake/v1", api_key="k")
        r = runner.run_query("q", CTX, model="m", timeout=10)
        self.assertTrue(r.triggered)
        # URL uses the configured base url
        url = mock_open.call_args[0][0].full_url
        self.assertEqual(url, "http://fake/v1/chat/completions")

    @mock.patch("urllib.request.urlopen")
    def test_http_error_reports_error(self, mock_open):
        import urllib.error

        mock_open.side_effect = urllib.error.HTTPError(
            "http://fake/v1/chat/completions", 401, "Unauthorized", {}, None)
        runner = OpenAICompatRunner(base_url="http://fake/v1", api_key="bad")
        r = runner.run_query("q", CTX, model="m", timeout=10)
        self.assertFalse(r.triggered)
        self.assertIn("401", r.error)


class RunnerSelectionTest(unittest.TestCase):
    @mock.patch("shutil.which", return_value="/usr/bin/claude")
    def test_detect_lists_claude_when_available(self, _):
        found = detect_available_runners()
        self.assertIn("claude-code", found)

    @mock.patch.dict("os.environ", {"OPENAI_API_KEY": "k"}, clear=False)
    @mock.patch("shutil.which", return_value=None)
    def test_detect_lists_openai_when_key_set(self, _):
        found = detect_available_runners()
        self.assertIn("openai", found)
        self.assertNotIn("claude-code", found)

    @mock.patch.dict("os.environ", {}, clear=True)
    @mock.patch("shutil.which", return_value=None)
    def test_detect_empty_when_nothing_available(self, _):
        self.assertEqual(detect_available_runners(), {})

    def test_get_runner_requires_explicit_name(self):
        with self.assertRaises(TypeError):
            get_runner()

    def test_openai_alias(self):
        runner = get_runner("openai-compatible", base_url="http://x", api_key="k")
        self.assertEqual(runner.name, "openai")
        self.assertEqual(runner.base_url, "http://x")

    def test_unknown_runner_raises(self):
        with self.assertRaises(ValueError):
            get_runner("does-not-exist")

    def test_irrelevant_kwargs_ignored_for_claude(self):
        # --runner claude-code --openai-base-url ... must not crash
        runner = get_runner("claude-code", base_url="http://x", api_key="k")
        self.assertEqual(runner.name, "claude-code")


class LLMClientSelectionTest(unittest.TestCase):
    @mock.patch("shutil.which", return_value="/usr/bin/claude")
    def test_detect_lists_claude_when_available(self, _):
        found = detect_available_llms()
        self.assertIn("claude", found)

    @mock.patch.dict("os.environ", {"OPENAI_API_KEY": "k"}, clear=False)
    @mock.patch("shutil.which", return_value=None)
    def test_detect_lists_openai_when_key_set(self, _):
        found = detect_available_llms()
        self.assertIn("openai", found)
        self.assertNotIn("claude", found)

    def test_get_llm_client_requires_explicit_name(self):
        with self.assertRaises(TypeError):
            get_llm_client()

    def test_openai_alias(self):
        client = get_llm_client("openai-compatible")
        self.assertEqual(client.name, "openai")

    def test_unknown_name_raises(self):
        with self.assertRaises(ValueError):
            get_llm_client("does-not-exist")

    def test_irrelevant_kwargs_ignored_for_claude(self):
        # --llm claude --openai-base-url ... must not crash
        client = get_llm_client("claude", base_url="http://x", api_key="k")
        self.assertEqual(client.name, "claude")

    def test_openai_kwargs_accepted(self):
        client = get_llm_client("openai", base_url="http://x", api_key="k")
        self.assertEqual(client.base_url, "http://x")
        self.assertEqual(client.api_key, "k")


if __name__ == "__main__":
    unittest.main()
