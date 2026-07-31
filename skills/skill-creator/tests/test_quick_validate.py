"""unittest suite for scripts.quick_validate.

Run from the skill-creator root:
    python -m unittest discover -s tests -v
"""

import tempfile
import unittest
from pathlib import Path

from scripts.quick_validate import validate_skill


def write_skill(tmp: Path, name: str = "valid-skill", extra_frontmatter: str = "",
                body: str = "# Skill\n") -> Path:
    skill_dir = tmp / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    fm = f"---\nname: {name}\ndescription: A valid description for testing.\n"
    if extra_frontmatter:
        fm += extra_frontmatter + "\n"
    fm += "---\n\n"
    (skill_dir / "SKILL.md").write_text(fm + body, encoding="utf-8")
    return skill_dir


class QuickValidateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    # --- basic structure ---

    def test_missing_skill_md(self):
        ok, msg = validate_skill(self.tmp / "nope")
        self.assertFalse(ok)
        self.assertIn("SKILL.md not found", msg)

    def test_no_frontmatter(self):
        d = self.tmp / "x"
        d.mkdir()
        (d / "SKILL.md").write_text("# no frontmatter", encoding="utf-8")
        ok, msg = validate_skill(d)
        self.assertFalse(ok)
        self.assertIn("No YAML frontmatter", msg)

    def test_invalid_yaml(self):
        d = self.tmp / "x"
        d.mkdir()
        (d / "SKILL.md").write_text("---\nname: [unclosed\n---\n", encoding="utf-8")
        ok, _ = validate_skill(d)
        self.assertFalse(ok)

    def test_valid_skill(self):
        d = write_skill(self.tmp)
        ok, msg = validate_skill(d)
        self.assertTrue(ok, msg)

    # --- name rules ---

    def test_name_uppercase_rejected(self):
        d = write_skill(self.tmp, name="PDF-Processing")
        ok, msg = validate_skill(d)
        self.assertFalse(ok)
        self.assertIn("kebab-case", msg)

    def test_name_dir_mismatch(self):
        # directory named "dir-a" but frontmatter name is "other-name"
        skill_dir = self.tmp / "dir-a"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: other-name\ndescription: desc\n---\n\n# x\n", encoding="utf-8")
        ok, msg = validate_skill(skill_dir)
        self.assertFalse(ok)
        self.assertIn("does not match the parent directory name", msg)

    def test_name_leading_hyphen_rejected(self):
        d = write_skill(self.tmp, name="-pdf")
        ok, msg = validate_skill(d)
        self.assertFalse(ok)

    def test_name_trailing_hyphen_rejected(self):
        d = write_skill(self.tmp, name="pdf-")
        ok, msg = validate_skill(d)
        self.assertFalse(ok)

    def test_name_consecutive_hyphens_rejected(self):
        d = write_skill(self.tmp, name="pdf--processing")
        ok, msg = validate_skill(d)
        self.assertFalse(ok)

    def test_name_too_long_rejected(self):
        long_name = "a" * 65
        d = write_skill(self.tmp, name=long_name)
        ok, msg = validate_skill(d)
        self.assertFalse(ok)
        self.assertIn("Maximum is 64", msg)

    def test_name_with_underscore_rejected(self):
        d = write_skill(self.tmp, name="my_skill")
        ok, msg = validate_skill(d)
        self.assertFalse(ok)

    # --- description rules ---

    def test_description_missing(self):
        d = self.tmp / "valid-skill"
        d.mkdir()
        (d / "SKILL.md").write_text("---\nname: valid-skill\n---\n\n# x\n", encoding="utf-8")
        ok, msg = validate_skill(d)
        self.assertFalse(ok)
        self.assertIn("Missing 'description'", msg)

    def test_description_empty(self):
        d = self.tmp / "valid-skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: valid-skill\ndescription: \"\"\n---\n\n# x\n", encoding="utf-8")
        ok, msg = validate_skill(d)
        self.assertFalse(ok)

    def test_description_too_long(self):
        d = write_skill(self.tmp, extra_frontmatter=f"description: {'x' * 1025}")
        ok, msg = validate_skill(d)
        self.assertFalse(ok)
        self.assertIn("Maximum is 1024", msg)

    def test_description_angle_brackets_rejected(self):
        d = write_skill(self.tmp, extra_frontmatter="description: has <b>html</b>")
        ok, msg = validate_skill(d)
        self.assertFalse(ok)

    # --- allowed-tools rules ---

    def test_allowed_tools_list_rejected(self):
        d = write_skill(self.tmp, extra_frontmatter="allowed-tools:\n  - Read\n  - Write")
        ok, msg = validate_skill(d)
        self.assertFalse(ok)
        self.assertIn("space-separated string", msg)

    def test_allowed_tools_comma_rejected(self):
        d = write_skill(self.tmp, extra_frontmatter="allowed-tools: Read, Write")
        ok, msg = validate_skill(d)
        self.assertFalse(ok)
        self.assertIn("space-separated", msg)

    def test_allowed_tools_ok(self):
        d = write_skill(self.tmp, extra_frontmatter="allowed-tools: Read Write Bash(git:*)")
        ok, msg = validate_skill(d)
        self.assertTrue(ok, msg)

    # --- unexpected fields ---

    def test_unexpected_frontmatter_key_rejected(self):
        d = write_skill(self.tmp, extra_frontmatter="bogus-field: 1")
        ok, msg = validate_skill(d)
        self.assertFalse(ok)
        self.assertIn("Unexpected key", msg)

    # --- metadata rules ---

    def test_metadata_non_string_value_rejected(self):
        d = write_skill(self.tmp, extra_frontmatter="metadata:\n  version: 1.0")
        ok, msg = validate_skill(d)
        self.assertFalse(ok)
        self.assertIn("must all be strings", msg)

    def test_metadata_ok(self):
        d = write_skill(self.tmp, extra_frontmatter="metadata:\n  version: \"1.0\"")
        ok, msg = validate_skill(d)
        self.assertTrue(ok, msg)

    # --- license ---

    def test_license_file_without_field_warns(self):
        d = write_skill(self.tmp)
        (d / "LICENSE.txt").write_text("MIT\n", encoding="utf-8")
        ok, msg = validate_skill(d)
        self.assertTrue(ok)
        self.assertIn("Warning", msg)

    # --- evals.json schema ---

    def test_evals_missing_required_field(self):
        d = write_skill(self.tmp)
        evals = {"skill_name": "valid-skill", "evals": [{"id": 1, "prompt": "p"}]}
        (d / "evals").mkdir()
        (d / "evals" / "evals.json").write_text(
            __import__("json").dumps(evals), encoding="utf-8")
        ok, msg = validate_skill(d)
        self.assertFalse(ok)
        self.assertIn("expected_output", msg)

    def test_evals_skill_name_mismatch(self):
        d = write_skill(self.tmp)
        evals = {"skill_name": "wrong-name", "evals": [{"id": 1, "prompt": "p", "expected_output": "o"}]}
        (d / "evals").mkdir()
        (d / "evals" / "evals.json").write_text(
            __import__("json").dumps(evals), encoding="utf-8")
        ok, msg = validate_skill(d)
        self.assertFalse(ok)
        self.assertIn("does not match frontmatter", msg)

    def test_evals_extra_fields_warn(self):
        d = write_skill(self.tmp)
        evals = {
            "skill_name": "valid-skill",
            "evals": [{"id": 1, "prompt": "p", "expected_output": "o", "name": "my-eval", "steps": ["a"]}],
        }
        (d / "evals").mkdir()
        (d / "evals" / "evals.json").write_text(
            __import__("json").dumps(evals), encoding="utf-8")
        ok, msg = validate_skill(d)
        self.assertTrue(ok)
        self.assertIn("outside the schema", msg)

    def test_evals_valid(self):
        d = write_skill(self.tmp)
        evals = {
            "skill_name": "valid-skill",
            "evals": [{
                "id": 1,
                "prompt": "Do the thing",
                "expected_output": "The thing done",
                "files": ["data/sample.pdf"],
                "expectations": ["output includes X"],
            }],
        }
        (d / "evals").mkdir()
        (d / "evals" / "evals.json").write_text(
            __import__("json").dumps(evals), encoding="utf-8")
        ok, msg = validate_skill(d)
        self.assertTrue(ok, msg)


if __name__ == "__main__":
    unittest.main()
