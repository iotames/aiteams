# Git 推送重试规则

- **多远程必须全部成功**：分布式仓库配了多个 remote（如 github / githost / nas / gitlab），push 命令输出显示某个 remote 收到 ≠ 全部成功；必须逐个 remote 确认（`git remote -v` 对照 push 输出或 `git ls-remote` 核实），有一个失败即视为推送未完成。
- **失败自动重试**：网络不稳导致 push 经常失败。推送失败时每分钟重试 1 次 `git push`，直至所有远程库推送成功，不要失败一次就报告了事。
- Why：多 remote 场景部分成功很常见且易被忽略；推漏会导致各远程仓库版本不一致。
