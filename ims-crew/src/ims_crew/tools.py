"""
自定义工具 — 为 Agent 提供代码质量验证、API 设计检查和测试执行能力。

参考: CrewAI-Agentic-SWE-Team 的工具设计模式。
"""

import ast
import re
import subprocess
import sys
from pathlib import Path

from crewai.tools import BaseTool


# =============================================================
# 工具函数
# =============================================================

class CheckPythonSyntaxTool(BaseTool):
    """检查 Python 文件语法是否正确。"""

    name: str = "Check Python Syntax"
    description: str = "检查一个 Python 文件的语法是否正确，返回语法检查结果。"

    def _run(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            return f"错误：文件不存在: {file_path}"
        if path.suffix != ".py":
            return f"跳过非 Python 文件: {file_path}"

        try:
            ast.parse(path.read_text(encoding="utf-8"))
            return f"✅ {file_path} 语法检查通过"
        except SyntaxError as e:
            return f"❌ {file_path} 语法错误 (行 {e.lineno}): {e.msg}"


class CheckImportsTool(BaseTool):
    """检查 import 语句是否使用了不推荐的内置库。"""

    name: str = "Check Imports"
    description: str = "检查一个 Python 文件的 import 语句，找出不应出现在 requirements.txt 中的内置库。"

    def _run(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            return f"文件不存在: {file_path}"

        content = path.read_text(encoding="utf-8")
        builtins = {"os", "sys", "re", "json", "math", "datetime", "pathlib"}
        issues = []

        for match in re.finditer(r"^import (\w+)", content, re.MULTILINE):
            if match.group(1) in builtins:
                issues.append(f"'{match.group(1)}' 是内置库，不需要加入 requirements.txt")
        for match in re.finditer(r"^from (\w+) import", content, re.MULTILINE):
            if match.group(1) in builtins:
                issues.append(f"'{match.group(1)}' 是内置库，不需要加入 requirements.txt")

        if not issues:
            return f"✅ {file_path} import 检查通过"
        return f"⚠️ {file_path}:\n" + "\n".join(f"  - {i}" for i in issues)


class RunPytestTool(BaseTool):
    """运行 pytest 测试并返回测试结果。"""

    name: str = "Run Pytest"
    description: str = "在指定目录运行 pytest 测试，返回测试执行结果（PASS/FAIL 详情）。"

    def _run(self, test_dir: str = "project/tests", verbose: str = "True") -> str:
        target = Path(test_dir)
        if not target.exists():
            return f"错误：测试目录不存在: {test_dir}"

        cmd = [sys.executable, "-m", "pytest", str(target)]
        if verbose.lower() in ("true", "1", "yes"):
            cmd.append("-v")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            output = result.stdout + "\n" + result.stderr
            # 截断过长输出
            if len(output) > 4000:
                output = output[:4000] + "\n... (输出已截断)"
            return output
        except subprocess.TimeoutExpired:
            return "错误：测试执行超时（120 秒）"
        except FileNotFoundError:
            return "错误：pytest 未安装，请运行 pip install pytest"
        except Exception as e:
            return f"错误：执行测试时发生异常: {e}"


class CodeQualityCheckAllTool(BaseTool):
    """对项目目录中所有 Python 文件执行完整质量检查。"""

    name: str = "Code Quality Check All"
    description: str = "对 project/backend 目录中所有 Python 文件执行语法和 import 检查，返回完整的检查报告。"

    def _run(self, project_dir: str = "project") -> str:
        base = Path(project_dir)
        if not base.exists():
            return f"错误：目录不存在: {project_dir}"

        results = []
        for py_file in sorted(base.rglob("*.py")):
            try:
                ast.parse(py_file.read_text(encoding="utf-8"))
            except SyntaxError as e:
                results.append(f"❌ {py_file} 语法错误 (行 {e.lineno}): {e.msg}")

        if not results:
            return f"✅ 所有 Python 文件语法检查通过（共 {len(list(base.rglob('*.py')))} 个文件）"
        return "\n".join(results)


class ValidateAPIRoutesTool(BaseTool):
    """验证 API 路由是否符合 RESTful 设计规范。"""

    name: str = "Validate API Routes"
    description: str = "检查 FastAPI router 文件中的路由是否符合 RESTful 规范（/api/ 前缀、资源命名等）。"

    def _run(self, router_dir: str = "project/backend/routers") -> str:
        base = Path(router_dir)
        if not base.exists():
            return f"错误：目录不存在: {router_dir}"

        issues = []
        for py_file in sorted(base.rglob("*.py")):
            content = py_file.read_text(encoding="utf-8")
            for method in ["get", "post", "put", "delete", "patch"]:
                for match in re.finditer(
                    rf'@router\.{method}\s*\(\s*["\']([^"\']+)["\']',
                    content, re.IGNORECASE,
                ):
                    route = match.group(1).lower()
                    if not route.startswith("/api/"):
                        issues.append(f"{py_file.name}: {method.upper()} {route} — 缺少 /api/ 前缀")

        if not issues:
            return f"✅ 所有路由符合规范（{len(list(base.rglob('*.py')))} 个文件）"
        return "\n".join(issues)


# =============================================================
# 工具注册
# =============================================================

# 按用途分组的工具列表
BACKEND_TOOLS = [
    CheckPythonSyntaxTool(),
    CheckImportsTool(),
    CodeQualityCheckAllTool(),
    ValidateAPIRoutesTool(),
]

QA_TOOLS = [
    RunPytestTool(),
    CheckPythonSyntaxTool(),
    CodeQualityCheckAllTool(),
]
