---
name: chromedp
description: >-
  通过 Chrome DevTools Protocol (CDP) 控制系统已安装的 Chrome/Edge 浏览器进行 debug。
  用于截图、JS 错误诊断、DOM 状态检查、网络请求分析、表单交互。
  当用户要求"截图看看"、"检查 JS 错误"、"提取页面文字"、"验证接口"、"用浏览器打开看看"、"打开浏览器看看"时触发。
  也适用于填写表单、点击按钮、检查网络请求、提取页面信息等浏览器自动化操作。
  自动检测系统已安装的 Chrome/Edge，通过远程调试接口 WebSocket 连接，极轻量无额外依赖。
metadata:
  version: 1.0.0
---

## 设计原则

- **极轻量**：唯一依赖 `websocket-client` (~82KB)，复用系统已安装的 Chrome
- **CDP 原生**：Playwright/Puppeteer 底层也是 CDP，我们直接调协议，无中间层
- **面向 debug**：专为"发现 bug → 修项目 → 重启验证"闭环设计
- **不启动 web 服务**：只连接已有页面，避免端口冲突

## 环境要求

- Python 3.7+
- Chrome/Chromium / Edge 已安装（Linux：系统级或 snap/linglong；Windows：标准安装路径）
- `pip install websocket-client`
- 显示模式：Windows 桌面环境默认有头模式（用户可观察浏览器操作）；Linux 需 `DISPLAY` 环境变量（`DISPLAY=:0` 或 `WAYLAND_DISPLAY`）；传 `headless=True` 强制无头

## 使用方法

### 1. 查找 Chrome

```python
from scripts.chromedp import chromedp_find_chrome
prefix, binary_path = chromedp_find_chrome()          # 自动检测
prefix, binary_path = chromedp_find_chrome(browser="chrome")  # 指定 Chrome
prefix, binary_path = chromedp_find_chrome(browser="edge")    # 指定 Edge
```

自动检测系统已安装的 Chrome/Edge（支持 Linux 和 Windows）。
使用 `browser="chrome"` 或 `browser="edge"` 指定浏览器类型。
如果找不到，**必须问用户**，不要直接放弃。

### 2. 启动 Chrome

```python
from scripts.chromedp import chromedp_launch, CDPClient
import os, signal

proc = chromedp_launch(
    url="http://127.0.0.1:5000",
    port=9222,
    timeout=5,
)
proc = chromedp_launch(browser="edge")  # 指定用 Edge
proc = chromedp_launch(browser="chrome")  # 指定用 Chrome
```

- 桌面环境（Windows）默认有头模式，用户可观察浏览器操作
- Linux 自动检测 `DISPLAY`/`WAYLAND_DISPLAY`，有显示器时有头
- 传 `headless=True` 强制无头
- 可传 `browser="chrome"` 或 `browser="edge"` 指定浏览器
- 最大重试 3 次等待调试端口就绪

### 3. 连接 CDP 并调试

```python
client = CDPClient(port=9222, url_filter="127.0.0.1:5000")

# 截图
client.screenshot("/tmp/page.png")

# 提取文本
title = client.evaluate("document.title")
body = client.evaluate("document.body.innerText")

# 检查 JS 错误
errors = client.get_console_errors()
for err in errors:
    print(f"[{err['level']}] {err['text']}")

# 检查网络失败
net_fails = client.get_network_errors()
for fail in net_fails:
    print(f"{fail['url']}: {fail['errorText']}")

client.close()
# 关闭浏览器：Windows 用 terminate()，Linux/macOS 用 SIGTERM
if os.name == "nt":
    proc.terminate()
else:
    os.kill(proc.pid, signal.SIGTERM)
```

无头模式下自动设置 viewport `1280x720`，确保 `getBoundingClientRect()` 返回正确尺寸。

## 错误层级

所有异常继承自 `CDPError`，可按需捕获：

