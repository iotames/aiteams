"""scripts.llm（LLM 文本补全客户端）的 unittest 测试套件。

覆盖：
- ClaudeCLIClient：以 mock subprocess.run 验证命令构造、模型参数、
  CLAUDECODE 环境变量移除、非零退出码报错。
- OpenAICompatClient：以 mock urllib.request.urlopen 验证请求体、
  成功响应解析、HTTP 错误、格式异常（不触网）。

在 skill-creator 根目录运行：
    python -m unittest discover -s tests -v
"""

import json
import unittest
from unittest import mock

from scripts.llm import ClaudeCLIClient, OpenAICompatClient, get_llm_client


class ClaudeCLIClientTest(unittest.TestCase):
    @mock.patch("subprocess.run")
    def test_runs_claude_with_prompt(self, mock_run):
        result = mock.Mock()
        result.returncode = 0
        result.stdout = "改进后的描述"
        result.stderr = ""
        mock_run.return_value = result

        client = ClaudeCLIClient()
        out = client.complete("请改进描述", model="sonnet")

        self.assertEqual(out, "改进后的描述")
        cmd = mock_run.call_args.args[0]
        self.assertEqual(cmd[0], "claude")
        self.assertEqual(cmd[1], "-p")
        self.assertIn("--output-format", cmd)
        self.assertIn("text", cmd)
        self.assertIn("--model", cmd)
        self.assertIn("sonnet", cmd)
        # prompt 通过 stdin 传递
        self.assertEqual(mock_run.call_args.kwargs["input"], "请改进描述")

    @mock.patch("subprocess.run")
    def test_claudecode_env_removed_for_nested_call(self, mock_run):
        result = mock.Mock()
        result.returncode = 0
        result.stdout = "ok"
        result.stderr = ""
        mock_run.return_value = result

        with mock.patch.dict("os.environ", {"CLAUDECODE": "1", "PATH": "/usr/bin"}, clear=True):
            ClaudeCLIClient().complete("q")

        env = mock_run.call_args.kwargs["env"]
        self.assertNotIn("CLAUDECODE", env)

    @mock.patch("subprocess.run")
    def test_nonzero_exit_raises(self, mock_run):
        result = mock.Mock()
        result.returncode = 2
        result.stdout = ""
        result.stderr = "boom"
        mock_run.return_value = result

        client = ClaudeCLIClient()
        with self.assertRaises(RuntimeError) as ctx:
            client.complete("q")
        self.assertIn("退出码 2", str(ctx.exception))
        self.assertIn("boom", str(ctx.exception))

    def test_no_model_flag_when_omitted(self):
        with mock.patch("subprocess.run") as mock_run:
            result = mock.Mock()
            result.returncode = 0
            result.stdout = "ok"
            result.stderr = ""
            mock_run.return_value = result
            ClaudeCLIClient().complete("q", model=None)
        cmd = mock_run.call_args.args[0]
        self.assertNotIn("--model", cmd)


class OpenAICompatClientTest(unittest.TestCase):
    @mock.patch("urllib.request.urlopen")
    def test_success_path_returns_content(self, mock_open):
        payload = {"choices": [{"message": {"content": "新描述"}}]}
        resp = mock.MagicMock()
        resp.read.return_value = json.dumps(payload).encode("utf-8")
        mock_open.return_value.__enter__.return_value = resp

        client = OpenAICompatClient(base_url="http://fake/v1", api_key="k")
        out = client.complete("请改进", model="gpt-4o-mini")

        self.assertEqual(out, "新描述")
        url = mock_open.call_args.args[0].full_url
        self.assertEqual(url, "http://fake/v1/chat/completions")
        # 请求体包含 model、messages、temperature
        body = json.loads(mock_open.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(body["model"], "gpt-4o-mini")
        self.assertEqual(body["messages"][0]["content"], "请改进")
        self.assertEqual(body["temperature"], 0)
        # Authorization 头
        headers = mock_open.call_args.args[0].headers
        self.assertEqual(headers.get("Authorization"), "Bearer k")

    @mock.patch("urllib.request.urlopen")
    def test_http_error_reports_detail(self, mock_open):
        import urllib.error

        mock_open.side_effect = urllib.error.HTTPError(
            "http://fake/v1/chat/completions", 401, "Unauthorized", {}, None)
        client = OpenAICompatClient(base_url="http://fake/v1", api_key="bad")
        with self.assertRaises(RuntimeError) as ctx:
            client.complete("q", model="m")
        self.assertIn("401", str(ctx.exception))

    @mock.patch("urllib.request.urlopen")
    def test_malformed_response_raises(self, mock_open):
        resp = mock.MagicMock()
        resp.read.return_value = b"not json at all"
        mock_open.return_value.__enter__.return_value = resp

        client = OpenAICompatClient(base_url="http://fake/v1", api_key="k")
        with self.assertRaises(RuntimeError):
            client.complete("q", model="m")

    def test_missing_model_raises(self):
        client = OpenAICompatClient(base_url="http://fake/v1", api_key="k")
        with self.assertRaises(ValueError):
            client.complete("q", model=None)

    def test_missing_api_key_raises(self):
        client = OpenAICompatClient(base_url="http://fake/v1", api_key="")
        with self.assertRaises(ValueError):
            client.complete("q", model="m")

    def test_default_base_url_from_env(self):
        with mock.patch.dict("os.environ", {"OPENAI_BASE_URL": "http://gw/v1"}, clear=True):
            client = OpenAICompatClient(api_key="k")
        self.assertEqual(client.base_url, "http://gw/v1")

    def test_default_base_url_fallback(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            client = OpenAICompatClient(api_key="k")
        self.assertEqual(client.base_url, "https://api.openai.com/v1")


class GetLlmClientTest(unittest.TestCase):
    def test_claude_client_factory(self):
        self.assertEqual(get_llm_client("claude").name, "claude")

    def test_openai_alias(self):
        self.assertEqual(get_llm_client("openai-compatible").name, "openai")

    def test_unknown_name_raises(self):
        with self.assertRaises(ValueError):
            get_llm_client("nope")


if __name__ == "__main__":
    unittest.main()
