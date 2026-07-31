"""scripts.utils 工具的 unittest 测试套件。

在 skill-creator 根目录运行：
    python -m unittest discover -s tests -v
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.utils import can_open_browser, parse_skill_md


class CanOpenBrowserTest(unittest.TestCase):
    def test_windows_always_true(self):
        with mock.patch("sys.platform", "win32"):
            self.assertTrue(can_open_browser())

    def test_darwin_always_true(self):
        with mock.patch("sys.platform", "darwin"):
            self.assertTrue(can_open_browser())

    def test_linux_without_display_false(self):
        with mock.patch.dict("os.environ", {}, clear=True), \
             mock.patch("sys.platform", "linux"):
            self.assertFalse(can_open_browser())

    def test_linux_with_display_true(self):
        with mock.patch.dict("os.environ", {"DISPLAY": ":0"}, clear=True), \
             mock.patch("sys.platform", "linux"):
            self.assertTrue(can_open_browser())

    def test_linux_with_wayland_true(self):
        with mock.patch.dict("os.environ", {"WAYLAND_DISPLAY": "wayland-0"}, clear=True), \
             mock.patch("sys.platform", "linux"):
            self.assertTrue(can_open_browser())


class ParseSkillMdTest(unittest.TestCase):
    def _make_skill(self, root: Path, content: str) -> Path:
        d = root / "demo"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(content, encoding="utf-8")
        return d

    def test_parses_basic_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = self._make_skill(Path(tmp), "---\nname: demo\ndescription: 描述\n---\n# 正文\n")
            name, desc, content = parse_skill_md(skill)
        self.assertEqual(name, "demo")
        self.assertEqual(desc, "描述")
        self.assertIn("# 正文", content)

    def test_handles_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = self._make_skill(Path(tmp), "\ufeff---\nname: demo\ndescription: 描述\n---\n# 正文\n")
            name, _, _ = parse_skill_md(skill)
        self.assertEqual(name, "demo")

    def test_missing_frontmatter_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = self._make_skill(Path(tmp), "# 无 frontmatter\n")
            with self.assertRaises(ValueError):
                parse_skill_md(skill)


if __name__ == "__main__":
    unittest.main()
