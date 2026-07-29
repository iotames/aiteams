# ims-metagpt 学习教程

> 基于 MetaGPT 的多 Agent 软件团队实战教程。
> 适合人群：已有 Python 基础，正在学习 AI Agent 框架的开发者。

---

## 目录

- [第一章：MetaGPT 核心概念](#第一章metagpt-核心概念)
- [第二章：Action 编写详解](#第二章action-编写详解)
- [第三章：Role 编写详解](#第三章role-编写详解)
- [第四章：Team 编排与 SOP](#第四章team-编排与-sop)
- [第五章：IMS 全流程剖析](#第五章ims-全流程剖析)
- [第六章：进阶扩展](#第六章进阶扩展)
- [第七章：工程化工作流实战](#第七章工程化工作流实战)

---

## 第一章：MetaGPT 核心概念

### 1.1 什么是 MetaGPT？

MetaGPT 是一个 **多 Agent 框架**，灵感来自**软件公司**的组织结构。它将不同的 LLM 实例赋予不同的**角色**（Role），每个角色执行特定的**动作**（Action），角色之间通过**消息**协作，最终完成复杂的软件工程任务。

**核心理念：** `Code = SOP(Team)`

把软件工程的标准化流程（SOP）固化为多 Agent 团队的协作流程，让 AI 像软件公司一样工作。

### 1.2 四大核心抽象

| 概念 | 类比 | 说明 | 源码位置 |
|------|------|------|----------|
| **Action** | 一个员工的具体技能 | 最细粒度的任务单元，如"写代码"、"写测试" | `metagpt/actions/action.py` |
| **Role** | 一个员工 | 拥有多项技能，能感知环境、思考、行动 | `metagpt/roles/role.py` |
| **Environment** | 公司的办公室 | 角色之间的消息路由和共享空间 | `metagpt/environment/base_env.py` |
| **Team** | 整个公司 | 组装角色、分配预算、启动运行 | `metagpt/team.py` |

### 1.3 消息驱动机制

MetaGPT 的角色之间通过 **Message** 通信。每个 Action 执行后输出一个 `Message`，包含：

```python
Message(content="...", role="ProductManager", cause_by=WritePRD)
```

- `cause_by`：标记这个消息是由哪个 Action 产生的
- 下游 Role 通过 `_watch([ActionClass])` 订阅特定类型的消息

**关键理解：** `_watch` 不是直接调用，而是**订阅消息类型**。当 Environment 中有匹配类型的消息发布时，订阅的 Role 自动被唤醒。

### 1.4 三种 React 模式

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| **REACT**（默认） | Role 先 `_think` 决定做什么，再 `_act` 执行 | 需要决策的场景 |
| **BY_ORDER** | 按 `set_actions` 的顺序依次执行 | 固定流水线场景 |
| **PLAN_AND_ACT** | Role 先规划再执行，可动态调整 | 复杂任务场景 |

---

## 第二章：Action 编写详解

### 2.1 Action 基类

```python
# metagpt/actions/action.py（简化版）
class Action(BaseModel):
    name: str = ""          # Action 名称
    prefix: str = ""        # system prompt 前缀
    llm: LLM               # LLM 实例

    async def run(self, *args, **kwargs):
        """执行 Action，子类必须实现"""
        raise NotImplementedError

    async def _aask(self, prompt: str) -> str:
        """向 LLM 发送 prompt 并获取回复"""
        return await self.llm.aask(prompt)
```

### 2.2 两种 Action 编写模式

**模式一：PROMPT_TEMPLATE + _aask（本项目采用）**

```python
# src/ims_metagpt/actions/write_prd.py
class WritePRD(Action):
    name: str = "WritePRD"

    async def run(self, task_plan: str, requirement: str) -> str:
        # 1. 组装 prompt
        prompt = PRD_PROMPT.format(task_plan=task_plan, requirement=requirement)
        # 2. 调用 LLM
        rsp = await self._aask(prompt)
        return rsp
```

**特点：** 简单直接，提示词放在独立文件 `prompts/` 中。

**模式二：ActionNode 结构化输出（官方常用）**

```python
# metagpt/actions/write_prd.py（官方示例，简化版）
class WritePRD(Action):
    name: str = "WritePRD"

    async def run(self, *args, **kwargs):
        # 使用 ActionNode 定义结构化输出格式
        node = ActionNode(
            key="PRD",
            expected_type=dict,
            instruction="Write a PRD document...",
            schema="json",  # 要求 LLM 以 JSON 格式输出
        )
        return await node.fill(req=context, llm=self.llm)
```

**特点：** 输出结构可控，适合需要解析结构化数据的场景。

### 2.3 Action 命名约定

- 系统内置 Action（位于 `metagpt/actions/`）以动词命名：`WriteCode`、`WriteTest`、`RunCode`
- 自定义 Action 建议：`[动词][领域]`，如 `WritePRD`、`WriteBackend`
- `name` 字段默认取类名，也可以在类中显式指定

---

## 第三章：Role 编写详解

### 3.1 Role 基类核心接口

```python
# metagpt/roles/role.py（简化版）
class Role(BaseModel):
    name: str           # 角色名（如 "Alice"）
    profile: str        # 角色类型（如 "ProductManager"）
    goal: str           # 角色目标
    actions: list[Action]  # 拥有的技能

    def _watch(self, actions: list[type[Action]]):
        """订阅指定类型的 Action 输出消息"""

    def set_actions(self, actions: list[Action]):
        """设置角色可执行的 Action 列表"""

    def _set_react_mode(self, react_mode: RoleReactMode):
        """设置 React 模式"""

    async def _act(self) -> Message:
        """执行当前 Action（子类重写）"""

    async def _think(self) -> bool:
        """决定下一步做什么（REACT 模式重写）"""

    def get_memories(self, k: int = 0) -> list[Message]:
        """获取历史消息，k=0 获取全部，k=1 获取最近一条"""
```

### 3.2 简单的 Role 实现

```python
# src/ims_metagpt/roles/ims_architect.py（简化版）
class IMSArchitect(Role):
    name: str = "Bob"
    profile: str = "Architect"
    goal: str = "设计可扩展的全栈系统架构"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_actions([WriteDesign])         # 拥有 WriteDesign 技能
        self._watch([WritePRD])                 # 订阅 WritePRD 的输出

    async def _act(self) -> Message:
        # 1. 获取触发消息（最近一条）
        memories = self.get_memories(k=1)
        prd = memories[0].content

        # 2. 执行 Action
        design = await self.rc.todo.run(prd=prd)

        # 3. 返回结果消息
        return Message(content=design, role=self.profile, cause_by=type(self.rc.todo))
```

### 3.3 BY_ORDER 模式的 Role

当 Role 有多个 Action 需要按顺序执行时，使用 `BY_ORDER` 模式：

```python
class IMSEngineer(Role):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 三个 Action 按顺序执行
        self.set_actions([WriteBackend, WriteFrontend, WriteTests])
        self._set_react_mode(RoleReactMode.BY_ORDER.value)
        self._watch([WriteDesign])

    async def _act(self) -> Message:
        todo = self.rc.todo  # 当前要执行的 Action
        # BY_ORDER 模式下，_act 会被多次调用（每次执行一个 Action）
        # 第一次调用：todo = WriteBackend
        # 第二次调用：todo = WriteFrontend
        # 第三次调用：todo = WriteTests
        ...
```

### 3.4 消息流完整链路

```
[用户输入] UserRequirement(content="生成一个进销存系统")
    │
    ▼ IMSTeamLeader._watch([UserRequirement]) ← 被唤醒
    → PlanTasks.run(requirement=...) → Message(cause_by=PlanTasks)
    │
    ▼ IMSProductManager._watch([PlanTasks]) ← 被唤醒  
    → WritePRD.run(task_plan=...) → Message(cause_by=WritePRD)
    │
    ▼ IMSArchitect._watch([WritePRD]) ← 被唤醒
    → WriteDesign.run(prd=...) → Message(cause_by=WriteDesign)
    │
    ▼ IMSEngineer._watch([WriteDesign]) ← 被唤醒
    → WriteBackend.run(design=...) → Message(cause_by=WriteBackend)
    → WriteFrontend.run(design=...) → Message(cause_by=WriteFrontend)
    → WriteTests.run(code=...) → Message(cause_by=WriteTests)
```

---

## 第四章：Team 编排与 SOP

### 4.1 Team 类

```python
# metagpt/team.py（简化版）
class Team(BaseModel):
    env: Environment        # 工作环境
    investment: float       # 预算上限
    idea: str               # 当前项目需求

    def hire(self, roles: list[Role]):
        """雇佣角色到团队"""

    def invest(self, investment: float):
        """设置预算"""

    async def run(self, n_round=3, idea="", send_to=""):
        """启动团队协作"""
```

### 4.2 两种 Environment

**标准 Environment**（本项目使用）：

```python
env = Environment(desc="开发环境")
team = Team(env=env, roles=[...])
# 或
team = Team()
team.hire([...])
# 默认 use_mgx=False 时使用标准 Environment
```

**MGXEnv**（MetaGPT X 模式，默认开启）：

```python
# team.py 中 use_mgx 默认 True
team = Team(use_mgx=True)  # 使用 MGXEnv
# MGXEnv 会将所有消息路由经过 TeamLeader（名为 "Mike"）处理
# 需要在角色列表中包含 TeamLeader
```

**二者的区别：**

| 特性 | 标准 Environment | MGXEnv |
|------|-----------------|--------|
| 消息路由 | 基于 `_watch` 订阅 | 经 TeamLeader 中转分发 |
| 适用场景 | 简单清晰的流水线 | 需要协调决策的复杂场景 |
| 复杂度 | 低 | 高 |

### 4.3 完整 Team 组装

```python
# src/ims_metagpt/main.py（简化版）
def _build_team(mode: str) -> Team:
    env = Environment(desc="IMS 软件生成团队工作环境")

    if mode == "full":
        roles = [IMSTeamLeader(), IMSProductManager(), IMSArchitect(), IMSEngineer()]
    elif mode == "plan-only":
        roles = [IMSTeamLeader()]

    team = Team(investment=10.0, env=env, roles=roles)
    return team
```

### 4.4 Team 运行流程

```python
async def run():
    team = _build_team("full")
    team.invest(investment=10.0)

    # team.run() 内部：
    # 1. run_project(idea) — 发布消息到 Environment
    # 2. 循环 n_round 次，每次调用 env.run()
    # 3. env.run() 遍历所有非空闲角色，并行执行 role.run()
    # 4. 当所有角色都 idle 时终止
    await team.run(n_round=10, idea="生成一个进销存系统")
```

---

## 第五章：IMS 全流程剖析

### 5.1 一条需求如何变成代码

以 `ims-metagpt "生成一个进销存管理系统"` 为例，追踪完整的消息流：

**Step 1: TeamLeader 接收需求**

```
输入: "生成一个进销存管理系统"
Action: PlanTasks.run(requirement="生成一个进销存管理系统")
提示词: prompts/task_planning.py
      → 将需求拆解为 T1~T5 五个任务
输出: 任务规划 Markdown
```

**Step 2: ProductManager 写 PRD**

```
输入: 任务规划 + 用户需求
Action: WritePRD.run(task_plan=..., requirement=...)
提示词: prompts/prd.py
      → 包含 IMS 六大模块的领域知识参考
      → 要求输出功能清单、用户故事、验收标准
输出: 完整的 PRD 文档
```

**Step 3: Architect 做设计**

```
输入: PRD 文档
Action: WriteDesign.run(prd=...)
提示词: prompts/design.py
      → 指定技术栈：FastAPI + SQLAlchemy + Bootstrap 5
      → 要求输出 ER 图、API 路由、前端组件
输出: 系统架构设计文档
```

**Step 4: Engineer 写代码（三轮）**

```
第1轮: WriteBackend.run(design=...)
      → 提示词包含 11 个文件的精确规格
      → 输出 FastAPI 后端代码

第2轮: WriteFrontend.run(design=...)
      → 提示词包含 11 个前端文件的精确规格
      → 输出 Bootstrap 5 前端页面

第3轮: WriteTests.run(code=...)
      → 提示词包含测试文件规格
      → 输出 pytest 测试代码
```

### 5.2 提示词设计的技巧

**技巧一：给 LLM 具体的输出格式**

```
不好的提示词："写一个商品管理功能"
好的提示词："文件路径: backend/app/routes/products.py\n---\nfrom fastapi import APIRouter\n..."
```

**技巧二：提供领域知识参考**

```
# 在 PRD 提示词中嵌入 IMS 领域知识
## IMS 核心模块
- 商品管理（分类、信息、图片、搜索）
- 采购管理（采购单、入库、退货）
- 销售管理（销售单、出库、退货）
...
```

**技巧三：Action 与 Prompt 分离**

```
actions/write_prd.py     ← 只负责调用 LLM
prompts/prd.py           ← 只负责提示词模板
```

这样替换领域知识只需要改 `prompts/` 目录。

### 5.3 常见问题

**Q: 角色没有按预期执行？**
A: 检查 `_watch` 订阅的 Action 类型是否与上游 Action 的 `cause_by` 匹配。注意 `_watch([PlanTasks])` 订阅的是 `PlanTasks` 类的输出消息。

**Q: 消息匹配不上？**
A: 检查 `Message(cause_by=type(todo))` 中的 `type(todo)` 是否正确。如果上下游的 Action 类型不匹配，消息会被静默丢弃。

**Q: 一个角色有多个 Action 怎么按顺序执行？**
A: 使用 `BY_ORDER` 模式，`_set_react_mode(RoleReactMode.BY_ORDER.value)`，Action 会按 `set_actions` 的顺序依次执行。

---

## 第六章：进阶扩展

### 6.1 自定义 Tool

MetaGPT 支持注册自定义工具函数，供 DataInterpreter 等角色调用：

```python
from metagpt.tools.tool_registry import register_tool

@register_tool()
def query_stock(product_code: str) -> dict:
    """
    查询商品库存信息。

    Args:
        product_code: 商品编码
    Returns:
        库存信息字典
    """
    # 实际查询逻辑...
    return {"code": product_code, "quantity": 100}
```

源码参考：`metagpt/tools/tool_registry.py`

### 6.2 断点恢复

MetaGPT 支持序列化和反序列化 Team 状态：

```python
# 保存
team.serialize(stg_path=Path("./storage/team"))

# 恢复
team = Team.deserialize(stg_path=Path("./storage/team"))
```

源码参考：`metagpt/team.py` 中的 `serialize` / `deserialize` 方法。

### 6.3 增量开发

使用 `inc=True` 模式在已有项目基础上继续开发：

```python
from metagpt.software_company import generate_repo

generate_repo(
    idea="添加库存预警功能",
    inc=True,
    project_path="./workspace/my-ims",
)
```

源码参考：`metagpt/software_company.py`

### 6.4 各角色使用不同 LLM

```yaml
# config2.yaml
roles:
  - role: "IMSArchitect"
    llm:
      api_type: "openai"
      model: "gpt-4-turbo"     # 架构师用最强的模型
  - role: "IMSEngineer"
    llm:
      api_type: "deepseek"
      model: "deepseek-chat"    # 工程师用性价比高的模型
```

### 6.5 参考资源

| 资源 | 链接/路径 |
|------|-----------|
| MetaGPT 官方文档 | https://docs.deepwisdom.ai/ |
| MetaGPT 源码 | `MetaGPT/metagpt/` |
| Action 源码 | `metagpt/actions/action.py` |
| Role 源码 | `metagpt/roles/role.py` |
| Team 源码 | `metagpt/team.py` |
| 官方示例 | `MetaGPT/examples/` |
| DataInterpreter | `MetaGPT/examples/di/` |

---

## 第七章：工程化工作流实战

> 本章聚焦于 **完整的软件交付流程**：从需求到 MVP 到迭代到重构。
> 这是本项目的核心价值所在——不是一次性的代码生成，而是覆盖整个软件生命周期的工程化工具。

### 7.1 核心理念：AI 生成 + 人工审核

```
         AI 负责                   人类负责
   ┌──────────────┐          ┌──────────────┐
   │ 生成草案      │  ──→    │ 审核确认      │
   │ (PRD/Design)  │          │ (修改/否决)   │
   └──────────────┘          └──────────────┘
         │                          │
         ▼                          ▼
   ┌──────────────┐          ┌──────────────┐
   │ 生成代码      │  ──→    │ 审查 diff     │
   │ (增量变更)    │          │ (确认合并)    │
   └──────────────┘          └──────────────┘
```

**为什么要有人工审核？**

AI 生成的代码和文档不一定完全符合你的业务需求。人工审核确保：
- 产品功能覆盖完整、优先级正确
- 技术选型符合团队标准
- 代码质量可控

### 7.2 五个命令对应五个阶段

| 命令 | 阶段 | AI 做什么 | 你做什么 |
|------|------|-----------|----------|
| `plan` | 需求分析 | 生成任务规划和 PRD | 审核 PRD，确认功能清单 |
| `design` | 架构设计 | 生成技术架构设计 | 审核设计，确认技术方案 |
| `code` | 编码实现 | 生成可运行代码 | 测试验证，部署上线 |
| `iterate` | 迭代开发 | 生成增量变更方案 | 审查 diff，合并代码 |
| `refactor` | 代码重构 | 生成重构方案 | 审查 diff，确认重构 |

### 7.3 完整实战：从零到上线

假设你要为一个便利店开发进销存系统。

#### Phase 1：需求分析（plan）

```bash
ims-metagpt plan "为便利店开发进销存系统，先做商品管理和进货出货" -o ./convenience-store
```

**运行后 AI 生成：**
- `docs/task-plan.md` — AI 认为需要做哪些任务
- `docs/prd.md` — 产品需求文档

**你的操作：**
```bash
# 打开 PRD 文件检查
notepad ./convenience-store/docs/prd.md
# 或者用 VS Code
code ./convenience-store/docs/prd.md
```

**审核要点：**
- 功能清单是否覆盖了便利店的核心流程？
- 用户故事是否符合实际业务场景？
- 优先级标注是否合理？（P0 必须是核心功能）

如果 PRD 缺了"会员管理"功能，你可以在文件中添加：
```markdown
### 会员管理（P2）
- 会员注册：姓名、手机号、积分
- 积分累计：消费金额自动累积积分
- 积分兑换：积分抵扣现金
```

修改保存后，进入下一阶段。

#### Phase 2：架构设计（design）

```bash
ims-metagpt design -w ./convenience-store
```

AI 读取你修改后的 PRD，生成架构设计。

**你的操作：**
```bash
code ./convenience-store/docs/design.md
```

**审核要点：**
- 数据模型是否覆盖了所有业务实体？
- API 路由设计是否符合 RESTful 规范？
- 前端页面布局是否合理？

修改确认后，进入编码阶段。

#### Phase 3：MVP 编码（code）

```bash
# MVP 模式：只生成最核心的功能
ims-metagpt code -w ./convenience-store --scope mvp
```

**MVP 范围（AI 只会生成这些）：**
- 商品管理（分类、商品 CRUD、搜索）
- 入库/出库操作
- 库存查询和低库存预警
- 基础的登录页面和仪表盘

**你的操作：**
```bash
# 启动后端验证
cd ./convenience-store/backend
pip install -r requirements.txt
python run.py
# 访问 http://localhost:8000/docs 查看 API 文档
```

测试通过后，MVP 就可以部署上线了。

#### Phase 4：迭代增加功能（iterate）

MVP 上线后，用户反馈需要采购管理：

```bash
ims-metagpt iterate "增加完整的采购管理模块，含采购单创建、审核、入库" -w ./convenience-store
```

AI 读取已有代码，生成增量变更：

```
./convenience-store/changes_0.md  ← 变更 diff
```

**你的操作：**
```bash
code ./convenience-store/changes_0.md  # 审查变更
```

变更 diff 的格式：
```diff
--- a/backend/app/routes/products.py
+++ b/backend/app/routes/products.py
@@ ... @@
+@router.post("/purchase-orders", response_model=PurchaseOrderOut)
+async def create_purchase_order(order: PurchaseOrderCreate, db: Session = Depends(get_db)):
+    """创建采购单"""
+    ...
```

确认无误后，手动将变更应用到代码中。

#### Phase 5：重构优化（refactor）

代码累积了几轮迭代后，你可能需要重构：

```bash
ims-metagpt refactor "提取公共 CRUD 基类，减少重复代码，统一错误处理" -w ./convenience-store
```

AI 分析所有代码，生成重构方案。

### 7.4 修改提示词的正确做法

**场景：PRD 不符合你的行业要求**

编辑 `src/ims_metagpt/prompts/prd.py`，找到 IMS 领域知识参考部分：

```python
# 修改前（通用进销存）
PRD_PROMPT = """
## IMS 领域知识参考
进销存管理系统（IMS）核心功能模块包括：
### 1. 商品管理
### 2. 采购管理
### 3. 销售管理
...
"""
```

改为你需要的行业版本：

```python
# 修改后（便利店专用）
PRD_PROMPT = """
## 便利店管理系统 核心功能模块
### 1. 商品管理
- 商品分类：食品、饮料、日用品、烟酒等
- 条码扫描录入
- 保质期管理（到期自动预警）
- 便利店特有的"关东煮/便当"等鲜食管理

### 2. 进货管理
- 供应商管理（本地供应商、批发市场）
- 进货单（支持按条码录入）
- 进货退货

### 3. 销售管理
- 收银台模式（快速结算）
- 微信/支付宝/现金多种支付
- 会员积分

### 4. 库存管理
- 实时库存（后仓+货架）
- 缺货预警
- 盘点（支持手持终端）
...
"""
```

**修改后重启运行即可生效**，不需要改任何 Python 代码。

### 7.5 常见工程化问题

**Q: 生成的代码运行报错怎么办？**
A: 这是预期的。AI 生成的代码可能有小 bug。修复后可以用 iterate 命令继续迭代：
```bash
ims-metagpt iterate "修复 API 路由错误，确保所有端点可访问" -w ./my-ims
```

**Q: 如何修改技术栈？**
A: 编辑 `src/ims_metagpt/prompts/design.py` 中的技术要求部分。例如把 SQLite 改为 PostgreSQL。

**Q: 如何控制每次生成的 Token 消耗？**
A: 使用 `--scope mvp`（只生成核心功能）和 `--mode backend-only`（只生成后端）。

**Q: 每次运行前需要清理 workspace 吗？**
A: 不需要。plan/design 阶段只读写 docs/ 目录。code 阶段会覆盖同名文件。iterate 阶段生成独立的 diff 文件，不会自动修改你的代码。

**Q: 想把整个流程自动化怎么办？**
A: 使用 `--auto` 参数跳过人工审核提示，但建议只在快速原型时使用。

---

> 学完本章，你已经掌握了完整的 AI 辅助软件交付流程。
> 接下来可以尝试：修改提示词适配你自己的业务领域，或者给本项目提交 PR 增加更多功能。
