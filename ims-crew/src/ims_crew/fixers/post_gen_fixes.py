"""
生成后自动修复管线 — 处理 LLM 生成代码的常见问题。

参考:
    - CrewAI-Agentic-SWE-Team post_generation_fixes.py
    - 常见问题: Pydantic v1→v2 语法、缺失依赖、CORS 配置
"""

import re
from pathlib import Path
from typing import Any


def fix_requirements(project_dir: Path) -> list[str]:
    """修复 backend/requirements.txt 的常见问题。"""
    fixes: list[str] = []
    req_file = project_dir / "backend" / "requirements.txt"

    if not req_file.exists():
        return ["❌ backend/requirements.txt 不存在"]

    content = req_file.read_text(encoding="utf-8")
    original = content

    # 移除 Python 内置库（不该出现在 requirements 中）
    content = re.sub(r"^sqlite3.*\n?", "", content, flags=re.MULTILINE)
    content = re.sub(r"^os\n?", "", content, flags=re.MULTILINE)
    content = re.sub(r"^sys\n?", "", content, flags=re.MULTILINE)
    content = re.sub(r"^re\n?", "", content, flags=re.MULTILINE)
    content = re.sub(r"^json\n?", "", content, flags=re.MULTILINE)
    content = re.sub(r"^pathlib\n?", "", content, flags=re.MULTILINE)
    content = re.sub(r"^datetime\n?", "", content, flags=re.MULTILINE)

    # 确保关键依赖存在
    required_pkgs = {
        "fastapi": "fastapi>=0.110.0\n",
        "uvicorn": "uvicorn[standard]>=0.27.0\n",
        "sqlalchemy": "sqlalchemy>=2.0.0\n",
        "pydantic": "pydantic>=2.0.0\n",
    }

    for pkg_name, line in required_pkgs.items():
        if pkg_name not in content.lower():
            content += line
            fixes.append(f"📦 添加缺失依赖: {pkg_name}")

    if content != original:
        req_file.write_text(content, encoding="utf-8")
        fixes.append("✅ requirements.txt 已修复")

    return fixes


def fix_pydantic_v2(project_dir: Path) -> list[str]:
    """修复 Pydantic v1 → v2 语法差异。"""
    fixes: list[str] = []
    for py_file in sorted(project_dir.rglob("*.py")):
        content = py_file.read_text(encoding="utf-8")
        original = content

        # orm_mode → model_config
        content = content.replace(
            "orm_mode = True",
            'model_config = {"from_attributes": True}',
        )
        content = content.replace(
            "orm_mode=True",
            'model_config={"from_attributes": True}',
        )

        # Config class → model_config（Pydantic v2）
        content = re.sub(
            r"class Config:\s*\n\s*orm_mode\s*=\s*True\s*",
            "",
            content,
        )

        if content != original:
            py_file.write_text(content, encoding="utf-8")
            fixes.append(f"🔧 Pydantic v2 语法修复: {py_file.name}")

    return fixes


def fix_cors_middleware(project_dir: Path) -> list[str]:
    """确保 backend/main.py 中配置了 CORS 中间件。"""
    fixes: list[str] = []
    main_file = project_dir / "backend" / "main.py"

    if not main_file.exists():
        return ["❌ backend/main.py 不存在，跳过 CORS 修复"]

    content = main_file.read_text(encoding="utf-8")

    if "CORSMiddleware" not in content:
        # 在 import 块后插入 CORS 导入
        if "from fastapi.middleware.cors import CORSMiddleware" not in content:
            content = content.replace(
                "from fastapi import",
                "from fastapi import\nfrom fastapi.middleware.cors import CORSMiddleware",
            )

        cors_block = """
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
"""

        # 定位 FastAPI 实例化后的插入位置
        lines = content.split("\n")
        insert_pos = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            # 找到 app = FastAPI() 所在行
            if re.match(r"^\w+\s*=\s*FastAPI\s*\(.*\)", stripped):
                insert_pos = i + 2  # app 创建后空一行插入
                break
            # 回退：找装饰器行（第一个 @app.xxx）
            if re.match(r"^@\w+\.", stripped):
                insert_pos = i
                break

        if insert_pos is not None and insert_pos < len(lines):
            lines.insert(insert_pos, cors_block)
            content = "\n".join(lines)
            fixes.append("🔧 添加 CORS 中间件配置")

        main_file.write_text(content, encoding="utf-8")

    return fixes


def fix_database_url(project_dir: Path) -> list[str]:
    """确保 database.py 使用环境变量配置数据库 URL。"""
    fixes: list[str] = []
    db_file = project_dir / "backend" / "database.py"

    if not db_file.exists():
        return ["❌ backend/database.py 不存在，跳过数据库 URL 修复"]

    content = db_file.read_text(encoding="utf-8")

    if "DATABASE_URL" not in content and "os.getenv" not in content:
        # 添加环境变量读取
        if "import os" not in content:
            content = "import os\n" + content

        # 替换硬编码的数据库 URL
        content = re.sub(
            r'sqlite:///.*\.db',
            'os.getenv("DATABASE_URL", "sqlite:///./ims.db")',
            content,
        )
        fixes.append("🔧 数据库 URL 改为环境变量配置")

        db_file.write_text(content, encoding="utf-8")

    return fixes


def run_all_fixes(project_dir: Path) -> dict[str, Any]:
    """执行所有自动修复管线。"""
    return {
        "requirements": fix_requirements(project_dir),
        "pydantic_v2": fix_pydantic_v2(project_dir),
        "cors": fix_cors_middleware(project_dir),
        "database_url": fix_database_url(project_dir),
    }
