---
name: routerman
description: >-
  登录 ZTE 路由器管理后台并执行常用管理操作。当用户提到"路由器"、"管理后台"、"端口转发"、
  "父母控制"、"家长控制"、"端口映射"、"开端口"、"限制上网"、"URL黑名单/白名单"、
  或要求读取/修改路由器配置时务必使用此技能。可直接通过 HTTP API 完成登录与配置修改，
  无需浏览器自动化。如 HTTP 方式失败，再回退到 chromedp 技能。
metadata:
  version: 1.0.0
---

# routerman — ZTE 路由器常用管理操作

通过 HTTP API 直接操作 ZTE 路由器管理后台。支持登录、端口转发与父母控制两项功能的增删改查。

## 环境要求

- `curl` 命令可用（仅依赖系统 curl + Python 标准库，无需第三方包）
- Python 3.8+
- 路由器地址与凭据在 `.env` 文件或环境变量中：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ROUTER_ADDR` | `http://192.168.2.1` | 路由器地址 |
| `ROUTER_BRAND` | `ZTE` | 品牌 |
| `ROUTER_LOGIN_USER` | `admin` | 登录用户名 |
| `ROUTER_LOGIN_PASSWORD` | `123456` | 登录密码 |
| `ROUTER_TOKEN` | 空 | 登录后的 SID（脚本自动获取，可选） |

配置加载顺序：`.env` 文件 → 系统环境变量，后者覆盖前者。运行命令的工作目录下放置 `.env` 即可。

## 快速开始

```bash
# 查询端口转发列表
python3 <技能目录>/scripts/routerman.py --env .env pf-list

# 查询父母控制列表
python3 <技能目录>/scripts/routerman.py --env .env pc-list
```

脚本每次运行都会自动完成登录（首页→logintoken→登录→高级模式→进入功能页），无需手动登录。

## 命令行接口

### 登录

```bash
python3 <技能目录>/scripts/routerman.py --env .env login
```

输出当前登录 SID（前 16 位）。如需把 SID 写入 `.env` 的 `ROUTER_TOKEN`，见下文「获取 ROUTER_TOKEN」。

### 端口转发

| 命令 | 功能 | 示例 |
|---|---|---|
| `pf-list` | 查询列表 | `pf-list` |
| `pf-add` | 新增 | `pf-add --alias SSH --protocol TCP --internal-client 192.168.2.10x --external-port 2222 --internal-port 22 --enable 1` |
| `pf-mod` | 修改 | `pf-mod --inst-id DEV.NAT.PtMappingX --alias SSH --protocol TCP --internal-client 192.168.2.10x --external-port 2222 --internal-port 22` |
| `pf-del` | 删除 | `pf-del --inst-id DEV.NAT.PtMappingX` |
| `pf-switch` | 开关 | `pf-switch --inst-id DEV.NAT.PtMappingX --enable 0` |

参数：

- `--alias`：规则名称（1~64 字符）
- `--protocol`：`TCP` / `UDP` / `BOTH`
- `--internal-client`：局域网主机 IP
- `--external-port`：广域网端口
- `--internal-port`：局域网主机端口
- `--enable`：`1` 开启 / `0` 关闭

### 父母控制

| 命令 | 功能 | 示例 |
|---|---|---|
| `pc-list` | 查询列表 | `pc-list` |
| `pc-add` | 新增 | `pc-add --name <设备名> --mac xx:xx:xx:00:00:00 --week 127 --start 8:0 --end 20:0 --mode NotAllowed` |
| `pc-mod` | 修改 | `pc-mod --inst-id DEV.PCUserX --name <设备名> --mac xx:xx:xx:00:00:00 --start 9:0 --end 21:0` |
| `pc-del` | 删除 | `pc-del --inst-id DEV.PCUserX` |
| `pc-switch` | 开关 | `pc-switch --inst-id DEV.PCUserX --enable 0` |

参数：

