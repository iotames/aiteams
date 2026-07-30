# Task: 系统架构设计

## Description

基于前序的 PRD 文档（见前序产出），设计系统的完整技术架构。

### 技术栈约束

- **后端**: Python FastAPI + SQLAlchemy 2.0 + SQLite（开发环境）/ PostgreSQL（生产）
- **前端**: 纯 HTML/CSS/JavaScript + Bootstrap 5（通过 CDN 加载，无需构建工具）
- **API 风格**: RESTful JSON API，统一 `/api/v1/` 前缀
- **ORM 迁移**: SQLAlchemy 自动建表（`Base.metadata.create_all`）

### 输出要求

请输出以下设计文档，写入文件 `output/ARCHITECTURE.md`：

#### 1. 技术选型说明
- 各技术组件的选择理由
- 版本要求

#### 2. 数据库 ER 设计
- 所有表的字段名、数据类型、约束、默认值、索引
- 表之间的关系（外键、级联策略）

**必须包含的表**:
| 表名 | 说明 | 关键字段 |
|------|------|---------|
| `categories` | 商品分类 | id, name, description, created_at |
| `products` | 商品 | id, name, sku, category_id, price, cost, stock_qty, min_stock, unit, created_at, updated_at |
| `purchases` | 采购单 | id, supplier, order_date, status, total_amount, note, created_at |
| `purchase_items` | 采购明细 | id, purchase_id, product_id, quantity, unit_price, subtotal |
| `sales` | 销售单 | id, customer, order_date, status, total_amount, note, created_at |
| `sale_items` | 销售明细 | id, sale_id, product_id, quantity, unit_price, subtotal |
| `inventory_logs` | 库存流水 | id, product_id, change_type, quantity, balance_after, reference_id, reference_type, note, created_at |

#### 3. API 接口列表
每个接口包含：
- HTTP 方法 + 路径
- 请求参数（query/path/body）
- 请求体 JSON Schema
- 成功响应体 JSON Schema
- 错误响应体 JSON Schema
- 权限要求

另外，将上述 API 定义输出为 **标准 OpenAPI 3.0 YAML**，写入 `output/openapi.yaml`。
这个文件是前后端的共同契约：后端按此实现，前端按此对接。
必须包含所有端点的完整请求/响应结构，不能省略任何字段。

#### 4. 前端页面设计
- 页面列表与路由映射
- 每个页面的组件规划
- 导航结构

#### 5. 项目目录结构

另外，将 SQLAlchemy 模型定义写入 `output/models.py`（可执行的 Python 文件）。

## Expected Output

架构文档 `output/ARCHITECTURE.md`、OpenAPI 规范 `output/openapi.yaml`、数据库模型 `output/models.py`。
文档必须完整精确，开发者可据此直接编码，无需反向猜测设计意图。

## 自检要求（输出前请确认）

1. 数据库 ER 设计是否覆盖所有表、字段、类型、约束、索引
2. API 接口定义是否包含路径、方法、请求体、响应体、错误码
3. OpenAPI 规范是否与 API 列表完全一致
4. 前端页面列表是否完整覆盖所有功能模块