| 异常 | 触发场景 |
|---|---|
| `CDPConnectionError` | WebSocket 连接失败、Chrome 未启动、端口无法访问 |
| `CDPTimeoutError` | CDP 命令超时（默认 10s） |
| `CDPJSError` | `evaluate()` / `evaluate_async()` 中 JS 报错 |
| `CDPError` | 其他 CDP 协议错误（基类，catch 全部） |

## CDPClient 方法参考

### 标签页管理

| 方法 | 说明 |
|---|---|
| `list_tabs()` | 列出所有打开的标签页 |
| `switch_to_tab(id_or_filter)` | 按 ID 或 URL 过滤切换到指定标签页 |
| `new_tab(url=None)` | 打开新标签页，可选打开 URL |

### 页面操作

| 方法 | 说明 |
|---|---|
| `set_viewport(width, height)` | 设置浏览器视口尺寸 |
| `screenshot(path)` | 截取当前页面 PNG |
| `screenshot_element(selector, path)` | 截取指定元素的截图 |
| `navigate(url)` | 导航到新 URL |
| `reload()` | 重新加载当前页 |
| `get_url()` | 获取当前页面 URL |
| `get_html(selector=None)` | 获取页面或元素的 outerHTML |

### JS 执行

| 方法 | 说明 |
|---|---|
| `evaluate(expr)` | 执行 JS 表达式，返回结果值。JS 报错时抛 `CDPJSError` |
| `evaluate_async(expr)` | 执行 async JS 表达式并 await（调用后端 API 常用） |

### DOM 查询

| 方法 | 说明 |
|---|---|
| `query_selector(selector)` | 获取匹配元素的 innerText，没找到返回 None |
| `query_selector_all(selector)` | 获取所有匹配元素的 innerText 列表 |
| `is_visible(selector)` | 元素可见（存在且 display/visibility 非 hidden，有尺寸） |
| `is_enabled(selector)` | 元素未禁用（!el.disabled） |
| `get_attribute(selector, attr)` | 获取元素属性值 |

### DOM 操作

| 方法 | 说明 |
|---|---|
| `click(selector)` | 点击匹配元素 |
| `fill(selector, value)` | 填写 input/textarea（触发 input + change 事件） |
| `clear(selector)` | 清空 input/textarea |
| `hover(selector)` | 触发 mouseover 事件 |
| `select_option(selector, value)` | 选择 `<select>` 中的选项 |
| `scroll_into_view(selector)` | 滚动到元素可见 |
| `scroll_to_bottom()` | 滚动到页面底部 |
| `scroll_to_top()` | 滚动到页面顶部 |

### 等待

| 方法 | 说明 |
|---|---|
| `wait_for_selector(selector, timeout=5)` | 等待 DOM 中出现匹配元素 |
| `wait_for_text(text, timeout=5)` | 等待页面中出现指定文本 |
| `wait_for_function(condition, timeout=5)` | 等待 JS 表达式返回 truthy 值 |
| `wait_for_navigation(timeout=5)` | 等待页面加载完成（readyState=complete） |
| `wait(seconds)` | 睡眠并排干事件缓冲区 |

### 对话框

| 方法 | 说明 |
|---|---|
| `handle_dialog(accept=True, prompt_text='')` | 接受/拒绝 JS 弹窗（alert/confirm/prompt） |
| `click_and_handle_dialog(selector, accept=True, delay=0.5)` | 点击并处理弹窗的组合方法 |

### 存储

| 方法 | 说明 |
|---|---|
| `get_cookies()` | 获取所有 cookies |
| `clear_cookies()` | 清除所有 cookies |
| `get_local_storage(key=None)` | 获取 localStorage（不传 key 返回全部） |
| `set_local_storage(key, value)` | 设置 localStorage 项 |
| `get_session_storage(key=None)` | 获取 sessionStorage |

### 日志 & 网络

