# ZTE 路由器管理后台 HTTP API 文档

> 本文档基于对 ZTE 家庭网关（`http://192.168.2.1`）的实测逆向，记录登录与常用功能的 HTTP 接口。
> 适用于编写可编程/可交互的路由器管理脚本。所有请求使用 `curl` 与 Python 标准库即可完成。

## 总览

- 认证：Cookie `SID`（登录成功后下发，每次登录会更新）
- 提交签名：表单提交需带 `Check: sha256(整个POST body)` 请求头
- 会话令牌：每个功能页加载后生成动态 `_sessionTmpToken`，提交数据末尾追加 `&_sessionTOKEN=<token>`
- 响应格式：`text/xml`，根元素 `<ajax_response_xml_root>`

### 通用响应结构

成功：

```xml
<ajax_response_xml_root>
  <IF_ERRORID>0</IF_ERRORID>
  <IF_ERRORTYPE>SUCC</IF_ERRORTYPE>
  <IF_ERRORSTR>SUCC</IF_ERRORSTR>
  <IF_ERRORPARAM>SUCC</IF_ERRORPARAM>
  ...
</ajax_response_xml_root>
```

失败示例（如 ChildId 校验失败）：

```xml
<IF_ERRORID>-257</IF_ERRORID>
<IF_ERRORTYPE>-1</IF_ERRORTYPE>
<IF_ERRORSTR>FAIL</IF_ERRORSTR>
<IF_ERRORPARAM>ChildId</IF_ERRORPARAM>
```

`IF_ERRORPARAM` 指向校验失败的字段名。

## 登录流程

### 1. 访问首页获取会话

```
GET / HTTP/1.1
```

响应 `Set-Cookie`：

- `SID=<64位hex>`（HttpOnly，认证凭证）
- `_TESTCOOKIESUPPORT=1`

### 2. 获取登录动态 Token

```
GET /function_module/login_module/login_page/logintoken_lua.lua
Cookie: SID=...; _TESTCOOKIESUPPORT=1
```

响应体为动态数字文本：

```xml
<ajax_response_xml_root><动态token></ajax_response_xml_root>
```

取其文本内容记为 `xmlObj`。

### 3. 提取登录页 `_sessionTOKEN`

```
GET /
Cookie: SID=...; _TESTCOOKIESUPPORT=1
```

页面内隐藏域（值每次访问不同）：

```html
<input type="hidden" name="_sessionTOKEN" id="_sessionTOKEN" value="<动态token>"/>
```

### 4. 提交登录

```
POST / HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Check: <sha256(body)>
Origin: http://192.168.2.1
Referer: http://192.168.2.1/
Cookie: SID=...; _TESTCOOKIESUPPORT=1

Username=admin&Password=<Password_enc>&action=login&Frm_Logintoken=&captchaCode=&_sessionTOKEN=<页面token>
```

- `Password_enc = sha256(明文密码 + xmlObj)`
- 成功：`HTTP/1.1 302 Moved Temporarily`，响应 `Set-Cookie: SID=<新值>`
- 后续所有请求使用**新 SID**

### 5. 切换高级模式（必需）

```
POST /
Check: sha256("IF_ModeSwitch=Advanced")
Cookie: SID=<登录后SID>; _TESTCOOKIESUPPORT=1

IF_ModeSwitch=Advanced
```

返回 `302`。不切换则无法访问应用功能接口。

## 进入功能页面（获取会话令牌）

```
GET /getpage.lua?pid=1002&nextpage=<nextpage>
X-Requested-With: XMLHttpRequest
Referer: http://192.168.2.1/
Cookie: SID=...; _TESTCOOKIESUPPORT=1
```

返回 HTML 中包含功能表单与 JS。其中 `_sessionTmpToken` 以 `\xNN` 转义形式出现两次，**最后一次赋值**（`$(document).ready` 内）为有效值，需反转义：

```js
_sessionTmpToken = "\x38\x31\x39\x39..."  // 取最后一个
```

### 功能页面映射

| 功能 | nextpage | 后端接口 |
|---|---|---|
| 端口转发 | `Internet_PortForwarding_t.lp` | `/common_page/PortForwarding_lua.lua` |
| 父母控制 | `Internet_Parent_Ctrl_t.lp` | `/common_page/ParentCtrl_lua.lua` |

## 通用提交规则

- 方法：`POST`
- Content-Type：`application/x-www-form-urlencoded`
- 必带：`Check: sha256(body)`、`X-Requested-With: XMLHttpRequest`、`Referer`
- body 末尾追加：`&_sessionTOKEN=<页面token>`
- 表单字段名需去掉 HTML id 的后缀（页面 JS `colonStripping` 处理），如：
  - `Name:ParentCtrl` → 提交 `Name`
  - `Enable:ParentCtrl` → 提交 `Enable`

## 端口转发 `/common_page/PortForwarding_lua.lua`

### 查询列表（GET）

```
GET /common_page/PortForwarding_lua.lua
Cookie: SID=...; _TESTCOOKIESUPPORT=1
X-Requested-With: XMLHttpRequest
```

响应 `OBJ_FWPM_ID` 下每 `<Instance>` 一条规则：

