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

## 已关联设备 `/common_page/Query_AccessDevice_lua.lua`（已验证）

> 用于获取父母控制 `ChildId` 所需的真实 MAC。

### 查询设备列表（GET）

```
GET /common_page/Query_AccessDevice_lua.lua?_=<当前毫秒时间戳>
Cookie: SID=...; _TESTCOOKIESUPPORT=1
X-Requested-With: XMLHttpRequest
Accept: application/xml, text/xml, */*; q=0.01
Referer: http://192.168.2.1/getpage.lua?pid=1002&nextpage=Internet_Parent_Ctrl_t.lp
```

关键点：

- `_` 查询参数必须是当前毫秒时间戳（防缓存）。实测 `?_=1`/`?_=123` 这类小值返回 `SessionTimeout`，真实时间戳正常。
- 响应 `OBJ_LAN_ACCESS_ID` 下每 `<Instance>` 一台设备，字段带 `_LuQUID_` 前缀，关键字段：
  `_LuQUID_MACAddress`（设备 MAC）、`_LuQUID_HostName`、`_LuQUID_IPAddress`、`_LuQUID_Active`、`_LuQUID_Band`、`_LuQUID_Interface`。
- 仅返回当前在线设备；已配父母控制但离线的设备不会出现。

## 会话抢占（踢出其他登录用户）（已验证）

> 场景：另一台设备已登录路由器后台，本机再登录时返回「警告！其他用户正在设置设备！」抢占页，
> 无法正常登录。需抢占（踢出）占用会话。

### 登录被占用时的响应特征

- 正常登录 `POST /`（Username/Password/action=login）返回 `302 Moved Temporarily`。
- 被占用时返回 `HTTP/1.1 200 OK`，页面含 `login_warn_span` 警告与 `<div id="Level">` 内的占用会话 radio 列表：

```html
<span id="login_warn_span">警告！其他用户正在设置设备！<br/>您可以选中某个用户，并点击"提交"强制其登出后再进行登录；<br/>或者点击"取消"，稍后再重试。</span>
<div id="Level">
  <p class="row"><input type="radio" id="radio1" name="preempt_sessid" value=<64位hex> />&nbsp;&nbsp;<label for="radio1">IP(用户名)</label></p>
</div>
```

- label 为 HTML 数字实体编码的 `IP(用户名)`，如 `&#49;&#57;&#50;...(&#97;&#100;&#109;&#105;&#110;)` = `192.168.2.100(admin)`。

### 抢占踢出（POST）

```
POST /
Content-Type: application/x-www-form-urlencoded
Check: <sha256(body)>
Cookie: SID=...; _TESTCOOKIESUPPORT=1

preempt_sessid=<占用会话ID>&action=preempt
```

- 成功：`HTTP/1.1 302 Moved Temporarily`，`Set-Cookie: SID=<新值>`，`Location: /`。
- 踢出后需重新走完整登录流程完成登录。
- 取消抢占：body 为 `action=preempt_cancel`。

### CLI 封装验证（✅ 实测通过）

| 命令 | 场景 | 结果 |
|---|---|---|
| `routerman.py kick-list` | 无占用 | ✅ 输出「无其他用户占用，登录正常」 |
| `routerman.py kick-list` | 192.168.2.100 已登录 | ✅ 列出占用会话 sessid + `192.168.2.100(admin)` |
| `routerman.py kick` | 192.168.2.100 已登录 | ✅ 抢占成功并登录，新 SID |
| 踢出后 `kick-list` | — | ✅ 无占用，登录正常 |

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
| 已关联设备 | 查询设备列表（含 MAC） | ✅ 14 台设备 |
| 会话抢占 | kick-list 检测占用 | ✅ 列出占用会话 |
| 会话抢占 | kick 踢出占用并登录 | ✅ 踢出后登录正常 |
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
| `routerman.py dev-list` | ✅ 列出 14 台在线设备及 MAC |
| `routerman.py kick-list` | ✅ 无占用提示 / 有占用列出会话 |
| `routerman.py kick` | ✅ 踢出占用并登录 |
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
3. 父母控制的 `ChildId` MAC 必须是路由器已关联设备的 MAC，用 `dev-list` 获取。
4. 提交字段名要去掉 HTML id 后缀（`colonStripping`），如 `Name:ParentCtrl` → `Name`。
5. `Query_AccessDevice_lua.lua` 的 `_` 查询参数必须是当前毫秒时间戳，小值会返回 `SessionTimeout`。
6. 登录被占用时返回 200 抢占页而非 302；抢占踢出为 `POST preempt_sessid=<sid>&action=preempt`，成功返回 302 + 新 SID。
7. 抢占页 label 为 HTML 数字实体编码的 `IP(用户名)`，用 `html.unescape` 解码。`kick` 会强制登出其他设备，操作前确认目标。

