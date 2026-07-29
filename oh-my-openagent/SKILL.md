---
name: omo-agent-upgrade
description: 升级 oh-my-openagent Agent 提示词。当用户要求同步上游 OmO 仓库的提示词变更、升级本地 Agent 提示词到最新版本、或检查开源更新时使用。
---

# OmO Agent 提示词升级流程

将 upstream [oh-my-openagent](https://github.com/code-yeongyu/oh-my-openagent) 的 Agent prompt 变更同步到本地 OpenCode 格式 + 中文翻译版。

## 目录结构

```
oh-my-openagent/
├── README.md          # 提取记录与映射说明
├── SKILL.md           # 本文件
├── origin/            # 原始英文 prompt（上游直采，未翻译）
│   ├── sisyphus.md
│   ├── hephaestus.md
│   ├── atlas.md
│   ├── prometheus.md
│   ├── oracle.md
│   ├── momus.md
│   ├── metis.md
│   ├── explore.md
│   ├── librarian.md
│   ├── multimodal-looker.md
│   └── sisyphus-junior.md
└── agents/            # 中文翻译版（OpenCode .md 格式）
    ├── sisyphus.md
    ├── hephaestus.md
    ├── atlas.md
    ├── prometheus.md
    ├── oracle.md
    ├── momus.md
    ├── metis.md
    ├── explore.md
    ├── librarian.md
    ├── multimodal-looker.md
    └── sisyphus-junior.md
```

## 上游 → 本地文件映射

| Agent | 上游源码路径 | origin 文件 | agents 文件 | 类型 |
|-------|-------------|-------------|-------------|------|
| Atlas | `packages/prompts-core/prompts/atlas/default.md` | `origin/atlas.md` | `agents/atlas.md` | 静态 Markdown |
| Prometheus | `packages/prompts-core/prompts/prometheus/default.md` | `origin/prometheus.md` | `agents/prometheus.md` | 静态 Markdown |
| Oracle | `packages/omo-opencode/src/agents/oracle.ts` | `origin/oracle.md` | `agents/oracle.md` | 静态 TypeScript 常量 |
| Momus | `packages/omo-opencode/src/agents/momus.ts` | `origin/momus.md` | `agents/momus.md` | 静态 TypeScript 常量 |
| Metis | `packages/omo-opencode/src/agents/metis.ts` | `origin/metis.md` | `agents/metis.md` | 静态 TypeScript 常量 |
| Explore | `packages/omo-opencode/src/agents/explore.ts` | `origin/explore.md` | `agents/explore.md` | 静态 TypeScript 常量 |
| Librarian | `packages/omo-opencode/src/agents/librarian.ts` | `origin/librarian.md` | `agents/librarian.md` | 静态 TypeScript 常量 |
| Multimodal Looker | `packages/omo-opencode/src/agents/multimodal-looker.ts` | `origin/multimodal-looker.md` | `agents/multimodal-looker.md` | 静态 TypeScript 常量 |
| Sisyphus-Junior | `packages/omo-opencode/src/agents/sisyphus-junior/default.ts` | `origin/sisyphus-junior.md` | `agents/sisyphus-junior.md` | 静态 TypeScript 常量 |
| Sisyphus | `packages/omo-opencode/src/agents/sisyphus/default.ts` + `sisyphus-dynamic-prompt-*.ts` | `origin/sisyphus.md` | `agents/sisyphus.md` | **动态模板** |
| Hephaestus | `packages/omo-opencode/src/agents/hephaestus/gpt.ts` | `origin/hephaestus.md` | `agents/hephaestus.md` | **动态模板** |

## 步骤

### 第 0 步：拉取上游最新

```bash
# 克隆或 fetch 上游 dev 分支到临时目录
UPSTREAM=$(mktemp -d)
git clone --depth 1 --branch dev https://github.com/code-yeongyu/oh-my-openagent.git "$UPSTREAM"
```

### 第 1 步：按类型比对变更

针对 `origin/` 下的每个 Agent，比对上游源文件与本地 origin 文件：

**静态 Markdown 类型**（Atlas, Prometheus）：
对比上游 repo 中的 `.md` 文件与本地 `origin/<agent>.md`。

**静态 TypeScript 类型**（Oracle, Momus, Metis 等）：
从上游 `.ts` 文件中提取 system prompt 字符串常量，与本地 `origin/<agent>.md` 比对。

**动态模板类型**（Sisyphus, Hephaestus）：
- 核心指令部分来自 `default.ts` / `gpt.ts`
- 模板中的动态 section 标记（如 `{{delegation_table}}`、`{{skills_guide}}`）需比对这些 section 的生成逻辑是否变化
- 只比对核心模板本身，不运行动态注入

比对方式：

```bash
SELF="$(dirname "$0")"  # 脚本所在目录即本项目目录
diff -u "$SELF/origin/<agent>.md" "$UPSTREAM/<对应源码路径>" || echo "有变更"
```

### 第 2 步：更新 origin 文件

对检测到变更的 Agent：
1. 从上游源文件提取完整 prompt 文本
2. 写入 `origin/<agent>.md`（覆盖），保持原始英文
3. 记录变更摘要

### 第 3 步：翻译并写入 agents 文件

对每个更新的 origin 文件：
1. 读取 `origin/<agent>.md` 中的英文原文
2. 读取 `agents/<agent>.md` 现在的 YAML front matter（保留不动）
3. 翻译英文正文为中文，保持：
   - YAML front matter 完全不变
   - 术语一致性（同一概念全库统一译法）
   - 指令语气一致（禁止谄媚、简洁直接等风格约束）
4. 写入 `agents/<agent>.md`

**动态模板特殊处理**：
- Sisyphus/Hephaestus 的 `agents/<agent>.md` 中只保留核心指令部分
- 模板中的 `{{variable}}` 占位符保持原样不翻译
- 在正文开头加注释注明此为静态核心模板，动态 section 在运行时注入

### 第 4 步：验证

```bash
SELF="$(dirname "$0")"
# 1. YAML front matter 完整性检查
for f in "$SELF/agents"/*.md; do
  head -1 "$f" | grep -q '^---$' || echo "缺失 front matter: $f"
done

# 2. 确保无残留英文占位符（如未翻译的段落）
for f in "$SELF/agents"/*.md; do
  # 检查是否有超过 50% 英文单词的段落（粗略）
  grep -c '[a-zA-Z]\{4,\}' "$f" && echo "可能残留英文: $f"
done

# 3. 行数差异警示（变更幅度过大说明上游变动大）
wc -l "$SELF/origin"/*.md
```

### 第 5 步：更新 README

更新 `README.md` 中的：
- 提取日期
- commit hash（如果追踪）
- 变更摘要

### 第 6 步：清理

```bash
rm -rf "$UPSTREAM"
```

## 变更追踪

每次升级后，在 README 的变更日志中追加记录：

```markdown
## 变更日志
### 2026-07-29
- Oracle: 新增关于 XYZ 的指令段落
- Sisyphus: 核心模板无变更
```

## 注意事项

- 每个 `task()` 委托处理一个 Agent 的升级，并行执行
- 动态模板 Agent（Sisyphus/Hephaestus）只比对核心指令部分，不涉及运行时注入的 section
- Hephaestus 上游只有 GPT 版本，翻译时注意模型无关性
- Sisyphus-Junior 有多个模型变体（gemini/gpt-5/kimi），只关注 Claude 系列的 default 版本