| 方法 | 说明 |
|---|---|
| `get_events(timeout=1)` | 获取所有原始 CDP 事件（调试用） |
| `get_console_logs(timeout=1)` | 获取所有 console 日志 |
| `get_console_errors(timeout=1)` | 仅获取 console error/warning |
| `get_network_errors(timeout=1)` | 获取网络请求失败信息 |
| `get_network_requests(timeout=1)` | 获取所有网络请求及响应状态码 |

### 生命周期

| 方法 | 说明 |
|---|---|
| `close()` | 关闭 WebSocket 连接 |

## 调试工作流

### 模板：快速诊断

```python
from scripts.chromedp import chromedp_launch, CDPClient
import os, signal, time

proc = chromedp_launch(url="http://127.0.0.1:5000", port=9222, timeout=5)
time.sleep(3)
client = CDPClient(port=9222, url_filter="127.0.0.1:5000")
time.sleep(2)

title = client.evaluate("document.title")
body = client.evaluate("document.body.innerText")
errors = client.get_console_errors(timeout=2)
net = client.get_network_errors(timeout=2)

client.close()
# 关闭浏览器：Windows 用 terminate()，Linux/macOS 用 SIGTERM
if os.name == "nt":
    proc.terminate()
else:
    os.kill(proc.pid, signal.SIGTERM)
```

### 模板：导航各页面检查

```python
pages = ["#/home", "#/list", "#/detail", "#/settings"]
for page in pages:
    client.evaluate(f'window.location.hash = "{page}"')
    time.sleep(2)
    text = client.query_selector("#app-main")
    errors = client.get_console_errors(timeout=1)
    print(f"{page}: errors={len(errors)}, text={text[:80]}")
```

### 模板：前端 API 调用（异步）

```python
result = client.evaluate_async("""
(async () => {
    try {
        const r = await fetch("/api/items", {headers: {Accept: "application/json"}});
        return await r.text();
    } catch(e) { return "ERR:" + e.message; }
})()
""")
print(result)
```

### 模板：全链路业务验证

```python
ops = [
    ("登录", 'window.app.login({user:"admin", password:"x"})'),
    ("拉取列表", 'window.app.loadItems({page:1})'),
    ("获取详情", 'window.app.getItem(1)'),
    ("保存修改", 'window.app.saveItem({id:1, name:"demo"})'),
    ("状态验证", 'window.app.getState()'),
]
for name, js in ops:
    r = client.evaluate_async(f'(async()=>{{try{{const r=await {js};return JSON.stringify(r.data)}}catch(e){{return"ERR:"+e.message}}}})()')
    print(f"{name}: {r[:60]}")
```

### 模板：表单交互

```python
client.wait_for_selector("#search-input", timeout=3)
client.fill("#search-input", "关键字")
client.click("#search-btn")
time.sleep(1)
results = client.query_selector("#results")
errors = client.get_console_errors(timeout=1)
```

## 注意事项

1. **Chrome 找不到时，先问用户** — 可能安装在自定义路径或容器中
2. **不要启动 web 服务** — 只连接已有的页面
3. **截图对我不可见** — 我是纯文本模型，只能通过 evaluate 提取 DOM 文本来"看"页面
4. **`evaluate` 是核心工具** — 可以读 DOM、调 API、触发事件，比截图有用
5. **杀 Chrome（Linux）用 `killall -9 chrome`** — `pkill -f "pattern"` 和 `ps | awk | xargs kill` 在有大量子进程（renderer/gpu/utility）时极慢（>10s），因为逐个匹配和发信号。`killall -9 chrome` 一次杀所有 `chrome` 命名进程，<1s。注意也会杀 VS Code 等嵌入 Chrome，在自动化测试环境无影响。Windows 环境见下一条。
6. **Windows 关闭浏览器用 `proc.terminate()`** — Windows 上 `os.kill(pid, signal.SIGTERM)` 可能无法正确终止进程树，优先使用 `proc.terminate()` 或 `taskkill /f /pid`。前面所有示例已按平台统一处理。
