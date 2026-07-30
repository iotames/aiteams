# Task: QA 重新测试

## Description

在 BUG 修复完成后，重新运行全部测试用例，确认修复有效。

### 处理流程

1. 运行 `pytest project/tests/ -v` 确认所有测试通过
2. 更新 `output/QA_REPORT.md`，标记已修复的 BUG 状态
3. 如果有新增 BUG，一并记录

### 输出要求

更新后的 QA 报告（`output/QA_REPORT.md`），包含：
- 重新测试的 PASS/FAIL 结果
- 已修复 BUG 列表（标记为 FIXED）
- 遗留 BUG 列表（如果有）

## Expected Output

更新后的测试结果和 QA 报告。

## 自检要求（输出前请确认）

1. 是否已重新评估所有测试用例的执行结果
2. 已修复 BUG 是否已标记为 FIXED
3. 新增 BUG 是否已记录到报告中
