# Task: BUG 修复（前端）

## Description

基于 QA 测试报告（`output/QA_REPORT.md`），修复前端代码中发现的 BUG。

### 处理流程

1. 读取 QA 测试报告，提取前端相关的 BUG
2. 定位问题代码（`project/frontend/`）
3. 逐个修复 BUG
4. 如果 QA 报告为空或无 BUG，直接跳过

### 修复要求

- 不要引入新功能，只修复报告中列出的 BUG
- 保持代码风格一致

## Expected Output

修复后的前端代码（`project/frontend/`）。

## 自检要求（输出前请确认）

1. 所有 BUG 是否已逐个修复
2. 修复是否只针对报告中列出的问题，未引入新功能
3. 修复后代码风格是否与原有一致
