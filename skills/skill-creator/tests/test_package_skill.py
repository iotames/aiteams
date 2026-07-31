"""unittest suite for scripts.package_skill.

Covers should_exclude rules and end-to-end packaging with a real (valid) skill
folder. Uses no network; validation runs against the real quick_validate rules.
"""

import tempfile
import unittest
import zipfile
from pathlib import Path
import json

from scripts.package_skill import package_skill, should_exclude


def make_valid_skill(root: Path, name: str = "demo"):
    """Create a minimal skill folder that passes quick_validate."""
    skill = root / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"""---
name: {name}
description: 测试技能，用于打包测试。不得包含尖括号。
---

# {name}

测试正文。
""",
        encoding="utf-8",
    )
    (skill / "scripts").mkdir()
    (skill / "scripts" / "helper.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    (skill / "references").mkdir()
    (skill / "references" / "extra.md").write_text("# extra", encoding="utf-8")
    (skill / "assets").mkdir()
    (skill / "assets" / "logo.png").write_bytes(b"\x89PNG fake")
    return skill


def add_excluded_files(skill: Path):
    """Add files/dirs that should be skipped during packaging."""
    (skill / "__pycache__").mkdir()
    (skill / "__pycache__" / "cache.pyc").write_bytes(b"pyc")
    (skill / "node_modules").mkdir()
    (skill / "node_modules" / "index.js").write_text("// dep", encoding="utf-8")
    (skill / ".DS_Store").write_bytes(b"ds")
    (skill / "notes.skill").write_bytes(b"zip")
    # root-level evals dir is excluded (but not nested evals under scripts/)
    (skill / "evals").mkdir()
    # evals.json must pass quick_validate even though the dir is excluded from packaging
    (skill / "evals" / "evals.json").write_text(
        json.dumps({"skill_name": "demo", "evals": [{"id": 1, "prompt": "测试", "expected_output": "输出"}]}),
        encoding="utf-8",
    )
    (skill / "scripts" / "evals").mkdir()
    (skill / "scripts" / "evals" / "keep.txt").write_text("keep", encoding="utf-8")


class ShouldExcludeTest(unittest.TestCase):
    def test_pycache_anywhere(self):
        self.assertTrue(should_exclude(Path("demo/__pycache__/cache.pyc")))

    def test_node_modules_anywhere(self):
        self.assertTrue(should_exclude(Path("demo/scripts/node_modules/lib.js")))

    def test_pyc_glob(self):
        self.assertTrue(should_exclude(Path("demo/scripts/util.pyc")))

    def test_skill_file(self):
        self.assertTrue(should_exclude(Path("demo/notes.skill")))

    def test_ds_store(self):
        self.assertTrue(should_exclude(Path("demo/.DS_Store")))

    def test_root_evals_excluded(self):
        self.assertTrue(should_exclude(Path("demo/evals/evals.json")))

    def test_nested_evals_kept(self):
        self.assertFalse(should_exclude(Path("demo/scripts/evals/keep.txt")))

    def test_regular_files_kept(self):
        self.assertFalse(should_exclude(Path("demo/SKILL.md")))
        self.assertFalse(should_exclude(Path("demo/scripts/helper.py")))
        self.assertFalse(should_exclude(Path("demo/assets/logo.png")))


class PackageSkillTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.skill = make_valid_skill(self.root)
        add_excluded_files(self.skill)

    def tearDown(self):
        self._tmp.cleanup()

    def test_package_success_creates_skill_file(self):
        out = self.root / "dist"
        result = package_skill(self.skill, out)
        self.assertIsNotNone(result)
        self.assertEqual(result, out / "demo.skill")
        self.assertTrue((out / "demo.skill").is_file())

    def test_zip_contains_expected_files_only(self):
        out = self.root / "dist"
        result = package_skill(self.skill, out)
        with zipfile.ZipFile(result) as zf:
            names = set(zf.namelist())
        self.assertIn("demo/SKILL.md", names)
        self.assertIn("demo/scripts/helper.py", names)
        self.assertIn("demo/references/extra.md", names)
        self.assertIn("demo/assets/logo.png", names)
        self.assertIn("demo/scripts/evals/keep.txt", names)
        # excluded artifacts absent
        self.assertNotIn("demo/__pycache__/cache.pyc", names)
        self.assertNotIn("demo/node_modules/index.js", names)
        self.assertNotIn("demo/.DS_Store", names)
        self.assertNotIn("demo/notes.skill", names)
        self.assertNotIn("demo/evals/evals.json", names)

    def test_package_uses_arcnames_relative_to_parent(self):
        out = self.root / "dist"
        with zipfile.ZipFile(package_skill(self.skill, out)) as zf:
            for n in zf.namelist():
                self.assertTrue(n.startswith("demo/"), f"unexpected arcname: {n}")

    def test_missing_skill_dir_returns_none(self):
        self.assertIsNone(package_skill(self.root / "nope"))

    def test_non_directory_returns_none(self):
        f = self.root / "file.txt"
        f.write_text("x", encoding="utf-8")
        self.assertIsNone(package_skill(f))

    def test_missing_sk_md_returns_none(self):
        bad = self.root / "badskill"
        bad.mkdir()
        self.assertIsNone(package_skill(bad))

    def test_invalid_skill_returns_none(self):
        # name does not match directory name -> validation fails before packaging
        bad = self.root / "mismatch"
        bad.mkdir()
        (bad / "SKILL.md").write_text(
            "---\nname: other\ndescription: 测试\n---\n# x\n", encoding="utf-8"
        )
        self.assertIsNone(package_skill(bad))
        # nothing was written
        self.assertFalse((bad / "other.skill").exists())


if __name__ == "__main__":
    unittest.main()
