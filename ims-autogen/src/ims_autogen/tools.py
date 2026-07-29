"""工具函数：Agent 在工作流中使用的工具。"""

import os
import subprocess
from pathlib import Path
from typing import Optional


def _workspace() -> Path:
    """获取当前工作区路径（从环境变量或默认值）。"""
    return Path(os.getenv("IMS_WORKSPACE", "./ims-output")).absolute()


async def save_file(path: str, content: str) -> str:
    """
    保存文件到工作区。

    Args:
        path: 相对于工作区的文件路径，如 "backend/models.py"
        content: 文件内容

    Returns:
        保存确认信息
    """
    full_path = _workspace() / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")
    return f"✅ 已保存: {path} ({len(content)} 字符)"


async def read_file(path: str) -> str:
    """
    读取工作区中的文件内容。

    Args:
        path: 相对于工作区的文件路径

    Returns:
        文件内容，不存在则返回错误信息
    """
    full_path = _workspace() / path
    if not full_path.exists():
        return f"❌ 文件不存在: {path}"
    return full_path.read_text(encoding="utf-8")


async def list_files(pattern: str = "**/*") -> str:
    """
    列出工作区中的文件。

    Args:
        pattern: 通配符模式，如 "backend/**/*.py"

    Returns:
        文件列表
    """
    base = _workspace()
    files = [str(f.relative_to(base)) for f in sorted(base.rglob(pattern)) if f.is_file()]
    if not files:
        return "（工作区为空）"
    return "\n".join(files)


async def run_command(command: str, timeout: int = 60) -> str:
    """
    在工作区目录下执行 shell 命令。

    Args:
        command: 要执行的命令
        timeout: 超时秒数

    Returns:
        命令输出
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(_workspace()),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        if result.returncode != 0:
            return f"⚠️ 退出码 {result.returncode}\n{output[:3000]}"
        return output[:3000] or "（命令执行成功，无输出）"
    except subprocess.TimeoutExpired:
        return f"⏰ 命令执行超时（{timeout}秒）"
    except Exception as e:
        return f"❌ 命令执行失败: {e}"
