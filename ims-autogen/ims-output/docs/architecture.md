# 进销存管理系统（IMS）架构设计文档

> 版本：v1.0 MVP | 作者：Bob | 日期：2025-01-21
> 技术栈：Python Flask + SQLite + Web Components + Bootstrap 5

---

## 一、技术栈选型及理由

### 1.1 总体技术栈

| 层级 | 技术选型 | 版本 | 选择理由 |
|------|---------|------|---------|
| **后端框架** | Flask | 3.x | 轻量、成熟、CRUD 友好，适合本地单机系统 |
| **ORM** | SQLAlchemy | 2.x | Python 生态最强大的 ORM，安全防 SQL 注入 |
| **数据库** | SQLite | 最新 | 本地单文件存储，备份方便，零配置 |
| **前端 UI** | Bootstrap 5 (CDN) | 5.3.x | 专业 UI 组件，响应式，零编译 |
| **前端组件** | Web Components (原生) | - | 浏览器原生标准，零编译，高可扩展 |
| **模板引擎** | Jinja2 (Flask 内置) | - | 仅用于页面加载，API 通信全用 JSON |

### 1.2 架构原则

```
标准原生架构：技术栈无关，遵循行业标准，回归原生标准
├── 前端：HTML + CSS + JavaScript（零编译，直接运行）
├── 通信：RESTful JSON API（标准 HTTP 协议）
├── 组件：Web Components（浏览器原生标准）
└── 数据库：SQLite（标准 SQL，文件即数据库）
```

---

## 二、系统架构总览

### 2.1 三层架构

```
┌──────────────────────────────────────────────────────────┐
│                   浏览器（前端）                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │  SPA 应用（Hash 路由）                             │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │  │
│  │  │ 页面视图  │ │ Web      │ │ Bootstrap 5     │   │  │
│  │  │ (Page     │ │ Components│ │ (表格/表单/导航) │   │  │
│  │  │  组件)    │ │ (业务组件)│ │                  │   │  │
│  │  └──────────┘ └──────────┘ └──────────────────┘   │  │
│  │  ┌────────────────────────────────────────────────┐ │  │
│  │  │  API Client（fetch 封装，统一错误处理）        │ │  │
│  │  └────────────────────────────────────────────────┘ │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────┬───────────────────────────────────┘
                       │ RESTful JSON API (HTTP)
                       ▼
┌──────────────────────────────────────────────────────────┐
│                 Flask 后端服务器                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │  路由层 (Blueprints)                               │  │
│  │  /api/products  /api/purchase  /api/sale  /api/... │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────┐  │
│  │  服务层 (Services)                                 │  │
│  │  ProductService  PurchaseService  SaleService     │  │
│  │  StockService    ReportService                     │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────┐  │
│  │  数据层 (Models + SQLAlchemy)                      │  │
│  │  SQLite 数据库文件 (ims.db)                        │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────┐  │
│  │  API 错误处理中间件                                │  │
│  │  全局异常捕获、统一 JSON 响应格式                   │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

### 2.2 模块划分

```
ims/
├── backend/                       # 后端 Python 代码
│   ├── app.py                     # Flask 应用入口 & 配置
│   ├── models/                    # 数据模型
│   │   ├── __init__.py
│   │   ├── product.py             # 商品、分类、单位
│   │   ├── supplier.py            # 供应商
│   │   ├── customer.py            # 客户
│   │   ├── purchase.py            # 采购订单及明细
│   │   ├── sale.py                # 销售订单及明细
│   │   └── stock.py               # 库存流水
│   ├── routes/                    # API 路由（蓝图）
│   │   ├── __init__.py
│   │   ├── product_routes.py      # 商品/分类/单位 CRUD
│   │   ├── supplier_routes.py     # 供应商 CRUD
│   │   ├── customer_routes.py     # 客户 CRUD
│   │   ├── purchase_routes.py     # 采购订单 & 入库确认
│   │   ├── sale_routes.py         # 销售订单 & 出库确认
│   │   ├── stock_routes.py        # 库存查询 & 流水
│   │   └── report_routes.py       # 报表统计（P1）
│   ├── services/                  # 业务逻辑层
│   │   ├── __init__.py
│   │   ├── product_service.py
│   │   ├── purchase_service.py
│   │   ├── sale_service.py
│   │   ├── stock_service.py       # 核心：库存变更引擎
│   │   └── report_service.py
│   └── utils/                     # 工具函数
│       ├── __init__.py
│       ├── response.py            # 统一 JSON 响应格式
│       └── validators.py          # 请求参数校验
│
├── frontend/                      # 前端静态文件（零编译）
│   ├── index.html                 # SPA 入口（Hash 路由容器）
│   ├── css/
│   │   └── app.css                # 自定义样式
│   ├── js/
│   │   ├── app.js                 # 路由引擎 & 应用初始化
│   │   ├── api.js                 # API Client 封装
│   │   ├── router.js              # Hash 路由管理器
│   │   ├── components/            # Web Components
│   │   │   ├── ims-table.js       # 通用数据表格组件
│   │   │   ├── ims-form.js        # 通用表单组件
│   │   │   ├── ims-modal.js       # 模态框组件
│   │   │   ├── ims-nav.js         # 侧边导航组件
│   │   │   └── ims-toast.js       # 通知提示组件
│   │   └── pages/                 # 页面组件
│   │       ├── dashboard.js       # 首页仪表盘
│   │       ├── product-list.js    # 商品列表页
│   │       ├── product-form.js    # 商品表单页（新增/编辑）
│   │       ├── category-list.js   # 分类管理页
│   │       ├── unit-list.js       # 单位管理页
│   │       ├── supplier-list.js   # 供应商列表页
│   │       ├── supplier-form.js   # 供应商表单页
│   │       ├── customer-list.js   # 客户列表页
│   │       ├── customer-form.js   # 客户表单页
│   │       ├── purchase-list.js   # 采购订单列表页
│   │       ├── purchase-form.js   # 采购订单表单页
│   │       ├── sale-list.js       # 销售订单列表页
│   │       ├── sale-form.js       # 销售订单表单页
│   │       ├── stock-list.js      # 库存查询页
│   │       ├── stock-flow.js      # 库存流水页
│   │       ├── report-summary.js  # 进销存汇总报表
│   │       └── report-sales.js    # 销售明细报表
│   └── static/                    # 其他静态资源
│       └── favicon.ico
│
├── start.py                       # 启动脚本（检测依赖 + 启动服务 + 打开浏览器）
├── start.bat                      # Windows 双击启动
├── start.sh                       # Mac/Linux 启动
├── requirements.txt               # Python 依赖
└── docs/                          # 文档
    ├── prd.md
    └── architecture.md
