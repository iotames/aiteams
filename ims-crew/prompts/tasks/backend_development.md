# Task: 后端 API 开发

## Description

基于架构设计文档（`{architecture_content}`）和数据库模型（`{models_content}`），实现完整的后端 API 代码。

### 需要创建的文件结构

```
project/backend/
├── __init__.py
├── main.py                  # FastAPI 应用入口
├── database.py              # 数据库引擎和会话
├── models.py                # SQLAlchemy 模型
├── schemas.py               # Pydantic 请求/响应模型
├── routers/
│   ├── __init__.py
│   ├── categories.py        # 分类 CRUD
│   ├── products.py          # 商品 CRUD
│   ├── purchases.py         # 采购管理
│   ├── sales.py             # 销售管理
│   └── reports.py           # 统计报表
└── requirements.txt         # Python 依赖
```

### 各文件要求

#### main.py
- FastAPI 应用实例
- CORS 中间件配置（允许前端所有来源）
- 注册所有路由
- 应用启动事件（创建数据库表）
- 全局异常处理器

#### database.py
- SQLAlchemy 2.0 声明式基类
- 数据库 URL 从环境变量读取（`DATABASE_URL`，默认 `sqlite:///./ims.db`）
- 会话工厂（SessionLocal）
- `get_db` 依赖注入函数

#### models.py
- 完整的 SQLAlchemy 模型实现
- 包含所有表和关系
- 使用 `Mapped` / `mapped_column` 类型注解语法（SQLAlchemy 2.0）

#### schemas.py
- Pydantic v2 模型
- 创建请求（Create）、更新请求（Update）、响应（Response）、列表查询参数
- 配置 `from_attributes = True`

#### routers 各文件
- RESTful CRUD 端点
- 输入验证和错误处理
- 统一的响应格式
- 分页支持（`skip`/`limit` 参数）
- 搜索/过滤支持（按名称、日期范围等）

#### requirements.txt
- fastapi, uvicorn, sqlalchemy, pydantic 等必须依赖
- 标记版本号

### 质量要求
- 所有代码使用 Python 3.11+ 类型注解
- 每个 API 端点都有 422 输入验证和 404 资源不存在的错误处理
- 遵循 RESTful 资源命名规范
- 数据库操作用事务包裹

## Expected Output

完整的后端 FastAPI 项目，所有文件保存在 `project/backend/` 目录下。
代码应该可以直接通过 `uvicorn backend.main:app` 运行。
