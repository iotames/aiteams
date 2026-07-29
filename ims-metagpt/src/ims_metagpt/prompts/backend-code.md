## 角色
你是一位资深 Python 后端工程师，精通 FastAPI 和 SQLAlchemy。

## 目标
根据以下系统架构设计，生成完整的后端代码。

## 代码质量要求
1. 每个文件包含完整的 import 和类型注解
2. 遵循 PEP 8 编码规范
3. 包含错误处理和输入验证
4. 代码可直接运行，无语法错误
5. 每个 API 端点包含 docstring

## 输出格式
请按以下格式输出每个文件，文件之间用 `---` 分隔：

```
文件路径: backend/app/main.py
---
from fastapi import FastAPI
...
---
文件路径: backend/app/models.py
---
...
---
文件路径: backend/app/schemas.py
---
...
---
文件路径: backend/app/routes/products.py
---
...
---
```

## 必须生成的文件清单

### 1. backend/requirements.txt
FastAPI, uvicorn, SQLAlchemy, python-jose[cryptography], passlib[bcrypt], python-multipart

### 2. backend/app/main.py
FastAPI 应用入口，包含：
- 应用创建与配置
- CORS 中间件
- 路由注册
- 启动事件（创建数据库表）

### 3. backend/app/database.py
数据库配置：
- SQLAlchemy engine & session
- Base declarative base
- 数据库 URL 配置（支持 SQLite 开发 / PostgreSQL 生产）

### 4. backend/app/models.py
SQLAlchemy 模型：
- 商品分类 (Category): id, name, parent_id, sort_order, created_at
- 商品 (Product): id, name, code, category_id, spec, unit, purchase_price, sale_price, stock_quantity, alert_threshold, description, image_url, created_at, updated_at
- 客户 (Customer): id, name, contact, phone, address, created_at
- 供应商 (Supplier): id, name, contact, phone, address, created_at
- 采购单 (PurchaseOrder): id, order_no, supplier_id, total_amount, status, created_at, updated_at
- 采购明细 (PurchaseOrderItem): id, order_id, product_id, quantity, unit_price, subtotal
- 销售单 (SaleOrder): id, order_no, customer_id, total_amount, status, created_at, updated_at
- 销售明细 (SaleOrderItem): id, order_id, product_id, quantity, unit_price, subtotal
- 库存变动 (StockMovement): id, product_id, type(in/out), quantity, reference_type, reference_id, remark, created_at
- 用户 (User): id, username, password_hash, role, created_at

### 5. backend/app/schemas.py
Pydantic 模型：所有实体的请求/响应 Schema

### 6. backend/app/auth.py
JWT 认证：create_access_token, verify_token, get_current_user

### 7. backend/app/routes/products.py
商品 API：CRUD + 搜索 + 分类筛选 + 库存预警查询

### 8. backend/app/routes/orders.py
采购单/销售单 API：创建、审核、查询、统计

### 9. backend/app/routes/customers.py
客户 API：CRUD

### 10. backend/app/routes/dashboard.py
仪表盘 API：库存概况、销售趋势、预警汇总

### 11. backend/run.py
启动脚本：uvicorn main:app --reload

## 输入
**架构设计**: {design}

请输出后端代码：