```

---

## 三、数据库设计（ER 描述）

### 3.1 完整表结构

```
┌─────────────────────────────────────────────────────────────────┐
│                         category (分类)                          │
├─────────────────────────────────────────────────────────────────┤
│ id          INTEGER  PRIMARY KEY AUTOINCREMENT                  │
│ name        VARCHAR(50)  NOT NULL  UNIQUE        # 分类名称      │
│ parent_id   INTEGER  DEFAULT NULL  → category.id  # 父分类      │
│ created_at  DATETIME  DEFAULT CURRENT_TIMESTAMP                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                          unit (单位)                             │
├─────────────────────────────────────────────────────────────────┤
│ id          INTEGER  PRIMARY KEY AUTOINCREMENT                  │
│ name        VARCHAR(20)  NOT NULL  UNIQUE        # 单位名称      │
│ created_at  DATETIME  DEFAULT CURRENT_TIMESTAMP                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                        product (商品)                            │
├─────────────────────────────────────────────────────────────────┤
│ id              INTEGER  PRIMARY KEY AUTOINCREMENT              │
│ name            VARCHAR(100)  NOT NULL           # 商品名称      │
│ code            VARCHAR(50)   NOT NULL  UNIQUE    # 商品编码      │
│ category_id     INTEGER  NOT NULL  → category.id  # 所属分类     │
│ unit_id         INTEGER  NOT NULL  → unit.id      # 计量单位     │
│ purchase_price  DECIMAL(10,2)  DEFAULT 0          # 采购进价      │
│ sale_price      DECIMAL(10,2)  DEFAULT 0          # 销售售价      │
│ stock_low       DECIMAL(10,2)  DEFAULT 0          # 库存下限      │
│ current_stock   DECIMAL(10,2)  DEFAULT 0          # 当前库存(缓    │
│                  ★★★ 缓存字段，由流水驱动更新 ★★★     │
│ created_at      DATETIME  DEFAULT CURRENT_TIMESTAMP              │
│ updated_at      DATETIME  DEFAULT CURRENT_TIMESTAMP              │
│ created_by      VARCHAR(50)  DEFAULT NULL         # 预留扩展      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                       supplier (供应商)                          │
├─────────────────────────────────────────────────────────────────┤
│ id          INTEGER  PRIMARY KEY AUTOINCREMENT                  │
│ name        VARCHAR(100)  NOT NULL                # 供应商名称    │
│ contact     VARCHAR(50)                           # 联系人        │
│ phone       VARCHAR(30)                           # 联系电话      │
│ address     TEXT                                  # 地址          │
│ created_at  DATETIME  DEFAULT CURRENT_TIMESTAMP                  │
│ created_by  VARCHAR(50)  DEFAULT NULL             # 预留扩展      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                       customer (客户)                            │
├─────────────────────────────────────────────────────────────────┤
│ id          INTEGER  PRIMARY KEY AUTOINCREMENT                  │
│ name        VARCHAR(100)  NOT NULL                # 客户名称      │
│ contact     VARCHAR(50)                           # 联系人        │
│ phone       VARCHAR(30)                           # 联系电话      │
│ address     TEXT                                  # 地址          │
│ created_at  DATETIME  DEFAULT CURRENT_TIMESTAMP                  │
│ created_by  VARCHAR(50)  DEFAULT NULL             # 预留扩展      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    purchase_order (采购订单)                      │
├─────────────────────────────────────────────────────────────────┤
│ id              INTEGER  PRIMARY KEY AUTOINCREMENT              │
│ order_no        VARCHAR(50)  NOT NULL  UNIQUE     # 订单编号      │
│ supplier_id     INTEGER  NOT NULL  → supplier.id   # 供应商      │
│ status          VARCHAR(20)  NOT NULL  DEFAULT '待入库'          │
│                 # 枚举：待入库 / 部分入库 / 已完成 / 已取消       │
│ total_amount    DECIMAL(12,2)  DEFAULT 0          # 订单总金额    │
│ remark          TEXT                               # 备注          │
│ created_at      DATETIME  DEFAULT CURRENT_TIMESTAMP              │
│ updated_at      DATETIME  DEFAULT CURRENT_TIMESTAMP              │
│ created_by      VARCHAR(50)  DEFAULT NULL         # 预留扩展      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                  purchase_order_item (采购明细)                   │
├─────────────────────────────────────────────────────────────────┤
│ id               INTEGER  PRIMARY KEY AUTOINCREMENT             │
│ order_id         INTEGER  NOT NULL  → purchase_order.id         │
│ product_id       INTEGER  NOT NULL  → product.id                │
│ quantity         DECIMAL(10,2)  NOT NULL          # 订购数量      │
│ received_quantity DECIMAL(10,2)  DEFAULT 0         # 已入库数量    │
│ unit_price       DECIMAL(10,2)  NOT NULL          # 单价          │
│ subtotal         DECIMAL(12,2)  DEFAULT 0          # 小计          │
│ ★ 约束: received_quantity ≤ quantity ★                           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      sale_order (销售订单)                        │
├─────────────────────────────────────────────────────────────────┤
│ id              INTEGER  PRIMARY KEY AUTOINCREMENT              │
│ order_no        VARCHAR(50)  NOT NULL  UNIQUE     # 订单编号      │
│ customer_id     INTEGER  NOT NULL  → customer.id   # 客户        │
│ status          VARCHAR(20)  NOT NULL  DEFAULT '待出库'          │
│                 # 枚举：待出库 / 部分出库 / 已完成 / 已取消       │
│ total_amount    DECIMAL(12,2)  DEFAULT 0          # 订单总金额    │
│ remark          TEXT                               # 备注          │
│ created_at      DATETIME  DEFAULT CURRENT_TIMESTAMP              │
│ updated_at      DATETIME  DEFAULT CURRENT_TIMESTAMP              │
│ created_by      VARCHAR(50)  DEFAULT NULL         # 预留扩展      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    sale_order_item (销售明细)                     │
├─────────────────────────────────────────────────────────────────┤
│ id               INTEGER  PRIMARY KEY AUTOINCREMENT             │
│ order_id         INTEGER  NOT NULL  → sale_order.id             │
│ product_id       INTEGER  NOT NULL  → product.id                │
│ quantity         DECIMAL(10,2)  NOT NULL          # 订购数量      │
│ shipped_quantity  DECIMAL(10,2)  DEFAULT 0         # 已出库数量    │
│ unit_price       DECIMAL(10,2)  NOT NULL          # 单价          │
│ subtotal         DECIMAL(12,2)  DEFAULT 0          # 小计          │
│ ★ 约束: shipped_quantity ≤ quantity ★                            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                   stock_transaction (库存流水)                    │
├─────────────────────────────────────────────────────────────────┤
│ id               INTEGER  PRIMARY KEY AUTOINCREMENT             │
│ product_id       INTEGER  NOT NULL  → product.id                │
│ type             VARCHAR(20)  NOT NULL            # 类型          │
│                  # 枚举：采购入库 / 销售出库 / 入库冲正 / 出库冲正 │
│ quantity_change  DECIMAL(10,2)  NOT NULL          # 变更数量      │
│                  # 入库为正(+)，出库为负(-)                      │
│ reference_type   VARCHAR(30)  NOT NULL            # 来源单据类型   │
│                  # purchase_order / sale_order                   │
│ reference_id     INTEGER  NOT NULL                # 来源单据ID     │
│ reference_item_id INTEGER  NOT NULL               # 来源明细ID     │
│ stock_before     DECIMAL(10,2)  NOT NULL          # 变更前库存     │
│ stock_after      DECIMAL(10,2)  NOT NULL          # 变更后库存     │
│ remark           VARCHAR(200)                     # 备注          │
│ created_at       DATETIME  DEFAULT CURRENT_TIMESTAMP             │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 关键约束总结

