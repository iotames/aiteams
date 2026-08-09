# routerman 调试记录

> 本文档记录路由器管理后台 `routerman` 技能的调试过程与已验证成功的步骤/接口。随调试推进持续更新。

## 环境与配置

- 路由器地址：`http://192.168.2.1`（ZTE 品牌）
- 配置来源：`.env` 文件（`ROUTER_ADDR` / `ROUTER_BRAND` / `ROUTER_LOGIN_USER` / `ROUTER_LOGIN_PASSWORD`）
- 加载顺序：`.env` 文件 → 系统环境变量，后者覆盖前者

## 登录流程（已验证成功）

### 1. 访问首页获取会话 Cookie

```
GET http://192.168.2.1/
```

响应 `Set-Cookie` 关键字段：

- `SID=<64位hex>` （HttpOnly，登录凭证）
- `_TESTCOOKIESUPPORT=1`

请求头建议带上浏览器 UA。`--insecure` 忽略证书。

### 2. 获取登录动态 Token（logintoken）

```
GET http://192.168.2.1/function_module/login_module/login_page/logintoken_lua.lua
Cookie: SID=...; _TESTCOOKIESUPPORT=1
```

响应体为纯文本数字，例如：

```
<ajax_response_xml_root><动态token></ajax_response_xml_root>
```

取文本内容 `<动态token>` 记为 `xmlObj`（该值每次请求都不同）。

### 3. 计算加密密码

登录页 JS 加密逻辑（`g_loginToken` 函数）：

```js
var SHA256Password = sha256(Password + xmlObj);
```

即：`Password_enc = sha256(明文密码 + xmlObj)`。

### 4. 从登录页提取 `_sessionTOKEN`

登录页 HTML 中隐藏域：

```html
<input type="hidden" name="_sessionTOKEN" id="_sessionTOKEN" value="<动态token>"/>
```

每次访问页面值不同，需从最新页面提取。

### 5. 构造登录请求（已验证成功，返回 302）

```
POST http://192.168.2.1/
Content-Type: application/x-www-form-urlencoded
Cookie: SID=...; _TESTCOOKIESUPPORT=1
Check: <sha256(body)>
Origin: http://192.168.2.1
Referer: http://192.168.2.1/

Username=admin&Password=<Password_enc>&action=login&Frm_Logintoken=&captchaCode=&_sessionTOKEN=<页面token>
```

关键点：

- `Check` 请求头 = `sha256(整个 POST body)`，已用官方抓包样例验证。
- 登录成功返回 `HTTP/1.1 302 Moved Temporarily`，并 `Set-Cookie: SID=<新值>`，用新 SID 继续后续请求。

### 6. 切换高级模式（已验证成功）

```
POST http://192.168.2.1/
Cookie: SID=<登录后SID>; _TESTCOOKIESUPPORT=1
Check: sha256(body)

IF_ModeSwitch=Advanced
```

- `Check` = `sha256("IF_ModeSwitch=Advanced")` = `45d7ab48c5ac7dec3759a650f6683f7d87f06bdb5346511c5a617216445f6086`
- 返回 `302 Moved Temporarily`。

### 7. 进入应用功能/功能页面

```
GET http://192.168.2.1/getpage.lua?pid=1002&nextpage=Internet_PortForwarding_t.lp
Cookie: SID=...; _TESTCOOKIESUPPORT=1
X-Requested-With: XMLHttpRequest
Referer: http://192.168.2.1/
```

返回页面中包含功能配置表单、JS 逻辑以及关键的 `_sessionTmpToken`（动态值，页面加载后 JS 会重新赋值覆盖）。

菜单对应页面：

| 功能 | page 值 | getpage URL |
|---|---|---|
| 端口转发 | `Internet_PortForwarding_t.lp` | `getpage.lua?pid=1002&nextpage=Internet_PortForwarding_t.lp` |
| 父母控制 | `Internet_Parent_Ctrl_t.lp` | `getpage.lua?pid=1002&nextpage=Internet_Parent_Ctrl_t.lp` |

## 接口调用通用规则（已验证）

