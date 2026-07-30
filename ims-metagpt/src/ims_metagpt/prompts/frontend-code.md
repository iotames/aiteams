## 技术要求
- 使用 Bootstrap 5 CDN 样式
- 使用 Font Awesome 5 CDN 图标
- JWT Token 存储在 localStorage
- 所有 API 调用使用 fetch API

## 输出格式
每个文件之间用 `---` 分隔：

```
文件路径: frontend/index.html
---
<!DOCTYPE html>
...
---
文件路径: frontend/js/api.js
---
...
---
```

## 必须生成的文件

### 1. frontend/index.html
登录页面：用户名/密码表单，JWT 认证后跳转首页

### 2. frontend/dashboard.html
仪表盘首页：卡片式布局，显示库存概况、今日销售、低库存预警等

### 3. frontend/products.html
商品管理页：商品列表表格 + 新增/编辑模态框 + 搜索筛选 + 分页

### 4. frontend/categories.html
分类管理页：树形分类展示 + 增删改

### 5. frontend/orders.html
订单管理页：采购单/销售单列表，Tab 切换，详情查看

### 6. frontend/order_create.html
新建订单页：选择商品、填写数量、计算金额

### 7. frontend/customers.html
客户/供应商管理页：列表 + 表单

### 8. frontend/reports.html
报表统计页：图表展示（使用 Chart.js CDN）

### 9. frontend/js/api.js
通用 API 调用模块：
- BASE_URL 配置
- get() / post() / put() / delete() 封装
- 自动附加 JWT Token
- 错误处理

### 10. frontend/js/auth.js
认证模块：登录、登出、Token 管理、路由守卫

### 11. frontend/css/style.css
自定义样式：侧边栏、卡片、表格、按钮主题色

## 输入
**架构设计**: {design}

请输出前端代码：