```
1. 库存一致性：
   product.current_stock = SUM(采购入库) - SUM(销售出库)
   ★ 每次业务操作同时更新 current_stock 和插入流水

2. 入库约束：
   purchase_order_item.received_quantity ≤ purchase_order_item.quantity

3. 出库约束：
   sale_order_item.shipped_quantity ≤ sale_order_item.quantity
   软约束：出库时校验库存，不足则提示但允许继续

4. 唯一约束：
   product.code 唯一
   purchase_order.order_no 唯一
   sale_order.order_no 唯一
   category.name 唯一
   unit.name 唯一
```

---

## 四、API 路由设计

### 4.1 统一规范

```
基础路径：/api/v1
响应格式：
  {
    "success": true/false,
    "data": { ... } | [ ... ],
    "message": "操作成功/错误描述",
    "total": 100           # 列表接口返回总数
  }

错误码：
  200 - 成功
  400 - 参数错误
  404 - 资源不存在
  409 - 冲突（如编码重复）
  500 - 服务器内部错误
```

### 4.2 商品管理 API

| 方法 | 路径 | 功能 | P0/P1 |
|------|------|------|-------|
| GET | `/api/v1/products` | 商品列表（分页/搜索/筛选） | P0 |
| GET | `/api/v1/products/<id>` | 商品详情 | P0 |
| POST | `/api/v1/products` | 新增商品 | P0 |
| PUT | `/api/v1/products/<id>` | 编辑商品 | P0 |
| DELETE | `/api/v1/products/<id>` | 删除商品（有业务引用则拒绝） | P0 |
| GET | `/api/v1/categories` | 分类列表 | P0 |
| POST | `/api/v1/categories` | 新增分类 | P0 |
| PUT | `/api/v1/categories/<id>` | 编辑分类 | P0 |
| DELETE | `/api/v1/categories/<id>` | 删除分类（有关联商品则拒绝） | P0 |
| GET | `/api/v1/units` | 单位列表 | P0 |
| POST | `/api/v1/units` | 新增单位 | P0 |
| PUT | `/api/v1/units/<id>` | 编辑单位 | P0 |
| DELETE | `/api/v1/units/<id>` | 删除单位（有关联商品则拒绝） | P0 |

