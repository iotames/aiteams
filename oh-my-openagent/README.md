# Oh My OpenAgent (OmO) — Agent 角色原始 Prompt 提取

## 说明

本目录从 [oh-my-openagent](https://github.com/code-yeongyu/oh-my-openagent) 源码中提取了 11 个预定义 Agent 角色的原始 system prompt。

## 提取信息

- **仓库**: https://github.com/code-yeongyu/oh-my-openagent
- **分支**: `dev` (commit: latest as of 2026-07-29)
- **提取方式**: 从 TypeScript 源码中的字符串常量 / Markdown prompt 文件直接复制
- **语言**: 保留原始英文，未翻译未压缩
- **许可证**: SUL-1.0 (上游仓库)

## 角色清单

| # | Agent | 角色 | 类型 | 数据源 |
|---|-------|------|------|--------|
| 1 | **Sisyphus** | 主协调者/全能开发 | 核心 Agent | `packages/omo-opencode/src/agents/sisyphus/default.ts` + `sisyphus-dynamic-prompt-*.ts` |
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

## 升级流程

升级到上游最新版本，见同目录下的 `SKILL.md`——Agent 可据此自动完成比对、更新、翻译和验证。

## 注意事项

- Sisyphus 和 Hephaestus 的 prompt 是**动态构建**的：运行时根据可用 Agent、工具、技能、分类等信息动态拼接各 section。此处提取的是 `default.ts` / `gpt.ts` 中的默认模板（Claude/GPT 版本），不包含动态注入的 section 内容（如 delegation table、key triggers、skills guide 等）。
- 其他 Agent 的 prompt 为 TypeScript 中的字符串常量或独立的 Markdown 文件，这里提取的是完整原始内容。
- Sisyphus-Junior 有多个模型变体（gemini, gpt-5-4, gpt-5-5, kimi-k2-6 等），此处提取的是 Claude 系列的 default 版本。
- Hephaestus 仅支持 GPT 系列模型，此处提取的是通用 GPT fallback 版本。

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

## 变更日志

### 初始提取 — 2026-07-29

从上游 `dev` 分支提取全部 11 个 Agent 的原始 prompt，完成中文翻译和 OpenCode .md 格式转换。更新 README 说明不收录的 upstream 文件。