- 认证方式：Cookie `SID`（登录时下发的值；每次登录会更新）
- 表单提交：`POST` + `Content-Type: application/x-www-form-urlencoded` + `Check: sha256(body)` 头
- 每个功能页面加载后会生成动态 `_sessionTmpToken`（从 `getpage.lua` 返回页面 JS 中提取，JS 在 `$(document).ready` 中最后赋值一次），所有提交数据末尾追加 `&_sessionTOKEN=<token>`
- 响应为 XML：成功时 `<IF_ERRORID>0</IF_ERRORID><IF_ERRORTYPE>SUCC</IF_ERRORTYPE><IF_ERRORSTR>SUCC</IF_ERRORSTR><IF_ERRORPARAM>SUCC</IF_ERRORPARAM>`
- 提交的字段名需去掉表单 id 中的后缀（如 `Name:ParentCtrl` 提交为 `Name`，`Enable:ParentCtrl` 提交为 `Enable`，页面 JS `colonStripping` 处理）
- 删除时 `IF_ACTION=Delete`，仍需携带完整表单字段 + `_InstID`

## 端口转发 `/common_page/PortForwarding_lua.lua`（已验证）

### 查询列表（GET）

```
GET /common_page/PortForwarding_lua.lua
Cookie: SID=...; _TESTCOOKIESUPPORT=1
X-Requested-With: XMLHttpRequest
Referer: http://192.168.2.1/
```

响应 XML 中 `OBJ_FWPM_ID` 下每个 `<Instance>` 一条转发规则，字段：

| 字段 | 含义 |
|---|---|
| `_InstID` | 规则实例 ID，如 `DEV.NAT.PtMappingX` |
| `Alias` | 名称 |
| `Protocol` | `TCP` / `UDP` / `BOTH` |
| `InternalClient` | 局域网主机 IP |
| `ExternalPort` / `ExternalPortEndRange` | 广域网端口范围 |
| `InternalPort` / `InternalPortEndRange` | 局域网主机端口范围 |
| `Enable` | `1` 开启 / `0` 关闭 |

### 新增 / 修改（POST，`IF_ACTION=Apply`）

```
POST /common_page/PortForwarding_lua.lua
Check: sha256(body)
Content-Type: application/x-www-form-urlencoded
X-Requested-With: XMLHttpRequest
Referer: http://192.168.2.1/

IF_ACTION=Apply&Alias=<名称>&Protocol=<TCP|UDP|BOTH>&InternalClient=<IP>
&ExternalPort=<端口>&ExternalPortEndRange=<端口>&InternalPort=<端口>&InternalPortEndRange=<端口>
&Enable=<1|0>&_InstID=<-1新增 | 实例ID修改>&_sessionTOKEN=<token>
```

- 新增：`_InstID=-1`
- 修改：`_InstID=DEV.NAT.PtMappingX`（已存在实例 ID）
- 成功响应返回 `INSTIDENTITY` 和 `_InstID`（新实例 ID）

### 删除（POST，`IF_ACTION=Delete`）

```
POST /common_page/PortForwarding_lua.lua
IF_ACTION=Delete&Alias=<名称>&Protocol=...&_InstID=<实例ID>&_sessionTOKEN=<token>
```

### 开关切换（InstSwitch）

```
IF_ACTION=Apply&Enable=<1|0>&_InstID=<实例ID>&_sessionTOKEN=<token>
```

## 父母控制 `/common_page/ParentCtrl_lua.lua`（已验证）

### 查询列表（GET）

```
GET /common_page/ParentCtrl_lua.lua
Cookie: SID=...; _TESTCOOKIESUPPORT=1
X-Requested-With: XMLHttpRequest
```

响应 `OBJ_PARENT_CONTROL_ID` 下每个 `<Instance>` 一条规则，字段：

| 字段 | 含义 |
|---|---|
| `_InstID` | 规则实例 ID，如 `DEV.PCUserX` |
| `Name` | 名称 |
| `ChildId` | 设备 MAC 地址（如 `xx:xx:xx:00:00:00`） |
| `Week` | 周历十进制值，7 位二进制（`Su Mo Tu We Th Fr Sa` 高位→低位），如 `127`=每天 |
| `StartHour` / `StartMin` / `EndHour` / `EndMin` | 时间段 |
| `FilterMode` | `NotAllowed`(不允许上网) / `BlackList`(URL黑名单) / `WhiteList`(URL白名单) |
| `URLCnt` / `URL0`~`URL31` | URL 规则条数及内容 |
| `Enable` | `1` 开启 / `0` 关闭 |