### 4.3 供应商/客户 API

| 方法 | 路径 | 功能 | P0/P1 |
|------|------|------|-------|
| GET | `/api/v1/suppliers` | 供应商列表 | P0 |
| GET | `/api/v1/suppliers/<id>` | 供应商详情 | P0 |
| POST | `/api/v1/suppliers` | 新增供应商 | P0 |
| PUT | `/api/v1/suppliers/<id>` | 编辑供应商 | P0 |
| DELETE | `/api/v1/suppliers/<id>` | 删除供应商 | P0 |
| GET | `/api/v1/customers` | 客户列表（同上模式） | P0 |
| ... | ... | 客户 CRUD | P0 |

### 4.4 采购管理 API

| 方法 | 路径 | 功能 | P0/P1 |
|------|------|------|-------|
| GET | `/api/v1/purchase-orders` | 采购订单列表（分页/筛选） | P0 |
| GET | `/api/v1/purchase-orders/<id>` | 采购订单详情（含明细） | P0 |
| POST | `/api/v1/purchase-orders` | 创建采购订单 | P0 |
| PUT | `/api/v1/purchase-orders/<id>` | 编辑采购订单（仅待入库可编辑） | P0 |
| DELETE | `/api/v1/purchase-orders/<id>` | 删除采购订单（仅待入库可删除） | P0 |
| POST | `/api/v1/purchase-orders/<id>/receive` | 入库确认（核心操作） | P0 |
| POST | `/api/v1/purchase-orders/<id>/cancel` | 取消订单 | P0 |

