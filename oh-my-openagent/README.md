# Oh My OpenAgent (OmO) — Agent 角色原始 Prompt 提取

## 说明

本目录从 [oh-my-openagent](https://github.com/code-yeongyu/oh-my-openagent) 源码中提取了 11 个预定义 Agent 角色的原始 system prompt。

## 提取信息

- **仓库**: https://github.com/code-yeongyu/oh-my-openagent
- **分支**: `dev` (commit: `c775ef033`, 版本 5.0.0-beta.82+, as of 2026-09-22)
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

## 变更日志

### 2026-09-22
- 全量比对（4.19.3 → 5.0.0-beta.82+，commit `c775ef033`）：11 个角色全部保留、均未删除。未变 7 个：Sisyphus、Sisyphus-Junior、Oracle、Momus、Metis、Explore、Multimodal-Looker。
- Atlas: REQUIRED TOOLS 移除 codegraph_*，改 lsp_* 为符号查询首选；`/start-work` 命令改名 `/ulw-execute`。
- Prometheus: `/start-work` → `/ulw-execute`。
- Librarian: 年份检查改动态表达式、context7 工具改名 `context7_query-docs`、清理多余表格头。
- 上游拼装链路说明：5.0 新增的 `sisyphus-dynamic-prompt-*.ts` 系列仅用于 fallback prompt，claude-fable-5 主链路未变，提取口径不变。上游提示词层整体是演进而非重写；大变化集中在运行时架构（senpi 引擎 daemon、任务隔离、模型链 lane 路由）与独立版 OmO Native。
- Hephaestus: 同步上游 dev（commit `c775ef033`）——核心模板仅 Todo Discipline 段有变化（旧 `<Todo_Discipline>` TODO OBSESSION 短版 → 完整 `## Todo Discipline (NON-NEGOTIABLE)` 段）；Hard Blocks、Anti-Patterns、Anti-Duplication、GPT File Edit Guidance 内联内容均未变；运行时 `${...}` 占位符 section 未纳入比对（其中 `buildParallelDelegationSection` 因 deep-low/deep-high 拆分有改动，但不在提取口径内）。origin 与中文译文已同步更新。

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

