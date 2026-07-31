"""eval-viewer/generate_review.py 的 unittest 测试套件。

覆盖 find_runs、build_run、embed_file、generate_html、load_previous_iteration、
get_mime_type 等纯函数。使用临时目录构造工作区结构，不启动 HTTP 服务器。

在 skill-creator 根目录运行：
    python -m unittest discover -s tests -v
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

# eval-viewer 不是包，需要手动加入导入路径
_VIEWER_DIR = Path(__file__).resolve().parents[1] / "eval-viewer"
sys.path.insert(0, str(_VIEWER_DIR))

import generate_review  # noqa: E402
from generate_review import (  # noqa: E402
    build_run,
    embed_file,
    find_runs,
    generate_html,
    get_mime_type,
    load_previous_iteration,
)


def make_workspace(root: Path, run_path: str = "eval-0/with_skill", eval_id: int = 0) -> Path:
    """构造一个包含单次运行输出的工作区。"""
    run_dir = root / run_path
    (run_dir / "outputs").mkdir(parents=True)
    (run_dir / "outputs" / "result.txt").write_text("任务完成", encoding="utf-8")
    (run_dir / "eval_metadata.json").write_text(
        json.dumps({"eval_id": eval_id, "eval_name": "描述性名称", "prompt": "测试 prompt"}),
        encoding="utf-8",
    )
    (run_dir / "grading.json").write_text(
        json.dumps({
            "expectations": [{"text": "输出存在", "passed": True, "evidence": "saw file"}],
            "summary": {"passed": 1, "failed": 0, "total": 1, "pass_rate": 1.0},
        }),
        encoding="utf-8",
    )
    return root


class FindRunsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_finds_run_with_outputs_dir(self):
        make_workspace(self.root)
        runs = find_runs(self.root)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["id"], "eval-0-with_skill")

    def test_recursive_discovery_under_nested_dirs(self):
        make_workspace(self.root, "iteration-1/eval-0/with_skill")
        runs = find_runs(self.root)
        self.assertEqual(len(runs), 1)

    def test_skips_build_and_vcs_dirs(self):
        (self.root / "node_modules").mkdir()
        make_workspace(self.root, "node_modules/eval-0/with_skill")
        runs = find_runs(self.root)
        self.assertEqual(len(runs), 0)

    def test_empty_workspace_returns_empty(self):
        (self.root / "nothing").mkdir()
        self.assertEqual(find_runs(self.root), [])

    def test_sorted_by_eval_id(self):
        make_workspace(self.root, "eval-1/with_skill", eval_id=1)
        make_workspace(self.root, "eval-0/without_skill", eval_id=0)
        runs = find_runs(self.root)
        ids = [r["eval_id"] for r in runs]
        self.assertEqual(ids, [0, 1])


class BuildRunTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_metadata_prompt_and_grading_loaded(self):
        make_workspace(self.root)
        run = build_run(self.root, self.root / "eval-0" / "with_skill")
        self.assertEqual(run["prompt"], "测试 prompt")
        self.assertEqual(run["eval_id"], 0)
        self.assertIsNotNone(run["grading"])
        self.assertEqual(run["grading"]["summary"]["passed"], 1)
        # 输出文件被收集（transcript.md 等元数据除外）
        names = [o["name"] for o in run["outputs"]]
        self.assertIn("result.txt", names)

    def test_prompt_falls_back_to_placeholder(self):
        run_dir = self.root / "eval-0" / "with_skill"
        (run_dir / "outputs").mkdir(parents=True)
        (run_dir / "outputs" / "out.md").write_text("x", encoding="utf-8")
        run = build_run(self.root, run_dir)
        self.assertIn("未找到 prompt", run["prompt"])
        self.assertIsNone(run["eval_id"])


class EmbedFileTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_text_file_inlined(self):
        f = self.root / "note.md"
        f.write_text("你好", encoding="utf-8")
        entry = embed_file(f)
        self.assertEqual(entry["type"], "text")
        self.assertEqual(entry["content"], "你好")

    def test_image_embedded_as_data_uri(self):
        f = self.root / "img.png"
        f.write_bytes(b"\x89PNG-fake")
        entry = embed_file(f)
        self.assertEqual(entry["type"], "image")
        self.assertTrue(entry["data_uri"].startswith("data:image/png;base64,"))

    def test_pdf_embedded(self):
        f = self.root / "doc.pdf"
        f.write_bytes(b"%PDF-fake")
        entry = embed_file(f)
        self.assertEqual(entry["type"], "pdf")
        self.assertTrue(entry["data_uri"].startswith("data:application/pdf;base64,"))

    def test_xlsx_returns_base64(self):
        f = self.root / "sheet.xlsx"
        f.write_bytes(b"PK-fake")
        entry = embed_file(f)
        self.assertEqual(entry["type"], "xlsx")
        self.assertIn("data_b64", entry)

    def test_unknown_binary_returns_download_link(self):
        f = self.root / "blob.dat"
        f.write_bytes(b"\x00\x01")
        entry = embed_file(f)
        self.assertEqual(entry["type"], "binary")
        self.assertTrue(entry["data_uri"].startswith("data:"))

    def test_missing_file_reports_error(self):
        entry = embed_file(self.root / "nope.txt")
        self.assertEqual(entry["type"], "error")


class GenerateHtmlTest(unittest.TestCase):
    def test_embeds_data_into_template(self):
        runs = [{"id": "eval-0-with_skill", "prompt": "p", "outputs": []}]
        html = generate_html(runs, skill_name="my-skill")
        self.assertIn("const EMBEDDED_DATA =", html)
        self.assertIn("my-skill", html)

    def test_benchmark_passed_through(self):
        benchmark = {"metadata": {"skill_name": "x"}, "runs": []}
        html = generate_html([], "s", benchmark=benchmark)
        self.assertIn("skill_name", html)
        self.assertIn('"skill_name": "x"', html)

    def test_previous_feedback_passed_through(self):
        previous = {"eval-0-with_skill": {"feedback": "改一下", "outputs": []}}
        html = generate_html([], "s", previous=previous)
        self.assertIn("改一下", html)


class LoadPreviousIterationTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_feedback_and_outputs_loaded(self):
        make_workspace(self.root)
        (self.root / "feedback.json").write_text(
            json.dumps({"reviews": [
                {"run_id": "eval-0-with_skill", "feedback": "很好", "timestamp": "t"},
            ], "status": "complete"}),
            encoding="utf-8",
        )
        prev = load_previous_iteration(self.root)
        self.assertIn("eval-0-with_skill", prev)
        self.assertEqual(prev["eval-0-with_skill"]["feedback"], "很好")
        # 运行中的输出文件被带入
        self.assertTrue(prev["eval-0-with_skill"]["outputs"])

    def test_empty_feedback_omitted(self):
        make_workspace(self.root)
        (self.root / "feedback.json").write_text(
            json.dumps({"reviews": [
                {"run_id": "eval-0-with_skill", "feedback": "", "timestamp": "t"},
            ], "status": "complete"}),
            encoding="utf-8",
        )
        prev = load_previous_iteration(self.root)
        self.assertEqual(prev["eval-0-with_skill"]["feedback"], "")

    def test_missing_feedback_file(self):
        make_workspace(self.root)
        prev = load_previous_iteration(self.root)
        self.assertIn("eval-0-with_skill", prev)
        self.assertEqual(prev["eval-0-with_skill"]["feedback"], "")


class GetMimeTypeTest(unittest.TestCase):
    def test_mime_overrides(self):
        self.assertEqual(get_mime_type(Path("a.svg")), "image/svg+xml")
        self.assertEqual(
            get_mime_type(Path("a.xlsx")),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_fallback_mime(self):
        self.assertEqual(get_mime_type(Path("a.txt")), "text/plain")

    def test_unknown_mime_fallback(self):
        self.assertEqual(get_mime_type(Path("a.unknownext")), "application/octet-stream")


if __name__ == "__main__":
    unittest.main()