### 4.5 销售管理 API

| 方法 | 路径 | 功能 | P0/P1 |
|------|------|------|-------|
| GET | `/api/v1/sale-orders` | 销售订单列表 | P0 |
| GET | `/api/v1/sale-orders/<id>` | 销售订单详情 | P0 |
| POST | `/api/v1/sale-orders` | 创建销售订单 | P0 |
| PUT | `/api/v1/sale-orders/<id>` | 编辑销售订单（仅待出库可编辑） | P0 |
| DELETE | `/api/v1/sale-orders/<id>` | 删除销售订单（仅待出库可删除） | P0 |
| POST | `/api/v1/sale-orders/<id>/ship` | 出库确认（核心操作） | P0 |
| POST | `/api/v1/sale-orders/<id>/cancel` | 取消订单 | P0 |

### 4.6 库存管理 API

| 方法 | 路径 | 功能 | P0/P1 |
|------|------|------|-------|
| GET | `/api/v1/stock` | 库存列表（含低库存标记） | P0 |
| GET | `/api/v1/stock/<product_id>` | 单个商品库存详情 | P0 |
| GET | `/api/v1/stock/transactions` | 库存流水列表（分页/筛选） | P0 |
| GET | `/api/v1/stock/low-stock` | 低库存商品列表 | P0 |

### 4.7 报表 API（P1）

| 方法 | 路径 | 功能 | P0/P1 |
|------|------|------|-------|
| GET | `/api/v1/reports/summary` | 进销存汇总报表（按时间段） | P1 |
| GET | `/api/v1/reports/sales-detail` | 销售明细报表（按时间段） | P1 |

---

## 五、前端组件架构

### 5.1 Hash 路由设计

```
#/dashboard              → 仪表盘（首页）
#/products               → 商品列表
#/products/new           → 新增商品
#/products/:id/edit      → 编辑商品
#/categories             → 分类管理
#/units                  → 单位管理
#/suppliers              → 供应商列表
#/suppliers/new          → 新增供应商
#/suppliers/:id/edit     → 编辑供应商
#/customers              → 客户列表
#/customers/new          → 新增客户
#/customers/:id/edit     → 编辑客户
#/purchase-orders        → 采购订单列表
#/purchase-orders/new    → 新建采购订单
#/purchase-orders/:id    → 采购订单详情
#/sale-orders            → 销售订单列表
#/sale-orders/new        → 新建销售订单
#/sale-orders/:id        → 销售订单详情
#/stock                  → 库存查询
#/stock/transactions     → 库存流水
#/reports/summary        → 进销存汇总报表
#/reports/sales          → 销售明细报表
```

### 5.2 Web Components 组件树

```
<ims-app>                          # 根应用组件
├── <ims-nav>                      # 侧边导航栏（菜单高亮）
│   ├── 仪表盘
│   ├── 商品管理 → 商品 / 分类 / 单位
│   ├── 采购管理 → 采购订单
│   ├── 销售管理 → 销售订单
│   ├── 库存管理 → 库存查询 / 库存流水
│   └── 报表统计 → 汇总报表 / 销售明细
├── <router-view>                  # 路由视图容器
│   └── (根据 Hash 动态挂载页面组件)
│       ├── <page-dashboard>       # 仪表盘页面
│       ├── <page-product-list>    # 商品列表页
│       ├── <page-product-form>    # 商品表单页
│       ├── <page-category-list>   # 分类管理页
│       ├── <page-unit-list>       # 单位管理页
│       ├── <page-supplier-list>   # 供应商列表页
│       ├── <page-supplier-form>   # 供应商表单页
│       ├── <page-customer-list>   # 客户列表页
│       ├── <page-customer-form>   # 客户表单页
│       ├── <page-purchase-list>   # 采购订单列表页
│       ├── <page-purchase-form>   # 采购订单表单页
│       ├── <page-sale-list>       # 销售订单列表页
│       ├── <page-sale-form>       # 销售订单表单页
│       ├── <page-stock-list>      # 库存查询页
│       ├── <page-stock-flow>      # 库存流水页
│       ├── <page-report-summary>  # 汇总报表页
│       └── <page-report-sales>    # 销售明细报表页
└── <ims-toast>                    # 全局通知提示
```

