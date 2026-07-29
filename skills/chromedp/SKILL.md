---
name: chromedp
description: >-
  通过 Chrome DevTools Protocol (CDP) 控制系统已安装的 Chrome 浏览器进行 debug。
  用于截图、JS 错误诊断、DOM 状态检查、网络请求分析、表单交互。
  当用户要求"截图看看"、"检查 JS 错误"、"提取页面文字"、"验证接口"、"用浏览器打开看看"时触发。
  自动检测 Chrome 位置（APT / Snap / linglong / 标准路径），通过远程调试接口 WebSocket 连接。
  仅依赖 websocket-client (~82KB)，不安装 Playwright/Puppeteer/Selenium。
---

## 设计原则

- **极轻量**：唯一依赖 `websocket-client` (~82KB)，复用系统已安装的 Chrome
- **CDP 原生**：Playwright/Puppeteer 底层也是 CDP，我们直接调协议，无中间层
- **面向 debug**：专为"发现 bug → 修项目 → 重启验证"闭环设计
- **不启动 web 服务**：只连接已有页面，避免端口冲突

## 环境要求

- Python 3.7+
- Chrome/Chromium 已安装（系统级或容器级如 snap/linglong）
- `pip install websocket-client`
- 有头模式需要 `DISPLAY` 环境变量（`DISPLAY=:0` 或 `WAYLAND_DISPLAY`）

## 使用方法

### 1. 查找 Chrome

```python
from scripts.chromedp import chromedp_find_chrome
prefix, binary_path = chromedp_find_chrome()
```

自动检测路径（按优先级）：
- `/usr/bin/google-chrome`
- `/usr/bin/chromium` / `chromium-browser`
- `/snap/bin/chromium`
- `/opt/google/chrome/google-chrome`
- Linglong（`ll-cli run cn.google.chrome --`，自动检测层路径）

对于 linglong 容器化 Chrome，自动使用 `ll-cli run cn.google.chrome --` 作为命令前缀，确保所有启动参数穿透容器。

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
```

- 自动检测 `DISPLAY`/`WAYLAND_DISPLAY`，有显示器时有头，否则 `--headless=new`
- 可 `headless=True` 强制无头
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
os.kill(proc.pid, signal.SIGTERM)
```

无头模式下自动设置 viewport `1280x720`，确保 `getBoundingClientRect()` 返回正确尺寸。

## 核心设计

### 事件缓冲机制

> chromedp 最关键的改进：**所有 CDP 事件永不丢失**。

`_send()` 在等待命令响应时，会把收到的非响应消息（console 日志、网络事件等）自动缓冲到 `_event_buffer`。调用 `get_console_logs()` / `get_network_errors()` 时，先排干缓冲区再读新的。

### CDP 命令自动重试

`_send()` 在 WebSocket 断开时自动重连一次，重新发送命令。无需调用方处理重连逻辑。

### 无头 Viewport 自动设置

无头模式默认 viewport 为 0x0，`getBoundingClientRect()` 返回 0 尺寸，导致 `is_visible()` 误判。`CDPClient` 在连接时自动调用 `Emulation.setDeviceMetricsOverride` 设置 1280x720。

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
os.kill(proc.pid, signal.SIGTERM)
```

### 模板：导航各页面检查

```python
pages = ["#/dashboard", "#/products", "#/categories",
         "#/suppliers", "#/stock", "#/purchase-orders"]
for page in pages:
    client.evaluate(f'window.location.hash = "{page}"')
    time.sleep(2)
    text = client.query_selector("#appContent")
    errors = client.get_console_errors(timeout=1)
    print(f"{page}: errors={len(errors)}, text={text[:80]}")
```

### 模板：前端 API 调用（异步）

```python
result = client.evaluate_async("""
(async () => {
    try {
        const r = await ApiClient.getProducts({per_page: 5});
        return JSON.stringify(r.data);
    } catch(e) { return "ERR:" + e.message; }
})()
""")
print(result)
```

### 模板：全链路业务验证

```python
ops = [
    ("分类", 'ApiClient.createCategory({name:"办公"})'),
    ("单位", 'ApiClient.createUnit({name:"箱"})'),
    ("商品", 'ApiClient.createProduct({code:"P001",name:"A4纸",category_id:1,unit_id:1,...})'),
    ("采购→入库", 'ApiClient.createPurchaseOrder → receivePurchaseOrder'),
    ("销售→出库", 'ApiClient.createSaleOrder → shipSaleOrder'),
    ("库存验证", 'ApiClient.getStock'),
]
for name, js in ops:
    r = client.evaluate_async(f'(async()=>{{try{{const r=await {js};return JSON.stringify(r.data)}}catch(e){{return"ERR:"+e.message}}}})()')
    print(f"{name}: {r[:60]}")
```

### 模板：表单交互

```python
client.wait_for_selector("#searchInput", timeout=3)
client.fill("#searchInput", "关键字")
client.click("#searchBtn")
time.sleep(1)
results = client.query_selector("#dataBody")
errors = client.get_console_errors(timeout=1)
```

## 对比 Playwright

| 维度 | chromedp (本技能) | Playwright |
|---|---|---|
| 安装体积 | ~82KB (`websocket-client`) | ~50MB+ (含 Chromium) |
| 浏览器 | 复用系统 Chrome | 自带 Chromium 或系统 Chrome |
| API 风格 | CDP 原生，手动控制 | 封装好的高级 API |
| 适用场景 | 快速 debug、验证修复 | 自动化测试 CI、复杂流程 |
| 学习成本 | 需了解 CDP 概念 | 开箱即用 |

**结论**：调试阶段用 chromedp 快速验证，需要自动化回归测试再上 Playwright。

## 注意事项

1. **Chrome 找不到时，先问用户** — 可能安装在自定义路径或容器中
2. **不要启动 web 服务** — 只连接已有的页面
3. **改代码后重启服务** — 用 `kill $(lsof -ti :5000)` 停服，`nohup python start.py &` 重启。若数据库有残留数据，先 `rm -f ims.db`
4. **截图对我不可见** — 我是纯文本模型，只能通过 evaluate 提取 DOM 文本来"看"页面
5. **`evaluate` 是核心工具** — 可以读 DOM、调 API、触发事件，比截图有用
6. **杀 Chrome 用 `killall -9 chrome`** — `pkill -f "pattern"` 和 `ps | awk | xargs kill` 在有大量子进程（renderer/gpu/utility）时极慢（>10s），因为逐个匹配和发信号。`killall -9 chrome` 一次杀所有 `chrome` 命名进程，<1s。注意也会杀 VS Code 等嵌入 Chrome，在自动化测试环境无影响。
