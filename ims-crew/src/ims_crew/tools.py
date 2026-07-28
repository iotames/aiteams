"""
自定义工具 — 为 Agent 提供代码质量验证和 API 设计检查能力。

参考: CrewAI-Agentic-SWE-Team 的工具设计模式。
"""

import ast
import re
from pathlib import Path
from typing import Any


class CodeQualityChecker:
    """代码质量检查工具 — 验证生成的 Python 代码是否符合基本规范。"""

    @staticmethod
    def check_python_syntax(file_path: str | Path) -> dict[str, Any]:
        """检查 Python 文件语法是否正确。

        Args:
            file_path: .py 文件路径

        Returns:
            {"valid": bool, "error": str | None, "line": int | None}
        """
        path = Path(file_path)
        if not path.exists():
            return {"valid": False, "error": "文件不存在", "line": None}
        if path.suffix != ".py":
            return {"valid": True, "error": None, "line": None}

        try:
            ast.parse(path.read_text(encoding="utf-8"))
            return {"valid": True, "error": None, "line": None}
        except SyntaxError as e:
            return {"valid": False, "error": str(e.msg), "line": e.lineno}

    @staticmethod
    def check_imports(file_path: str | Path) -> list[str]:
        """检查 import 语句是否使用了不推荐的内置库。

        Returns:
            问题列表，空列表表示无问题
        """
        path = Path(file_path)
        if not path.exists():
            return ["文件不存在"]

        issues = []
        content = path.read_text(encoding="utf-8")
        # 不推荐在 requirements.txt 中出现的内置库
        builtins = {"os", "sys", "re", "json", "math", "datetime", "pathlib"}
        std_imports = re.findall(r"^import (\w+)", content, re.MULTILINE)
        # 也匹配 from X import Y
        std_from_imports = re.findall(r"^from (\w+) import", content, re.MULTILINE)

        for imp in std_imports + std_from_imports:
            if imp in builtins:
                issues.append(f"文件 {path.name} 导入了内置库 '{imp}'，不需要加入 requirements.txt")

        return issues

    @staticmethod
    def check_all(project_dir: str | Path) -> dict[str, Any]:
        """对项目目录中的所有 Python 文件执行完整检查。

        Returns:
            {file_path: {"syntax": ..., "imports": [...]}}
        """
        results = {}
        for py_file in Path(project_dir).rglob("*.py"):
            syntax = CodeQualityChecker.check_python_syntax(py_file)
            imports = CodeQualityChecker.check_imports(py_file)
            if not syntax["valid"] or imports:
                results[str(py_file.relative_to(project_dir.parent))] = {
                    "syntax": syntax,
                    "imports": imports,
                }
        return results


class APIDesignValidator:
    """API 设计验证工具 — 检查 RESTful API 设计规范。"""

    # 常见 RESTful 资源名（复数形式）
    VALID_RESOURCES = {
        "categories", "products", "purchases", "purchase_items",
        "sales", "sale_items", "inventory_logs", "reports",
    }

    @classmethod
    def validate_route(cls, method: str, path: str) -> list[str]:
        """验证单个路由是否符合 RESTful 约定。

        Args:
            method: HTTP 方法（GET, POST, PUT, DELETE）
            path: API 路径

        Returns:
            问题列表
        """
        issues = []
        path_lower = path.lower()

        # 检查是否以 /api/ 开头
        if not path_lower.startswith("/api/"):
            issues.append(f"路径 '{path}' 应以 /api/ 前缀开头")

        # 检查是否包含有效的资源名称
        has_valid_resource = any(
            resource in path_lower for resource in cls.VALID_RESOURCES
        )
        if not has_valid_resource:
            issues.append(f"路径 '{path}' 未包含有效的资源名")

        return issues

    @classmethod
    def validate_all_routes(cls, router_files: list[str]) -> dict[str, list[str]]:
        """验证多个路由文件中的所有路由。

        注意：实际使用时需要配合 AST 解析提取 @router.get/post/put/delete 装饰器。

        Returns:
            {路径: [问题列表]}
        """
        # 简化版本：检查文件内容中的路由定义
        results: dict[str, list[str]] = {}
        http_methods = ["get", "post", "put", "delete", "patch"]

        for file_path in router_files:
            path = Path(file_path)
            if not path.exists():
                continue

            content = path.read_text(encoding="utf-8")
            for method in http_methods:
                pattern = rf'@router\.{method}\s*\(\s*["\']([^"\']+)["\']'
                for match in re.finditer(pattern, content, re.IGNORECASE):
                    route_path = match.group(1)
                    issues = cls.validate_route(method.upper(), route_path)
                    if issues:
                        results[f"{path.name}:{method.upper()} {route_path}"] = issues

        return results
