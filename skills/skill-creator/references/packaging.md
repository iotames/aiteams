# 打包与脚本命令参考

> 本文件为**低频参考**。默认场景（本地开发、零依赖技能、无分发需求）无需读取本文件——
> SKILL 标准以**目录**为分发单位，技能目录本身（`SKILL.md` + 附带资源）就是官方认可、客户端直接可用的形态。
> 仅当需要"单文件分发/传输/归档"、或需要查询完整 CLI 命令时，才加载本文件。

---

## 一、打包（可选，仅用于单文件分发）

**默认不打包。** `.skill` 是本工具提供的**自定义单文件分发格式**（zip），**不是 agentskills.io 标准规定**；
是否可被直接安装取决于目标产品是否支持该导入格式。只有当你确实需要"单个文件分发/传输/归档"时才打包。

```bash
python -m scripts.package_skill <path/to/skill-folder> --output <output-dir>
```

打包前 `package_skill` 会自动运行 `quick_validate`，验证失败则中止打包。

如环境可用，建议用官方参考实现做最终校验（比自研验证器更严格、跟随规范演进）：

```bash
skills-ref validate <path/to/skill-folder>
```

（`skills-ref` 是 agentskills.io 官方发布的验证工具；本机没有时跳过，以 `quick_validate` 为准。）

打包后交付 `.skill` 文件供安装。保留原名（如原技能是 `research-helper`，输出 `research-helper.skill`）。先复制到可写位置再编辑。

> 提示：若仅在本地使用、不进分发流程，无需打包——目录即技能，直接可用。

### 打包排除规则

`scripts/package_skill.py` 会自动排除构建产物，无需手动清理：

| 类型 | 排除项 |
|---|---|
| 目录 | `__pycache__`、`node_modules` |
| 根目录级 | `evals/`（测试用例不进分发包） |
| 文件 | `*.pyc`、`*.skill`、`.DS_Store` |

---

## 二、脚本命令速查

> 注意：所有 `python -m scripts.*` 命令须从 `skill-creator` 技能根目录（含 `scripts/` 目录的层级）运行。

```bash
# 快速验证技能（起草后、打包前必须通过）
python -m scripts.quick_validate <skill-path>

# 汇总 benchmark（生成 benchmark.json 和 benchmark.md）
python -m scripts.aggregate_benchmark <workspace>/iteration-N --skill-name <name>

# 生成评测报告
python -m scripts.generate_report <results.json> -o report.html

# 运行单次触发评测
python -m scripts.run_eval --eval-set <eval-set.json> --skill-path <skill-path>

# 优化技能描述（触发评测 + 改进循环）
python -m scripts.improve_description --eval-results <eval-results.json> --skill-path <skill-path> --model <model>

# 运行优化循环（含 train/test 分层）
python -m scripts.run_loop --eval-set <eval-set.json> --skill-path <skill-path> --model <model>

# 用 OpenAI 兼容端点评测 + 改进（runner 与 llm 可分别指定）
python -m scripts.run_loop --eval-set <eval-set.json> --skill-path <skill-path> \
  --runner openai --llm openai --model gpt-4o-mini \
  --openai-base-url <base-url> --openai-api-key <key>

# 打包技能
python -m scripts.package_skill <skill-path> --output <output-dir>
```

### 环境与依赖

- 依赖：先 `pip install -r requirements.txt`（仅 PyYAML）。
- 测试：`python -m unittest discover -s tests`（无需额外安装）。
- `--runner` 控制评测后端（`claude-code` / `openai`），`--llm` 控制描述改进所用文本模型，两者可混用。
