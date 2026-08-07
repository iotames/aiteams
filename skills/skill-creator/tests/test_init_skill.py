"""scripts.init_skill 的 unittest 测试套件。

在 skill-creator 根目录运行：
    python -m unittest discover -s tests -v
"""

import tempfile
import unittest
from pathlib import Path

from scripts.init_skill import (
    MAX_SKILL_NAME_LENGTH,
    init_skill,
    normalize_skill_name,
    parse_resources,
    title_case_skill_name,
)
from scripts.quick_validate import validate_skill
from scripts.utils import extract_frontmatter


class NormalizeSkillNameTest(unittest.TestCase):
    def test_lowercases_and_hyphenates(self):
        self.assertEqual(normalize_skill_name("My Cool Skill"), "my-cool-skill")

    def test_strips_illegal_characters(self):
        self.assertEqual(normalize_skill_name("PDF_Processor!"), "pdf-processor")

    def test_collapses_duplicate_hyphens(self):
        self.assertEqual(normalize_skill_name("a--b---c"), "a-b-c")

    def test_empty_after_normalization(self):
        self.assertEqual(normalize_skill_name("!!!"), "")


class TitleCaseTest(unittest.TestCase):
    def test_title_case(self):
        self.assertEqual(
            title_case_skill_name("flipbook-download"), "Flipbook Download")


class ParseResourcesTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(
            parse_resources("scripts,references,assets"),
            ["scripts", "references", "assets"])

    def test_deduplicates(self):
        self.assertEqual(parse_resources("scripts,scripts"), ["scripts"])

    def test_empty(self):
        self.assertEqual(parse_resources(""), [])


class InitSkillTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_creates_skill_with_valid_template(self):
        result = init_skill("my-skill", str(self.tmp), [], False)
        self.assertIsNotNone(result)
        skill_dir = result
        self.assertTrue((skill_dir / "SKILL.md").exists())
        ok, msg = validate_skill(skill_dir)
        self.assertTrue(ok, msg)
        frontmatter, _, _ = extract_frontmatter(
            (skill_dir / "SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(frontmatter["name"], "my-skill")

    def test_creates_resource_dirs(self):
        result = init_skill(
            "with-res", str(self.tmp), ["scripts", "references"], False)
        self.assertIsNotNone(result)
        self.assertTrue((result / "scripts").is_dir())
        self.assertTrue((result / "references").is_dir())
        self.assertFalse((result / "assets").exists())

    def test_examples_creates_placeholder_files(self):
        result = init_skill(
            "with-examples", str(self.tmp),
            ["scripts", "references", "assets"], True)
        self.assertIsNotNone(result)
        self.assertTrue((result / "scripts" / "example.py").exists())
        self.assertTrue((result / "references" / "api_reference.md").exists())
        self.assertTrue((result / "assets" / "example_asset.txt").exists())

    def test_existing_dir_fails(self):
        (self.tmp / "taken").mkdir()
        self.assertIsNone(init_skill("taken", str(self.tmp), [], False))

    def test_name_too_long_fails(self):
        long_name = "a" * (MAX_SKILL_NAME_LENGTH + 1)
        self.assertIsNone(init_skill(long_name, str(self.tmp), [], False))