### 5.3 通用业务组件

```
<ims-table>                        # 通用数据表格
  Props: columns, data, actions, loading
  功能：排序、分页、操作按钮、空状态

<ims-form>                         # 通用表单
  Props: fields, values, rules
  功能：表单验证、提交、重置

<ims-modal>                        # 模态对话框
  Props: title, size, closable
  功能：确认弹窗、表单弹窗

<ims-toast>                        # 消息通知
  Props: type (success/error/warning/info)
  功能：自动消失、堆叠显示
```

---

## 六、核心数据流向

### 6.1 采购入库流程（核心链路）

```
用户操作                             系统处理
─────────                          ────────
1. 填写采购订单表单                  前端校验必填项
   ↓                                ↓
2. POST /api/v1/purchase-orders    后端：校验供应商存在、商品存在
   ↓                                ↓         创建订单 + 明细
   ↓                                ↓         状态 → 待入库
   ↓                                ← 返回订单详情
3. 查看采购订单列表/详情              
   ↓                                
4. 发起入库确认                      
   ↓                                
5. POST /purchase-orders/:id/receive 
   ↓                                
   backend:                         
   ├── 校验：订单状态为待入库/部分入库
   ├── 更新 purchase_order_item.received_quantity
   ├── 更新 purchase_order.status
   │   ├── 全部入库 → 已完成
   │   └── 部分入库 → 部分入库
   ├── 更新 product.current_stock += 入库数量
   ├── 创建 stock_transaction 记录（type=采购入库）
   └── 检查低库存预警
   ← 返回成功
6. 前端刷新库存页可看到库存增加       前端：toast 提示成功
   流水页可溯源该笔入库记录
```

### 6.2 销售出库流程（核心链路）

```
用户操作                             系统处理
─────────                          ────────
1. 填写销售订单表单                  前端校验库存（软提示）
   ↓                                ↓
2. POST /api/v1/sale-orders        后端：校验客户存在、商品存在
   ↓                                ↓         校验库存是否充足
   ↓                                ↓         （不充足则 warning 但不阻止）
   ↓                                ↓         创建订单 + 明细
   ↓                                ↓         状态 → 待出库
   ↓                                ← 返回订单详情
3. 查看销售订单列表/详情              
   ↓                                
4. 发起出库确认                      
   ↓                                
5. POST /sale-orders/:id/ship       
   ↓                                
   backend:                         
   ├── 校验：订单状态为待出库/部分出库
   ├── 更新 sale_order_item.shipped_quantity
   ├── 更新 sale_order.status
   │   ├── 全部出库 → 已完成
   │   └── 部分出库 → 部分出库
   ├── 更新 product.current_stock -= 出库数量
   ├── 创建 stock_transaction 记录（type=销售出库）
   └── 检查低库存预警
   ← 返回成功
6. 前端刷新库存页可看到库存减少       前端：toast 提示成功
   流水页可溯源该笔出库记录
```

### 6.3 库存查询流程

```
GET /api/v1/stock
  └── SELECT product.id, product.name, product.code,
            product.current_stock, product.stock_low,
            category.name AS category_name, unit.name AS unit_name
      FROM product
      JOIN category ON product.category_id = category.id
      JOIN unit ON product.unit_id = unit.id
      WHERE (搜索条件)
      ORDER BY product.current_stock < product.stock_low DESC, product.name
      
  前端：
  ├── current_stock < stock_low → 行高亮（红色/黄色）
  ├── 正常库存 → 正常显示
  └── 支持按商品名称/编码搜索
```

---

## 七、库存一致性保障策略（核心设计）

### 7.1 双重保障机制