| 字段 | 含义 | 示例 |
|---|---|---|
| `_InstID` | 规则实例 ID | `DEV.NAT.PtMappingX` |
| `Alias` | 名称 | `SSH` |
| `Protocol` | 协议 | `TCP` / `UDP` / `BOTH` |
| `InternalClient` | 局域网主机 IP | `192.168.2.10x` |
| `ExternalPort` / `ExternalPortEndRange` | 广域网端口范围 | `2222` |
| `InternalPort` / `InternalPortEndRange` | 局域网主机端口范围 | `22` |
| `Enable` | 开关 | `1` / `0` |

### 新增 / 修改（POST）

```
POST /common_page/PortForwarding_lua.lua
Check: sha256(body)
Content-Type: application/x-www-form-urlencoded
X-Requested-With: XMLHttpRequest

IF_ACTION=Apply&Alias=<名称>&Protocol=<TCP|UDP|BOTH>&InternalClient=<IP>
&ExternalPort=<端口>&ExternalPortEndRange=<端口>&InternalPort=<端口>&InternalPortEndRange=<端口>
&Enable=<1|0>&_InstID=<-1|实例ID>&_sessionTOKEN=<token>
```

- 新增：`_InstID=-1`；修改：`_InstID=<已存在实例ID>`
- 成功响应含 `INSTIDENTITY` 与新实例 `_InstID`

### 删除（POST）

```
IF_ACTION=Delete&_InstID=<实例ID>&...&_sessionTOKEN=<token>
```

删除时也需携带完整表单字段，`_InstID` 必填。

### 开关（POST）

```
IF_ACTION=Apply&Enable=<1|0>&_InstID=<实例ID>&_sessionTOKEN=<token>
```

## 父母控制 `/common_page/ParentCtrl_lua.lua`

### 查询列表（GET）

```
GET /common_page/ParentCtrl_lua.lua
Cookie: SID=...; _TESTCOOKIESUPPORT=1
X-Requested-With: XMLHttpRequest
```

响应 `OBJ_PARENT_CONTROL_ID` 下每 `<Instance>` 一条规则：

| 字段 | 含义 | 示例 |
|---|---|---|
| `_InstID` | 规则实例 ID | `DEV.PCUserX` |
| `Name` | 名称 | `<设备名>` |
| `ChildId` | 设备 MAC | `xx:xx:xx:00:00:00` |
| `Week` | 周历十进制值 | `127` |
| `StartHour` / `StartMin` | 开始时间 | `6` / `0` |
| `EndHour` / `EndMin` | 结束时间 | `9` / `0` |
| `FilterMode` | 动作 | `NotAllowed` / `BlackList` / `WhiteList` |
| `URLCnt` | URL 规则条数 | `1` |
| `URL0`~`URL31` | URL 内容 | `http://example.com` |
| `Enable` | 开关 | `1` / `0` |

### Week 周历编码

7 位二进制，**高位到低位依次为 `Su Mo Tu We Th Fr Sa`**，转十进制：

- 每天：`1111111` = `127`
- 仅周六周日：`1000001` = `65`
- 仅周一：`0100000` = `32`

### 新增 / 修改（POST）

```
POST /common_page/ParentCtrl_lua.lua
Check: sha256(body)
Content-Type: application/x-www-form-urlencoded
X-Requested-With: XMLHttpRequest

IF_ACTION=Apply&Name=<名称>&ChildId=<MAC>&Week=<周历>&StartHour=<时>&StartMin=<分>
&EndHour=<时>&EndMin=<分>&FilterMode=<模式>&Enable=<1|0>&_InstID=<-1|实例ID>
[&URLCnt=<n>&URL0=<url>&URL1=<url>...]&_sessionTOKEN=<token>
```

- 新增：`_InstID=-1`；修改：`_InstID=<已存在实例ID>`
- **`ChildId` MAC 必须是路由器已关联的设备 MAC**，任意 MAC 会返回 `IF_ERRORPARAM=ChildId` 校验失败
- `FilterMode=NotAllowed` 时 URL 字段不提交
- `FilterMode=BlackList/WhiteList` 时需携带 `URLCnt` 与 `URL0`~`URLn-1`

### 删除（POST）

```
IF_ACTION=Delete&_InstID=<实例ID>&Name=<名称>&ChildId=<MAC>&...&_sessionTOKEN=<token>
```

### 开关（POST）

```
IF_ACTION=Apply&Enable=<1|0>&_InstID=<实例ID>&_sessionTOKEN=<token>
```

## 注意事项

1. **SID 必须用登录后下发的值**。使用登录前旧 SID 访问功能接口会返回 `SessionTimeout`（页面 HTML 内嵌 `<IF_ERRORSTR>SessionTimeout</IF_ERRORSTR>`）。
2. `Check` 头 = `sha256(body)` 是硬性要求，缺失会被拒绝。
3. `_sessionTmpToken` 取自功能页 HTML 中最后一次赋值，需反转义 `\xNN` 序列。
4. 所有 `Cookie` 需同时携带 `SID` 与 `_TESTCOOKIESUPPORT=1`。
5. 请求统一带 `--insecure`（HTTP 明文亦可，路由器无 HTTPS 证书）。
6. 本路由器为 `ZTE web server 1.0 ZTE corp 2015.`，接口可能随固件版本变化，异常时重新抓取功能页 JS 比对。
