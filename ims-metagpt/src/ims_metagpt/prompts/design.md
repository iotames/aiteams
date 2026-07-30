## 生成范围
当前范围为：{scope}
- 当 scope="mvp" 时：只设计核心功能模块（商品管理 + 基础库存管理），数据结构简洁
- 当 scope="full" 时：设计完整的全功能架构

## 技术栈要求
- **后端**: Python FastAPI + SQLAlchemy ORM + SQLite（开发）/ PostgreSQL（生产）
- **前端**: 原生 HTML + CSS + JavaScript（使用 Bootstrap 5 样式，无需构建工具）
- **API 风格**: RESTful JSON API
- **认证**: JWT Token
- **文档**: Swagger (FastAPI 自动生成)

## 输出格式要求
请严格按照以下 Markdown 模板输出：

### 1. 技术栈总览
列出所有使用的技术及版本。

### 2. 数据库 ER 设计
```
表名: 字段名 (类型, 约束) [备注]
```
列出所有数据表，包含字段、类型、外键关系。

### 3. API 路由设计
```
[HTTP方法] /api/{path} — 功能描述
  - 请求参数: ...
  - 响应格式: ...
```

### 4. 前端组件设计
```
页面路由: /
  - 组件列表: ...
页面路由: /products
  - 组件列表: ...
```

### 5. 目录结构
```
backend/
frontend/
```

### 6. 关键接口规格
列出每个核心 API 的请求/响应示例（JSON）。

## 输入
**PRD**: {prd}

请输出系统架构设计文档（注意遵循当前范围 {scope} 的限制）：