- `--name`：规则名称（1~32 字符）
- `--mac`：设备 MAC，**必须是路由器已关联设备的 MAC**（虚拟 MAC 会校验失败）
- `--week`：周历十进制值（每天=`127`；位顺序 Su Mo Tu We Th Fr Sa）
- `--start` / `--end`：时间段，格式 `时:分`（如 `8:0`、`20:30`）
- `--mode`：`NotAllowed`（不允许上网）/ `BlackList`（URL黑名单）/ `WhiteList`（URL白名单）
- `--url`：URL 规则（黑/白名单模式可重复传多个）
- `--enable`：`1` 开启 / `0` 关闭

URL 黑名单示例：

```bash
python3 <技能目录>/scripts/routerman.py --env .env pc-add \
  --name 测试黑名单 --mac xx:xx:xx:00:00:00 \
  --start 8:0 --end 20:0 --mode BlackList --url http://example.com
```

## Python API

脚本导出 `Router` 类与各功能函数，可直接 import 使用：

```python
import sys
sys.path.insert(0, "<技能目录>/scripts")
from routerman import Router, load_config, pf_list, pf_apply, pc_apply, pc_list

cfg = load_config(".env")
r = Router(cfg)
r.login()

# 端口转发
items = pf_list(r)                    # 查询列表
ok, err = pf_apply(r, "SSH", "TCP", "192.168.2.10x", 2222, internal_port=22)  # 新增

# 进入功能页拿会话 token 后提交
page = r.enter_feature("portforwarding")
ok, err = pf_apply(r, "SSH", "TCP", "192.168.2.10x", 2222, internal_port=22)
```

### 关键函数

| 函数 | 说明 |
|---|---|
| `Router(cfg)` | 客户端，`cfg` 为 `load_config` 返回的 dict |
| `Router.login()` | 完整登录，成功返回 SID |
| `Router.enter_feature(feature)` | 进入功能页并提取会话 token；`feature` 为 `portforwarding` 或 `parentctrl` |
| `pf_list(r)` | 端口转发列表 |
| `pf_apply(r, alias, protocol, internal_client, external_port, internal_port=None, enable=1, inst_id="-1")` | 端口转发新增/修改 |
| `pf_delete(r, inst_id, ...)` | 端口转发删除 |
| `pf_switch(r, inst_id, enable)` | 端口转发开关 |
| `pc_list(r)` | 父母控制列表 |
| `pc_apply(r, name, child_id, week, start_hour, start_min, end_hour, end_min, filter_mode="NotAllowed", enable=1, inst_id="-1", urls=None)` | 父母控制新增/修改 |
| `pc_delete(r, inst_id, ...)` | 父母控制删除 |
| `pc_switch(r, inst_id, enable)` | 父母控制开关 |

每个操作函数返回 `(ok, err)`：`ok=True` 表示成功；`err` 为失败详情（含 `IF_ERRORPARAM` 指出的字段）。

## 获取 ROUTER_TOKEN 并写入 .env

```bash
# 1. 运行登录获取 SID
python3 <技能目录>/scripts/routerman.py --env .env login

# 2. 用脚本把 SID 写入 .env 的 ROUTER_TOKEN（避免直接操作敏感数据）
```

> `ROUTER_TOKEN` 即登录后下发的 SID Cookie 值，后续请求用它作为认证凭证。脚本自动管理，一般无需手动写入。

## 故障排查

| 现象 | 原因 | 解决 |
|---|---|---|
| 返回 `SessionTimeout` | 使用了登录前的旧 SID | 重新运行脚本（每次自动重新登录） |
| 父母控制新增报 `IF_ERRORPARAM=ChildId` | MAC 非路由器已关联设备 | 先用 `pc-list` 查看已有关联 MAC，或用浏览器"从已关联设备中选择" |
| `Check` 校验失败 | `Check` 头与 body 不匹配 | 确认 body 未变，`Check=sha256(body)` |

## 参考文档

- `docs/ZTE/api.md` — 完整 HTTP 接口文档（登录、端口转发、父母控制字段与请求示例）
- `references/` — 预留扩展

## 回退策略

若 HTTP API 方式失效（固件升级、接口变更等），使用 `chromedp` 技能驱动浏览器登录并操作。先诊断 HTTP 失败原因，再决定是否回退。
