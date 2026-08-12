**Git提交前强制自查步骤**（每次 commit 前必须执行）：
1. 提交Git之前，用 `git status`, `git diff --stat`, `git diff` 等命令，对待提交的代码进行没有上下文意图污染的独立窗口审核，有问题直接阻止。
2. 检查 message 全文，只包含必要的变更描述和用户许可的内容，不能包含 `Co-Authored`、`Assisted-by`、`Crush`、`Generated` 等多余署名（用户指定的格式除外）。
3. Git提交不能包含隐私文件，编译后的文件（除非用户同意），文件绝对不能有隐私数据。