```
每次库存变更操作 → 数据库事务内完成：
┌─────────────────────────────────────┐
│  BEGIN TRANSACTION                  │
│  ├── 1. 更新明细表的 received/shipped  │
│  ├── 2. 更新订单状态                    │
│  ├── 3. 更新 product.current_stock     │
│  ├── 4. 插入 stock_transaction 记录     │
│  │     (记录变更前后的库存值，可对账)      │
│  ├── 5. 检查低库存预警                   │
│  COMMIT                               │
└─────────────────────────────────────┘

如果事务中任何一步失败 → ROLLBACK，数据回滚到变更前状态
```

### 7.2 对账脚本（可选管理工具）

```
可通过 stock_transaction 表汇总验证：
  SELECT product_id, SUM(quantity_change) 
  FROM stock_transaction 
  GROUP BY product_id
  
  结果应等于 product.current_stock
  不一致则触发告警（MVP 阶段基本不会出现）
```

---

## 八、部署与启动方案

### 8.1 环境要求

```
- Python 3.9+
- 现代浏览器（Chrome/Edge/Firefox）
- 操作系统：Windows / macOS / Linux
```

### 8.2 启动方式

**方式一：双击 start.bat（Windows 推荐）**
```batch
@echo off
echo 正在启动进销存管理系统...
pip install -r requirements.txt
python start.py
pause
```

**方式二：双击 start.sh（macOS/Linux）**
```bash
#!/bin/bash
pip install -r requirements.txt
python start.py
```

**方式三：命令行手动启动**
```bash
pip install -r requirements.txt
python start.py
```

### 8.3 start.py 功能

```python
# 1. 检测 Python 版本 ≥ 3.9
# 2. 自动安装/更新依赖 (pip install -r requirements.txt)
# 3. 初始化数据库（首次运行自动建表）
# 4. 启动 Flask 开发服务器 (默认 127.0.0.1:5000)
# 5. 自动打开浏览器访问 http://127.0.0.1:5000
```

### 8.4 requirements.txt

```
flask>=3.0.0
flask-cors>=4.0.0
sqlalchemy>=2.0.0
```

---

## 九、可扩展性设计（为 Full 版本预留）

### 9.1 数据层预留

```python
# 所有 Models 已预留 created_by 字段
# 未来扩展用户系统时，可通过外键关联用户表

# 示例：扩展后的用户模型
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20))  # admin / operator / viewer
```

### 9.2 API 层预留

```python
# 路由装饰器预留鉴权中间件
# 未来扩展时只需添加 @require_auth 装饰器

def require_auth(f):
    """鉴权装饰器（预留，MVP 阶段不做实际校验）"""
    @wraps(f)
    def decorated(*args, **kwargs):
        # MVP 阶段直接放行
        # Full 版本：校验 token → 获取当前用户 → 权限检查
        return f(*args, **kwargs)
    return decorated
```

### 9.3 前端预留

```python
# api.js 中预留 token 管理
// 未来扩展：在请求头自动附加 Authorization token
const API = {
    baseURL: '/api/v1',
    token: localStorage.getItem('ims_token'),
    
    async request(method, path, data) {
        const headers = { 'Content-Type': 'application/json' };
        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }
        // ...
    }
};
```

---

## 十、PRD 未明确事项的处理决策

| 决策点 | 我的决定 | 理由 |
|--------|---------|------|
| 订单编号生成规则 | `PO-20250121-0001`（采购） / `SO-20250121-0001`（销售） | 前缀+日期+序号的通用格式，一目了然 |
| 删除商品时若有订单引用 | 软删除（标记删除）或拒绝删除（提示被引用） | 防止数据不一致，推荐拒绝删除+提示 |
| 分页默认值 | 每页 20 条，支持 10/20/50 切换 | 常见分页大小，适合中小数据量 |
| 搜索方式 | 商品名称/编码模糊搜索，客户/供应商名称模糊搜索 | 最常用的搜索场景 |
| 入库/出库确认方式 | 全单确认（一次确认整单的全部/部分数量） | MVP 简化操作，不做分批多次确认 |

---

> **文档状态：已完成 ✅**
>
> 下一步：Eve 根据此架构设计开始编码实现。
>
> 设计原则重申：
> 1. **零编译** — 前端代码写完直接运行，无需任何构建步骤
> 2. **组件化** — 所有业务功能封装为 Web Components
> 3. **数据一致** — 库存变更必须走事务，双重保障
> 4. **可扩展** — 预留用户、权限扩展点
