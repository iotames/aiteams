## 语言偏好

1. **使用简体中文**：所有回答、注释、文档、commit message 必须使用中文。代码标识符保持工程化英文惯例。
2. **简洁明确**：回答必须务实、简洁、精准。不扩展未询问的内容。
3. **交互式对话确认**：先问再做，优先使用交互式对话，明确用户需求。

## 记忆文件（上下文注入文件）

1. **简明扼要**：写入新记忆条目时，文字精简可落地，去掉不可执行的解释。元数据只保留 `type`，不记录会话 ID。
2. **禁止重复**：写入新记忆条目前，先读一遍现有内容，存在语义重复则改/合/跳过，不盲目追加。

## 工作流规则

1. **提交须经确认**: 用户没明确说"提交/commit"，绝不执行 git 写入操作。
2. **文档同步**：修改代码后同步更新相关 .md 文档（README.md、CLAUDE.md、USAGE.md 等）。
3. **先问再写**：任务存在歧义时，先提问澄清再执行。复杂任务先出方案，认可后实施。

**Git提交前强制自查步骤**（每次 commit 前必须执行）：
1. 提交Git之前，用 `git status`, `git diff --stat`, `git diff` 对全部待提交的代码进行没有上下文目标意图污染的独立窗口审核，有问题直接阻止。
2. 检查 message 全文，不能包含 `Co-Authored`、`Assisted-by`、`Crush`、`Generated` 等多余署名（用户指定的格式除外）
3. 确认 message 只包含必要的变更描述和用户许可的内容

## 命令行规则

1. 禁止用 npx 探测本地软件，要用 `where` 或 `cmd /c` 查。

## 中国大陆网络环境与网络资源获取

- 用户位于中国大陆境内，境外网络资源连接不稳定或可能被阻断（如 developers.openai.com 等境外站点可能 403/不可达）。
- **优先用国内镜像**：获取依赖、文档、资源时优先使用国内镜像（npm/cargo/pip/go/GitHub 等），只有国内镜像报错后才切换国际中心仓库。
- 确需外网时，先询问用户是否有可用网络代理（如 127.0.0.1:7897），不要反复盲目重试境外直连。

## Windows Markdown 转 PDF 流程

1. Python `markdown` 库转 HTML → Edge headless 打印为 PDF。不要用 npm/puppeteer/weasyprint/pandoc（此机器 npm 有 EBUSY 问题，weasyprint 缺 GTK 系统库）。
2. Edge 参数必带 `--print-to-pdf-no-header --no-margins` 以禁止默认页头页脚（时间戳、文件路径）。
3. 隐私要求：转换后用 pypdf 剥离元数据（`writer.metadata = None`），页头页脚绝不能包含时间、文件路径等隐私信息。页头仅保留文件名，页脚仅保留页码。
4. CSS 限制须知：`@page` margin boxes 不生效，`position: fixed` 被 Edge headless 剥离。页头/页脚需用独立 Edge 实例逐页生成（`position: absolute` + mm 坐标定位），再用 pypdf `merge_page(over=True)` 合并。
5. fpdf2 与 pypdf 合并时 TrueType 字体会触发 `MERG NOT subset` 警告，导致水印文字丢失。改用 Edge 生成水印页可避免此问题。
6. 用 Python `subprocess` 调 Edge 时，路径为 `C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe`，HTML 路径需转换为 `file:///` URL。

## 子 Agent 工作透明

派发子 Agent / 并行任务时，禁止让用户面对黑箱等待：

- 派发前：用一句话说明派给谁、做什么、预计耗时。
- 工作中：持续汇报进度，两次状态更新间隔不超过 60 秒；汇报具体进展（当前阶段、已完成的文件或步骤、有无阻塞），不用"正在处理"式空话。
- 长等待期间：wait_agent 等长时间等待要穿插状态更新，而不是静默等待到超时。
- 结束后：立即给出结果摘要，再继续后续步骤。

## 记忆作用范围判断

新增记忆时，先判断其作用范围：

- 只适用于当前项目的 → 写入项目级 AGENTS.md（仓库根目录）。
- 跨项目/全局的 → 写入全局
- 不得擅自只写入局部；不确定时向用户确认范围。

