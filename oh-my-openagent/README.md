# Oh My OpenAgent (OmO) — Agent 角色原始 Prompt 提取

## 说明

本目录从 [oh-my-openagent](https://github.com/code-yeongyu/oh-my-openagent) 源码中提取了 11 个预定义 Agent 角色的原始 system prompt。

## 提取信息

- **仓库**: https://github.com/code-yeongyu/oh-my-openagent
- **分支**: `dev` (commit: `51c737d15`, 版本 4.19.3, as of 2026-07-31)
- **提取方式**: 从 TypeScript 源码中的字符串常量 / Markdown prompt 文件直接复制
- **语言**: 保留原始英文，未翻译未压缩
- **许可证**: SUL-1.0 (上游仓库)

## 角色清单

| # | Agent | 角色 | 类型 | 数据源 |
|---|-------|------|------|--------|
| 1 | **Sisyphus** | 主协调者/全能开发 | 核心 Agent | `packages/omo-opencode/src/agents/sisyphus/claude-fable-5.ts` + 共享 `dynamic-agent-*.ts` |
| 2 | **Prometheus** | 战略规划师 | 核心 Agent | `packages/prompts-core/prompts/prometheus/default.md` |
| 3 | **Atlas** | 待办任务管理/工作流编排 | 核心 Agent | `packages/prompts-core/prompts/atlas/default.md` |
| 4 | **Hephaestus** | 深度自主工作者 | 专业 Agent | `packages/omo-opencode/src/agents/hephaestus/gpt.ts` |
| 5 | **Oracle** | 架构顾问/调试专家 | 专业 Agent | `packages/omo-opencode/src/agents/oracle.ts` |
| 6 | **Momus** | 计划审查员 | 专业 Agent | `packages/omo-opencode/src/agents/momus.ts` |
| 7 | **Metis** | 预规划顾问 | 专业 Agent | `packages/omo-opencode/src/agents/metis.ts` |
| 8 | **Explore** | 代码库快速搜索 | 工具型 Agent | `packages/omo-opencode/src/agents/explore.ts` |
| 9 | **Librarian** | 文档/代码检索 | 工具型 Agent | `packages/omo-opencode/src/agents/librarian.ts` |
| 10 | **Multimodal Looker** | 截图/视觉分析 | 工具型 Agent | `packages/omo-opencode/src/agents/multimodal-looker.ts` |
| 11 | **Sisyphus-Junior** | 轻量执行器 | 工具型 Agent | `packages/omo-opencode/src/agents/sisyphus-junior/default.ts` |

- `Sisyphus`: 总指挥。主协调者。 你说话，它边想边做（交互式全权入口）
- `Atlas`: 编排官。流程编排。计划已定，它照计划批处理干到全部通过（只编排不写码）
- `Hephaestus`: 执行工程师。深度自主工作者。领一个具体任务，自主探索后干到底（深度执行者）

## 升级流程

升级到上游最新版本，见同目录下的 `SKILL.md`——Agent 可据此自动完成比对、更新、翻译和验证。

## 注意事项

- Sisyphus 和 Hephaestus 的 prompt 是**动态构建**的：运行时根据可用 Agent、工具、技能、分类等信息动态拼接各 section。此处提取的是 Sisyphus `claude-fable-5.ts` / Hephaestus `gpt.ts` 的核心模板；静态 section（Agent Identity、Anti-Duplication、Hard Blocks、Anti-Patterns、Todo Discipline 等）已内联渲染，依赖运行时状态的 section（key triggers、tool selection、delegation table 等）保留 `${...}` 占位符。
- 其他 Agent 的 prompt 为 TypeScript 中的字符串常量或独立的 Markdown 文件，这里提取的是完整原始内容。
- origin 提取保留源码转义原样（`\``、`\`\`\``、`\${` 不还原），与既有 origin 文件格式一致。
- Sisyphus 上游有多个变体（claude-fable-5 / claude-opus-5 / claude-opus-4-8 / claude-opus-4-7 / gpt-5-4 / gpt-5-5 / kimi / gemini 等），此处提取的是 Claude Fable 5 变体。
- Sisyphus-Junior 有多个模型变体（gemini, gpt-5-4, gpt-5-5, kimi-k2-6 等），此处提取的是 Claude 系列的 default 版本（`useTaskSystem=false`，TODO 模式）。
- Hephaestus 仅支持 GPT 系列模型，上游有 gpt.ts / gpt-5-4 / gpt-5-5 / gpt-5-6 变体，此处提取的是通用 GPT fallback 版本（`gpt.ts`）。

## 不收录的角色/模式说明

以下文件位于上游仓库中，但 **不是独立 Agent 角色**，因此不收录：

| 文件路径 | 本质 | 不收录理由 |
|----------|------|-----------|
| `prompts-core/prompts/ultrawork/default.md` | 工作模式注入 | 运行时注入给 Sisyphus 的指令，无独立 Agent 身份 |
| `prompts-core/prompts/ultrawork/codex.md` | 同上（Codex 变体） | 同上 |
| `prompts-core/prompts/ultrawork/gemini.md` | 同上（Gemini 变体） | 同上 |
| `prompts-core/prompts/ultrawork/gpt.md` | 同上（GPT 变体） | 同上 |
| `prompts-core/prompts/ultrawork/glm.md` | 同上（GLM 变体） | 同上 |
| `prompts-core/prompts/ultrawork/planner.md` | Prometheus 扩展指令 | 内容以 "You are Prometheus" 开头，是 Prometheus 的补充，非新角色 |
| `prompts-core/prompts/mode/hyperplan.md` | 运行模式 | 嵌套在 team-mode 中的对抗性规划流程指引，非 Agent |
| `prompts-core/prompts/mode/team.md` | 运行模式 | team_* 工具使用指引，非 Agent |

