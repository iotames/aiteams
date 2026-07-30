# Task: 测试与质量验证

## Description

基于后端代码和前端页面（见架构设计产出和 project/ 目录），为系统编写完整的测试用例并执行质量审查。

### 需要创建的文件

```
project/tests/
├── __init__.py
├── conftest.py              # 测试夹具（TestClient、测试数据库）
├── test_categories.py       # 分类 API 测试
├── test_products.py         # 商品 API 测试
├── test_purchases.py        # 采购 API 测试
└── test_sales.py            # 销售 API 测试
```

### 测试要求

#### conftest.py
- 使用内存 SQLite 数据库（`sqlite://`）
- 创建独立的 TestClient 实例
- 自动创建和销毁数据库表（每个测试函数）
- 预置测试数据夹具

#### 每个测试文件至少覆盖

1. **正常路径 (200)**
   - 创建资源（POST）→ 检查返回 201/200 和数据正确
   - 读取资源（GET）→ 检查返回数据和分页
   - 更新资源（PUT）→ 检查数据修改正确
   - 删除资源（DELETE）→ 检查返回 204 和确认删除

2. **异常路径**
   - 无效输入（如空名称、负价格）→ 检查返回 422
   - 资源不存在 → 检查返回 404
   - 删除已被引用的资源 → 检查返回 409

3. **业务规则**
   - 采购入库后库存量增加
   - 销售出库后库存量减少
   - 库存不足时销售应返回错误

### 质量审查

检查以下问题并写入 `output/QA_REPORT.md`：
- 后端代码中未处理的异常路径
- 缺少输入验证的 API 端点
- 前端页面中未对接的 API
- 代码规范问题

## Expected Output

- `project/tests/` 目录下的 pytest 测试文件
- `output/QA_REPORT.md` 质量审查报告

## 自检要求（输出前请确认）

1. 测试文件是否覆盖所有 API 端点的正常和异常路径
2. 每个测试用例是否相互独立、可重复运行
3. QA 报告中的 BUG 是否标注了位置和严重级别
4. 测试数据库是否使用内存 SQLite
