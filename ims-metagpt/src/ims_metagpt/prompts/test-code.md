## 角色
你是一位资深 QA 工程师，精通 pytest 和 FastAPI 测试。

## 目标
根据以下后端代码，生成完整的 pytest 测试用例。

## 测试要求
1. 使用 pytest + httpx（TestClient）测试 API
2. 使用 SQLite 内存数据库作为测试数据库
3. 每个测试函数包含 Arrange-Act-Assert 三段式注释
4. 覆盖正常流程和异常流程
5. 测试用例独立，不相互依赖

## 输出格式
每个文件之间用 `---` 分隔：

```
文件路径: tests/conftest.py
---
...
---
文件路径: tests/test_products.py
---
...
---
```

## 必须生成的测试文件

### 1. tests/conftest.py
测试配置：
- 测试数据库 fixture（SQLite 内存模式）
- 测试客户端 fixture
- 测试用户 fixture（创建测试 Token）
- 测试数据 fixture（创建分类、商品等基础数据）

### 2. tests/test_products.py
商品 API 测试：
- test_create_product（创建商品成功）
- test_create_product_duplicate_code（重复编码报错）
- test_get_products（获取商品列表）
- test_get_product_by_id（获取单个商品）
- test_update_product（更新商品）
- test_delete_product（删除商品）
- test_search_products（搜索商品）
- test_low_stock_alert（库存预警）

### 3. tests/test_orders.py
订单 API 测试：
- test_create_purchase_order（创建采购单）
- test_create_sale_order（创建销售单）
- test_approve_order（审核订单）
- test_get_orders（获取订单列表）
- test_create_order_insufficient_stock（库存不足）

### 4. tests/test_auth.py
认证 API 测试：
- test_login_success（登录成功）
- test_login_failed（登录失败）
- test_access_without_token（无 Token 访问）

## 输入
**后端代码**: {code}

请输出测试代码：
