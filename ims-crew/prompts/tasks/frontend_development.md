# Task: 前端管理后台开发

## Description

基于架构设计文档（见前序产出）和 OpenAPI 规范（`output/openapi.yaml`），实现完整的管理后台前端页面。

所有 API 请求的 URL、请求体、响应解析必须严格遵循 `output/openapi.yaml` 中定义的接口规范。

### 技术限制
- 纯 HTML/CSS/JavaScript（不使用 React/Vue 等框架）
- 通过 CDN 加载 Bootstrap 5、Bootstrap Icons、Chart.js
- 使用原生 `fetch` API 与后端通信

### 需要创建的文件

```
project/frontend/
├── index.html               # 仪表盘/登录首页
├── products.html            # 商品管理
├── categories.html          # 分类管理
├── purchases.html           # 采购管理
├── sales.html               # 销售管理
├── inventory.html           # 库存管理
├── reports.html             # 报表统计
└── shared/
    ├── style.css            # 公共样式
    └── api.js               # API 调用封装模块
```

### 各页面要求

#### 仪表盘 (index.html)
- 统计卡片：商品总数、本月采购额、本月销售额、低库存商品数
- 最近交易动态列表

#### 商品管理 (products.html)
- 商品列表表格（含搜索、分页）
- 新增/编辑商品表单（模态框）
- 删除确认
- 显示库存数量和低库存标记

#### 分类管理 (categories.html)
- 分类列表
- 新增/编辑/删除分类

#### 采购管理 (purchases.html)
- 采购单列表
- 创建采购单（可选择商品、填写数量和单价）
- 入库操作（确认入库 → 更新库存）
- 采购单详情查看

#### 销售管理 (sales.html)
- 销售单列表
- 创建销售单（可选择商品、填写数量和售价）
- 出库操作（确认出库 → 扣减库存）
- 销售单详情查看

#### 库存管理 (inventory.html)
- 库存状态列表（商品、库存量、预警状态）
- 库存流水记录

#### 报表统计 (reports.html)
- 各类统计图表（使用 Chart.js）

### 公共模块 (shared/)

#### api.js
- 封装 `get`, `post`, `put`, `delete` 方法
- 统一错误处理和提示
- API 基础 URL 配置
- 请求/响应拦截

#### style.css
- 全局样式
- 打印样式优化
- 响应式调整

### 开发规范
- 统一导航栏（包含所有功能入口）
- 每个操作都有 Toast 提示反馈
- 表单提交前做前端验证
- 删除操作需要二次确认
- 表格支持按列排序

## Expected Output

完整的后台管理前端项目，所有文件保存在 `project/frontend/` 目录下。
用浏览器直接打开 `frontend/index.html` 即可使用（需要后端同时运行）。

## 自检要求（输出前请确认）

1. 所有 HTML 文件是否已创建并包含完整内容
2. 每个页面是否有对应的导航入口
3. API 调用是否与 `output/openapi.yaml` 的接口路径一致
4. 表单提交是否有前端验证
5. 删除操作是否有二次确认弹窗
