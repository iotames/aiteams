#!/usr/bin/env python3
"""生成并托管评测结果审查页面。

读取工作区目录，发现运行目录（含 outputs/ 的目录），
把所有输出数据嵌入到一个自包含的 HTML 页面中，并通过一个微型 HTTP
服务器托管。反馈会自动保存到工作区的 feedback.json。

用法：
    python generate_review.py <workspace-path> [--port PORT] [--skill-name NAME]
    python generate_review.py <workspace-path> --previous-feedback /path/to/old/feedback.json

仅依赖 Python 标准库。
"""

import argparse
import base64
import io
import json
import mimetypes
import os
import re
import signal
import subprocess
import sys
import time
import webbrowser
from functools import partial
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path


def ensure_utf8_stdio() -> None:
    """把 stdout/stderr 重配置为 UTF-8，避免非 ASCII 输出在 Windows
    控制台（GBK）或其他依赖语言环境的终端上崩溃。

    从 scripts.utils 复制而来，使 eval-viewer 可以独立运行
    （它没有包初始化文件，不能依赖 scripts 包）。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError, io.UnsupportedOperation):
            pass

# 输出列表中要排除的文件
METADATA_FILES = {"transcript.md", "user_notes.md", "metrics.json"}

# 以内联文本渲染的扩展名
TEXT_EXTENSIONS = {
    ".txt", ".md", ".json", ".csv", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".yaml", ".yml", ".xml", ".html", ".css", ".sh", ".rb", ".go", ".rs",
    ".java", ".c", ".cpp", ".h", ".hpp", ".sql", ".r", ".toml",
}

# 以内联图片渲染的扩展名
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}

# 常见类型的 MIME 覆盖
MIME_OVERRIDES = {
    ".svg": "image/svg+xml",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def get_mime_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in MIME_OVERRIDES:
        return MIME_OVERRIDES[ext]
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


def find_runs(workspace: Path) -> list[dict]:
    """递归查找所有包含 outputs/ 子目录的目录。"""
    runs: list[dict] = []
    _find_runs_recursive(workspace, workspace, runs)
    runs.sort(key=lambda r: (r.get("eval_id", float("inf")), r["id"]))
    return runs


def _find_runs_recursive(root: Path, current: Path, runs: list[dict]) -> None:
    if not current.is_dir():
        return

    outputs_dir = current / "outputs"
    if outputs_dir.is_dir():
        run = build_run(root, current)
        if run:
            runs.append(run)
        return

    skip = {"node_modules", ".git", "__pycache__", "skill", "inputs"}
    for child in sorted(current.iterdir()):
        if child.is_dir() and child.name not in skip:
            _find_runs_recursive(root, child, runs)


def build_run(root: Path, run_dir: Path) -> dict | None:
    """构建包含 prompt、输出和评分数据的运行字典。"""
    prompt = ""
    eval_id = None

    # 先尝试 eval_metadata.json
    for candidate in [run_dir / "eval_metadata.json", run_dir.parent / "eval_metadata.json"]:
        if candidate.exists():
            try:
                metadata = json.loads(candidate.read_text(encoding="utf-8"))
                prompt = metadata.get("prompt", "")
                eval_id = metadata.get("eval_id")
            except (json.JSONDecodeError, OSError):
                pass
            if prompt:
                break

    # 回退到 transcript.md
    if not prompt:
        for candidate in [run_dir / "transcript.md", run_dir / "outputs" / "transcript.md"]:
            if candidate.exists():
                try:
                    text = candidate.read_text(encoding="utf-8")
                    match = re.search(r"## Eval Prompt\n\n([\s\S]*?)(?=\n##|$)", text)
                    if match:
                        prompt = match.group(1).strip()
                except OSError:
                    pass
                if prompt:
                    break

    if not prompt:
        prompt = "（未找到 prompt）"

    run_id = str(run_dir.relative_to(root)).replace("/", "-").replace("\\", "-")

    # 收集输出文件
    outputs_dir = run_dir / "outputs"
    output_files: list[dict] = []
    if outputs_dir.is_dir():
        for f in sorted(outputs_dir.iterdir()):
            if f.is_file() and f.name not in METADATA_FILES:
                output_files.append(embed_file(f))

    # 加载评分（如存在）
    grading = None
    for candidate in [run_dir / "grading.json", run_dir.parent / "grading.json"]:
        if candidate.exists():
            try:
                grading = json.loads(candidate.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
            if grading:
                break

    return {
        "id": run_id,
        "prompt": prompt,
        "eval_id": eval_id,
        "outputs": output_files,
        "grading": grading,
    }


def embed_file(path: Path) -> dict:
    """读取文件并返回内嵌表示。"""
    ext = path.suffix.lower()
    mime = get_mime_type(path)

    if ext in TEXT_EXTENSIONS:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return {"name": path.name, "type": "error", "content": "（读取文件出错）"}
        return {
            "name": path.name,
            "type": "text",
            "content": content,
        }
    elif ext in IMAGE_EXTENSIONS:
        try:
            raw = path.read_bytes()
            b64 = base64.b64encode(raw).decode("ascii")
        except OSError:
            return {"name": path.name, "type": "error", "content": "（读取文件出错）"}
        return {
            "name": path.name,
            "type": "image",
            "mime": mime,
            "data_uri": f"data:{mime};base64,{b64}",
        }
    elif ext == ".pdf":
        try:
            raw = path.read_bytes()
            b64 = base64.b64encode(raw).decode("ascii")
        except OSError:
            return {"name": path.name, "type": "error", "content": "（读取文件出错）"}
        return {
            "name": path.name,
            "type": "pdf",
            "data_uri": f"data:{mime};base64,{b64}",
        }
    elif ext == ".xlsx":
        try:
            raw = path.read_bytes()
            b64 = base64.b64encode(raw).decode("ascii")
        except OSError:
            return {"name": path.name, "type": "error", "content": "（读取文件出错）"}
        return {
            "name": path.name,
            "type": "xlsx",
            "data_b64": b64,
        }
    else:
        # 二进制 / 未知 —— base64 下载链接
        try:
            raw = path.read_bytes()
            b64 = base64.b64encode(raw).decode("ascii")
        except OSError:
            return {"name": path.name, "type": "error", "content": "（读取文件出错）"}
        return {
            "name": path.name,
            "type": "binary",
            "mime": mime,
            "data_uri": f"data:{mime};base64,{b64}",
        }


def load_previous_iteration(workspace: Path) -> dict[str, dict]:
    """加载上一轮迭代的反馈和输出。

    返回 run_id -> {"feedback": str, "outputs": list[dict]} 的映射。
    """
    result: dict[str, dict] = {}

    # 加载反馈
    feedback_map: dict[str, str] = {}
    feedback_path = workspace / "feedback.json"
    if feedback_path.exists():
        try:
            data = json.loads(feedback_path.read_text(encoding="utf-8"))
            feedback_map = {
                r["run_id"]: r["feedback"]
                for r in data.get("reviews", [])
                if r.get("feedback", "").strip()
            }
        except (json.JSONDecodeError, OSError, KeyError):
            pass

    # 加载运行（用于获取输出）
    prev_runs = find_runs(workspace)
    for run in prev_runs:
        result[run["id"]] = {
            "feedback": feedback_map.get(run["id"], ""),
            "outputs": run.get("outputs", []),
        }

    # 同时为有反馈但没有匹配运行的 run_id 补充反馈
    for run_id, fb in feedback_map.items():
        if run_id not in result:
            result[run_id] = {"feedback": fb, "outputs": []}

    return result


def generate_html(
    runs: list[dict],
    skill_name: str,
    previous: dict[str, dict] | None = None,
    benchmark: dict | None = None,
) -> str:
    """生成完整的内嵌数据自包含 HTML 页面。"""
    template_path = Path(__file__).parent / "viewer.html"
    template = template_path.read_text(encoding="utf-8")

    # 为模板构建 previous_feedback 和 previous_outputs 映射
    previous_feedback: dict[str, str] = {}
    previous_outputs: dict[str, list[dict]] = {}
    if previous:
        for run_id, data in previous.items():
            if data.get("feedback"):
                previous_feedback[run_id] = data["feedback"]
            if data.get("outputs"):
                previous_outputs[run_id] = data["outputs"]

    embedded = {
        "skill_name": skill_name,
        "runs": runs,
        "previous_feedback": previous_feedback,
        "previous_outputs": previous_outputs,
    }
    if benchmark:
        embedded["benchmark"] = benchmark

    data_json = json.dumps(embedded, ensure_ascii=False)

    return template.replace("/*__EMBEDDED_DATA__*/", f"const EMBEDDED_DATA = {data_json};")


# ---------------------------------------------------------------------------
# HTTP 服务器（仅标准库，零依赖）
# ---------------------------------------------------------------------------

def _kill_port(port: int) -> None:
    """终止监听指定端口的任何进程。"""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True, timeout=5,
        )
        for pid_str in result.stdout.strip().split("\n"):
            if pid_str.strip():
                try:
                    os.kill(int(pid_str.strip()), signal.SIGTERM)
                except (ProcessLookupError, ValueError):
                    pass
        if result.stdout.strip():
            time.sleep(0.5)
    except subprocess.TimeoutExpired:
        pass
    except FileNotFoundError:
        print("提示：未找到 lsof，无法检查端口是否被占用", file=sys.stderr)

class ReviewHandler(BaseHTTPRequestHandler):
    """托管审查 HTML 并处理反馈保存。

    每次页面加载时重新生成 HTML，使浏览器刷新即可看到新的评测输出，
    无需重启服务器。
    """

    def __init__(
        self,
        workspace: Path,
        skill_name: str,
        feedback_path: Path,
        previous: dict[str, dict],
        benchmark_path: Path | None,
        *args,
        **kwargs,
    ):
        self.workspace = workspace
        self.skill_name = skill_name
        self.feedback_path = feedback_path
        self.previous = previous
        self.benchmark_path = benchmark_path
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/index.html":
            # 每次请求都重新生成 HTML（重新扫描工作区的新输出）
            runs = find_runs(self.workspace)
            benchmark = None
            if self.benchmark_path and self.benchmark_path.exists():
                try:
                    benchmark = json.loads(self.benchmark_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    pass
            html = generate_html(runs, self.skill_name, self.previous, benchmark)
            content = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == "/api/feedback":
            data = b"{}"
            if self.feedback_path.exists():
                data = self.feedback_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if self.path == "/api/feedback":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                if not isinstance(data, dict) or "reviews" not in data:
                    raise ValueError("预期包含 'reviews' 键的 JSON 对象")
                self.feedback_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                resp = b'{"ok":true}'
                self.send_response(200)
            except (json.JSONDecodeError, OSError, ValueError) as e:
                resp = json.dumps({"error": str(e)}).encode()
                self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
        else:
            self.send_error(404)

    def log_message(self, format: str, *args: object) -> None:
        # 抑制请求日志，保持终端干净
        pass


def main() -> None:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="生成并托管评测审查页面")
    parser.add_argument("workspace", type=Path, help="工作区目录路径")
    parser.add_argument("--port", "-p", type=int, default=3117, help="服务器端口（默认：3117）")
    parser.add_argument("--skill-name", "-n", type=str, default=None, help="页头显示的技能名称")
    parser.add_argument(
        "--previous-workspace", type=Path, default=None,
        help="上一轮迭代的工作区路径（显示旧输出和反馈作为上下文）",
    )
    parser.add_argument(
        "--benchmark", type=Path, default=None,
        help="要显示在 Benchmark 标签页的 benchmark.json 路径",
    )
    parser.add_argument(
        "--static", "-s", type=Path, default=None,
        help="把独立 HTML 写入此路径而不是启动服务器",
    )
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    if not workspace.is_dir():
        print(f"错误：{workspace} 不是目录", file=sys.stderr)
        sys.exit(1)

    runs = find_runs(workspace)
    if not runs:
        print(f"在 {workspace} 中未找到运行", file=sys.stderr)
        sys.exit(1)

    skill_name = args.skill_name or workspace.name.replace("-workspace", "")
    feedback_path = workspace / "feedback.json"

    previous: dict[str, dict] = {}
    if args.previous_workspace:
        previous = load_previous_iteration(args.previous_workspace.resolve())

    benchmark_path = args.benchmark.resolve() if args.benchmark else None
    benchmark = None
    if benchmark_path and benchmark_path.exists():
        try:
            benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    if args.static:
        html = generate_html(runs, skill_name, previous, benchmark)
        args.static.parent.mkdir(parents=True, exist_ok=True)
        args.static.write_text(html, encoding="utf-8")
        print(f"\n  静态查看器已写入：{args.static}\n")
        sys.exit(0)

    # 终止目标端口上的任何已有进程
    port = args.port
    _kill_port(port)
    handler = partial(ReviewHandler, workspace, skill_name, feedback_path, previous, benchmark_path)
    try:
        server = HTTPServer(("127.0.0.1", port), handler)
    except OSError:
        # 终止尝试后端口仍被占用 —— 找一个空闲端口
        server = HTTPServer(("127.0.0.1", 0), handler)
        port = server.server_address[1]

    url = f"http://localhost:{port}"
    print(f"\n  评测查看器")
    print(f"  {'-' * 33}")
    print(f"  地址：      {url}")
    print(f"  工作区：    {workspace}")
    print(f"  反馈文件：  {feedback_path}")
    if previous:
        print(f"  上一轮：    {args.previous_workspace}（{len(previous)} 个运行）")
    if benchmark_path:
        print(f"  基准数据：  {benchmark_path}")
    print(f"\n  按 Ctrl+C 停止。\n")

    webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
        server.server_close()


if __name__ == "__main__":
    main()