### 新增 / 修改（POST，`IF_ACTION=Apply`）

```
POST /common_page/ParentCtrl_lua.lua
Check: sha256(body)
Content-Type: application/x-www-form-urlencoded
X-Requested-With: XMLHttpRequest

IF_ACTION=Apply&Name=<名称>&ChildId=<MAC>&Week=<周历>&StartHour=&StartMin=&EndHour=&EndMin=
&FilterMode=<NotAllowed|BlackList|WhiteList>&Enable=<1|0>&_InstID=<-1新增 | 实例ID修改>
[&URLCnt=<n>&URL0=..&URL1=..]&_sessionTOKEN=<token>
```

- **重要**：`ChildId` MAC 必须是路由器已关联的设备 MAC，虚拟 MAC 会返回 `IF_ERRORPARAM=ChildId` 校验失败
- `FilterMode=BlackList/WhiteList` 时需携带 `URLCnt` 和 `URL0`~`URLn-1`
- `FilterMode=NotAllowed` 时 URL 字段不提交

### 删除（POST，`IF_ACTION=Delete`）

```
IF_ACTION=Delete&Name=<名称>&ChildId=<MAC>&_InstID=<实例ID>&_sessionTOKEN=<token>
```

## 调试验证情况

| 功能 | 操作 | 结果 |
|---|---|---|
| 登录 | 完整登录流程 | ✅ 302 + 新 SID |
| 端口转发 | 查询列表 | ✅ 7 条规则 |
| 端口转发 | 新增 `DEV.NAT.PtMappingX` | ✅ |
| 端口转发 | 修改端口 2222→2223 | ✅ |
| 端口转发 | 删除 | ✅ |
| 父母控制 | 查询列表 | ✅ 4 条规则 |
| 父母控制 | 新增（NotAllowed）`DEV.PCUserX` | ✅ |
| 父母控制 | 新增（BlackList + URL）`DEV.PCUserX` | ✅ |
| 父母控制 | 修改 | ✅ |
| 父母控制 | 删除 | ✅ |

> 注：端口转发返回 SessionTimeout 的根因是使用了登录前的旧 SID。必须用登录后下发的 SID + 对应页面的 `_sessionTmpToken` 才能成功。

## 技能封装

技能已封装到 `skills/routerman/`：

```
skills/routerman/
├── SKILL.md                    # 技能主说明（触发、CLI、Python API、故障排查）
├── docs/
│   └── ZTE/
│       └── api.md              # 完整 HTTP 接口文档（登录/端口转发/父母控制）
└── scripts/
    └── routerman.py            # 核心脚本（登录 + 端口转发/父母控制增删改查，CLI + Python API）
```

封装验证（正式版脚本实测通过）：

| 命令 | 结果 |
|---|---|
| `routerman.py pf-list` | ✅ 列出 7 条规则 |
| `routerman.py pc-list` | ✅ 列出 4 条规则 |
| `routerman.py pf-add`（`SkillTest`） | ✅ 新增 `DEV.NAT.PtMappingX` |
| `routerman.py pf-mod` | ✅ 端口 2222→2223 |
| `routerman.py pf-switch` | ✅ 开关切换 |
| `routerman.py pf-del` | ✅ 删除 |
| `routerman.py pc-add`（NotAllowed） | ✅ `DEV.PCUserX` |
| `routerman.py pc-add`（BlackList + URL） | ✅ `URLCnt=1 URL0=...` |
| `routerman.py pc-mod` | ✅ 时间/名称修改 |
| `routerman.py pc-del` | ✅ 删除 |

调试经验要点：

1. 登录的 `Check` 头 = `sha256(POST body)`，`Password_enc = sha256(密码 + xmlObj)`。
2. `_sessionTmpToken` 取功能页 HTML 中最后一次 `\xNN` 转义赋值，需反转义。
3. 父母控制的 `ChildId` MAC 必须是路由器已关联设备的 MAC。
4. 提交字段名要去掉 HTML id 后缀（`colonStripping`），如 `Name:ParentCtrl` → `Name`。

