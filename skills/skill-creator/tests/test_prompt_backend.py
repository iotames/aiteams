"""unittest suite for scripts.utils.prompt_choose_backend.

The backend-selection prompt must always hand the decision to the user:
- candidates are only listed, never auto-picked
- Enter uses the recommended default
- typing a name selects it
- non-interactive stdin (EOFError) raises RuntimeError asking for the flag
"""

import unittest
from unittest import mock

from scripts.utils import prompt_choose_backend

CANDIDATES = {
    "claude-code": "检测到 claude CLI",
    "openai": "已设置 OPENAI_API_KEY",
}


class PromptChooseBackendTest(unittest.TestCase):
    @mock.patch("builtins.input", return_value="")
    def test_enter_uses_first_candidate_as_default(self, _):
        self.assertEqual(
            prompt_choose_backend("评测后端 (runner)", CANDIDATES, "--runner"),
            "claude-code",
        )

    @mock.patch("builtins.input", return_value="")
    def test_recommended_overrides_default_order(self, _):
        self.assertEqual(
            prompt_choose_backend("评测后端 (runner)", CANDIDATES, "--runner",
                                  recommended="openai"),
            "openai",
        )

    @mock.patch("builtins.input", return_value="openai")
    def test_typed_name_is_respected(self, _):
        self.assertEqual(
            prompt_choose_backend("评测后端 (runner)", CANDIDATES, "--runner"),
            "openai",
        )

    @mock.patch("builtins.input", return_value="OpenAI")
    def test_typed_name_case_insensitive(self, _):
        self.assertEqual(
            prompt_choose_backend("评测后端 (runner)", CANDIDATES, "--runner"),
            "openai",
        )

    @mock.patch("builtins.input", side_effect=EOFError)
    def test_non_interactive_stdin_raises_runtime_error(self, _):
        with self.assertRaises(RuntimeError) as ctx:
            prompt_choose_backend("评测后端 (runner)", CANDIDATES, "--runner")
        self.assertIn("--runner", str(ctx.exception))

    @mock.patch("builtins.input", return_value="nonexistent")
    def test_unknown_choice_raises_value_error(self, _):
        with self.assertRaises(ValueError):
            prompt_choose_backend("评测后端 (runner)", CANDIDATES, "--runner")

    def test_no_candidates_raises_runtime_error(self):
        with self.assertRaises(RuntimeError):
            prompt_choose_backend("评测后端 (runner)", {}, "--runner")


if __name__ == "__main__":
    unittest.main()
