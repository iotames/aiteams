"""
Chromedp —— 基于 Chrome DevTools Protocol（CDP）的浏览器调试辅助库。

用法：
    from scripts.chromedp import chromedp_launch, CDPClient

    proc = chromedp_launch(url="http://127.0.0.1:5000")
    client = CDPClient(port=9222, url_filter="127.0.0.1:5000")
    client.screenshot("/tmp/page.png")
    logs = client.get_console_logs()
    title = client.evaluate("document.title")
    client.close()
    os.kill(proc.pid, signal.SIGTERM)
"""

import json
import time
import base64
import urllib.request
import urllib.parse
import subprocess
import os
import tempfile
import websocket


# ─── 错误层级 ────────────────────────────────────────────

class CDPError(Exception):
    """CDP 操作的基础异常。"""
    pass

class CDPConnectionError(CDPError):
    """WebSocket 连接或传输失败。"""
    pass

class CDPTimeoutError(CDPError):
    """CDP 命令超时。"""
    pass

class CDPJSError(CDPError):
    """JavaScript 执行错误。"""
    pass


# ─── Chrome 启动器 ───────────────────────────────────────

def chromedp_find_chrome(browser="auto"):
    """定位系统中已安装的 Chrome/Edge 可执行文件。

    参数：
        browser: ``"auto"``（默认，全量扫描）、``"chrome"``（仅 Chrome）、
                 ``"edge"``（仅 Edge）。

    支持 Linux（APT/Snap/Linglong）与 Windows（Chrome/Edge 标准路径）；
    Windows 标准路径找不到时回退到 ``where`` 命令。
    返回（启动命令前缀列表, 可执行文件路径），找不到时抛出 FileNotFoundError。
    """
    browser = browser.lower().strip()
    if browser not in ("auto", "chrome", "edge"):
        raise ValueError(f"browser must be 'auto', 'chrome', or 'edge', got {browser!r}")

    # ── Linux 路径（仅 Chrome/Chromium）──
    if browser in ("auto", "chrome"):
        linux_candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
            "/opt/google/chrome/google-chrome",
        ]
        for lp in linux_candidates:
            if os.path.exists(lp):
                return ([], lp)

        # ── Linux linglong（仅 Chrome）──
        import shutil
        llcli = shutil.which("ll-cli")
        if llcli:
            layers_dir = "/var/lib/linglong/layers"
            if os.path.isdir(layers_dir):
                import glob as _glob
                entries = sorted(_glob.glob(os.path.join(
                    layers_dir, "*", "files", "bin", "google", "chrome", "google-chrome"
                )))
                if entries:
                    return ([llcli, "run", "cn.google.chrome", "--"],
                            "/opt/apps/cn.google.chrome/files/bin/google/chrome/google-chrome")

    # ── Windows 路径 ──
    if os.name == "nt":
        user_profile = os.environ.get("USERPROFILE", "")

        chrome_candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.join(user_profile, r"AppData\Local\Google\Chrome\Application\chrome.exe"),
            os.path.join(user_profile, r"AppData\Local\MyChrome\Chrome\Application\chrome.exe"),
        ]
        edge_candidates = [
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            os.path.join(user_profile, r"AppData\Local\Microsoft\Edge\Application\msedge.exe"),
        ]

        win_candidates = []
        if browser in ("auto", "chrome"):
            win_candidates.extend(chrome_candidates)
        if browser in ("auto", "edge"):
            win_candidates.extend(edge_candidates)

        for wp in win_candidates:
            if os.path.exists(wp):
                return ([], wp)

        # ── Windows 回退：``where`` 命令 ──
        where_names = []
        if browser in ("auto", "chrome"):
            where_names.extend(["chrome", "google-chrome"])
        if browser in ("auto", "edge"):
            where_names.append("msedge")

        for name in where_names:
            try:
                result = subprocess.run(
                    ["where", name],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    path = result.stdout.strip().split("\n")[0].strip()
                    if path and os.path.exists(path):
                        return ([], path)
            except Exception:
                continue

    raise FileNotFoundError(
        "Chrome/Edge not found. Ask the user where the browser is installed "
        "(e.g. /usr/bin/google-chrome, snap, linglong, custom path on Linux; "
        "Chrome or Edge standard install path on Windows)."
    )
def chromedp_launch(
    url="http://127.0.0.1:5000",
    port=9222,
    user_data_dir=None,
    extra_flags=None,
    timeout=5,
    headless=False,
    browser="auto",
):
    """以远程调试模式启动 Chrome/Edge。

    参数：
        url: 初始导航地址。
        port: 远程调试端口。
        user_data_dir: 自定义用户数据目录（默认自动创建临时目录）。
        extra_flags: 附加命令行参数。
        timeout: 每次等待调试端口就绪的秒数。
        headless: 强制无头模式（否则按显示环境自动判断）。
        browser: ``"auto"``（默认）、``"chrome"`` 或 ``"edge"``。

    自动检测显示环境：Windows 桌面默认有头模式；Linux 检查 DISPLAY/
    WAYLAND_DISPLAY 环境变量。传 headless=True 可强制无头。
    调试端口最多重试连接 3 次；返回 Popen 句柄，调用方负责结束进程。
    """
    if user_data_dir is None:
        user_data_dir = tempfile.mkdtemp(prefix="chromedp-")

    prefix, binary = chromedp_find_chrome(browser=browser)
    cmd = [*prefix, binary]

    # Windows: desktop headed by default; Linux: check DISPLAY env
    if os.name == "nt":
        has_display = True
    else:
        has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    use_headless = headless or not has_display

    flags = [
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-gpu-driver-bug-workarounds",
    ]
    if use_headless:
        flags.append("--headless=new")
    flags.append(url)

    if extra_flags:
        flags.extend(extra_flags)

    cmd.extend(flags)
    proc = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    for attempt in range(3):
        time.sleep(timeout if attempt == 0 else 2)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2)
            return proc
        except Exception:
            if attempt == 2:
                raise ConnectionError(
                    f"Chrome started (PID {proc.pid}) but debug port {port} "
                    "not responding."
                )
    return proc


# ─── CDP 客户端 ──────────────────────────────────────────

class CDPClient:
    """通过 CDP 连接 Chrome。所有事件都会缓冲，避免丢失。"""

    def __init__(self, port=9222, host="127.0.0.1", url_filter=None, timeout=10,
                 viewport=None):
        self.port = port
        self.host = host
        self.ws = None
        self._msg_id = 0
        self._timeout = timeout
        self._event_buffer = []
        self._target_id = None
        self._connect(url_filter, viewport=viewport)

    # ─── 连接管理 ──────────────────────────────────────

    def _connect(self, url_filter=None, viewport=None):
        tabs_url = f"http://{self.host}:{self.port}/json"
        try:
            tabs = json.loads(urllib.request.urlopen(tabs_url, timeout=self._timeout).read())
        except Exception as e:
            raise CDPConnectionError(
                f"Cannot connect to CDP at {self.host}:{self.port}: {e}"
            )

        target = None
        if url_filter:
            for t in tabs:
                if url_filter in t.get("url", ""):
                    target = t
                    break
        if not target and tabs:
            target = tabs[0]
        if not target:
            raise CDPConnectionError(f"No page found on CDP port {self.port}")

        self._target_id = target["id"]
        self.ws = websocket.create_connection(
            target["webSocketDebuggerUrl"], timeout=self._timeout
        )
        self._send("Page.enable")
        self._send("Console.enable")
        self._send("Log.enable")
        self._send("Network.enable")

        if viewport:
            self.set_viewport(*viewport)
        elif not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            self.set_viewport(1280, 720)

    def _reconnect_ws(self):
        """连接断开后重新建立到同一目标的 WebSocket 连接。"""
        tabs_url = f"http://{self.host}:{self.port}/json/{self._target_id}"
        info = json.loads(urllib.request.urlopen(tabs_url, timeout=5).read())
        ws_url = info.get("webSocketDebuggerUrl")
        if not ws_url:
            raise CDPConnectionError("Cannot reconnect: no WebSocket URL")

        old_ws = self.ws
        self.ws = websocket.create_connection(ws_url, timeout=self._timeout)
        self._event_buffer.clear()

        for method in ("Page.enable", "Console.enable", "Log.enable", "Network.enable"):
            self._msg_id += 1
            self.ws.send(json.dumps({"id": self._msg_id, "method": method}))
            self._recv_response(self._msg_id)

        if old_ws:
            try:
                old_ws.close()
            except Exception:
                pass

    def _send(self, method, params=None):
        """发送 CDP 命令并返回响应。

        非响应消息（事件）缓冲到 self._event_buffer，避免数据丢失；
        WebSocket 出错时自动重试一次。
        """
        self._msg_id += 1
        msg = {"id": self._msg_id, "method": method}
        if params:
            msg["params"] = params

        for attempt in range(2):
            try:
                self.ws.send(json.dumps(msg))
                return self._recv_response(msg["id"])
            except websocket.WebSocketException as e:
                if attempt == 1:
                    raise CDPConnectionError(
                        f'CDP command "{method}" failed after retry: {e}'
                    )
                self._reconnect_ws()
                # 重连期间 _reconnect_ws 已推进 _msg_id，重新同步 msg id
                msg["id"] = self._msg_id

    def _recv_response(self, msg_id):
        """Receive responses until the one matching msg_id arrives.

        Events (no 'id' field) are buffered. Raises CDPTimeoutError or
        CDPConnectionError on failure.
        """
        deadline = time.time() + self._timeout
        while time.time() < deadline:
            self.ws.settimeout(deadline - time.time())
            try:
                resp = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                raise CDPTimeoutError(f'CDP command timed out after {self._timeout}s')
            except websocket.WebSocketException as e:
                raise CDPConnectionError(f"WebSocket error: {e}")

            rid = resp.get("id")
            if rid == msg_id:
                if "error" in resp:
                    raise CDPError(f'CDP error: {resp["error"]}')
                return resp
            elif rid is None and resp.get("method"):
                self._event_buffer.append(resp)
        raise CDPTimeoutError(f'CDP command timed out after {self._timeout}s')

    def _collect_events(self, timeout=0.5):
        """读取缓冲事件并从 WebSocket 接收新事件。

        返回自上次调用以来的全部事件（console、network 等）。
        """
        events = list(self._event_buffer)
        self._event_buffer.clear()

        self.ws.settimeout(timeout)
        try:
            while True:
                resp = json.loads(self.ws.recv())
                if resp.get("method"):
                    events.append(resp)
        except (websocket.WebSocketTimeoutException, websocket.WebSocketException):
            pass

        return events

    # ─── 标签页管理 ────────────────────────────────────

    def list_tabs(self):
        """列出所有已打开的标签页。"""
        try:
            tabs_url = f"http://{self.host}:{self.port}/json"
            tabs = json.loads(urllib.request.urlopen(tabs_url, timeout=5).read())
            return [
                {"id": t["id"], "title": t.get("title", ""),
                 "url": t.get("url", ""), "type": t.get("type", "")}
                for t in tabs if t.get("type") in ("page",)
            ]
        except Exception as e:
            raise CDPError(f"Failed to list tabs: {e}")

    def switch_to_tab(self, target_id_or_filter):
        """按 ID 或 URL 过滤条件切换标签页。

        成功返回 True，找不到时抛出 CDPError。
        """
        tabs = self.list_tabs()
        target = None

        for t in tabs:
            if t["id"] == target_id_or_filter:
                target = t
                break

        if not target:
            for t in tabs:
                if target_id_or_filter in t["url"]:
                    target = t
                    break

        if not target:
            raise CDPError(f"Tab matching '{target_id_or_filter}' not found")

        new_ws_url = f"http://{self.host}:{self.port}/json/{target['id']}"
        try:
            info = json.loads(urllib.request.urlopen(new_ws_url, timeout=5).read())
            ws_url = info.get("webSocketDebuggerUrl")
            if not ws_url:
                raise CDPError("No WebSocket URL for tab")

            old_ws = self.ws
            self.ws = websocket.create_connection(ws_url, timeout=self._timeout)
            self._target_id = target["id"]
            self._event_buffer.clear()
            self._send("Page.enable")
            self._send("Console.enable")
            self._send("Log.enable")
            self._send("Network.enable")
            if old_ws:
                try:
                    old_ws.close()
                except Exception:
                    pass
            return True
        except Exception as e:
            raise CDPError(f"Failed to switch tab: {e}")

    def new_tab(self, url=None):
        """打开新标签页；传入 url 时导航到该地址。"""
        new_url = f"http://{self.host}:{self.port}/json/new"
        if url:
            new_url += "?" + urllib.parse.urlencode({"url": url})
        try:
            # Chrome 88+ 要求 PUT 方法创建新标签页
            req = urllib.request.Request(new_url, method="PUT")
            info = json.loads(urllib.request.urlopen(req, timeout=5).read())
            old_ws = self.ws
            self.ws = websocket.create_connection(
                info["webSocketDebuggerUrl"], timeout=self._timeout
            )
            self._target_id = info["id"]
            self._event_buffer.clear()
            self._send("Page.enable")
            self._send("Console.enable")
            self._send("Log.enable")
            self._send("Network.enable")
            if old_ws:
                try:
                    old_ws.close()
                except Exception:
                    pass
            return info["id"]
        except Exception as e:
            raise CDPError(f"Failed to create new tab: {e}")

    # ─── 页面操作 ────────────────────────────────────────

    def set_viewport(self, width=1280, height=720):
        """设置浏览器视口尺寸。"""
        self._send("Emulation.setDeviceMetricsOverride", {
            "width": width, "height": height,
            "deviceScaleFactor": 1, "mobile": False,
        })

    def screenshot(self, path):
        res = self._send("Page.captureScreenshot", {"format": "png", "fromSurface": True})
        with open(path, "wb") as f:
            f.write(base64.b64decode(res["result"]["data"]))
        return path

    def print_to_pdf(self, path, *, paper_width=210, paper_height=297,
                     margin_top=24, margin_bottom=22, margin_left=18,
                     margin_right=18, page_ranges="", header_template="",
                     footer_template="", display_header_footer=False,
                     print_background=True, prefer_css_page_size=False,
                     landscape=False, scale=1.0):
        """通过 CDP Page.printToPDF 将当前页面打印为 PDF。

        参数：
            path: 输出 PDF 文件路径。
            paper_width/paper_height: 纸张尺寸（毫米，默认 A4）。
            margin_*: 页面边距（毫米）。
            page_ranges: 页码范围，如 "1-2,4"，空串表示全部。
            header_template/footer_template: 页眉/页脚 HTML 模板，
                仅在 display_header_footer=True 时生效。
            display_header_footer: 是否显示自定义页眉页脚。
            print_background: 是否打印 CSS 背景。
            prefer_css_page_size: 是否遵循 CSS @page 尺寸/边距（慎用，
                会覆盖本方法传入的纸张和边距参数）。
            landscape: 横向打印。
            scale: 页面缩放比例。

        返回：
            输出 PDF 文件路径。
        """
        mm_to_inch = 1 / 25.4
        params = {
            "landscape": landscape,
            "displayHeaderFooter": display_header_footer,
            "printBackground": print_background,
            "scale": scale,
            "paperWidth": paper_width * mm_to_inch,
            "paperHeight": paper_height * mm_to_inch,
            "marginTop": margin_top * mm_to_inch,
            "marginBottom": margin_bottom * mm_to_inch,
            "marginLeft": margin_left * mm_to_inch,
            "marginRight": margin_right * mm_to_inch,
            "preferCSSPageSize": prefer_css_page_size,
            "transferMode": "ReturnAsBase64",
        }
        if page_ranges:
            params["pageRanges"] = page_ranges
        if display_header_footer:
            params["headerTemplate"] = header_template
            params["footerTemplate"] = footer_template
        res = self._send("Page.printToPDF", params)
        data = res.get("result", {}).get("data", "")
        if not data:
            raise CDPError("Page.printToPDF returned no data")
        with open(path, "wb") as f:
            f.write(base64.b64decode(data))
        return path

    def screenshot_element(self, selector, path):
        res = self._send("Runtime.evaluate", {
            "expression": f"""(function() {{
                const el = document.querySelector({json.dumps(selector)});
                if (!el) throw new Error('Element not found: ' + {json.dumps(selector)});
                const {{x, y, width, height}} = el.getBoundingClientRect();
                return JSON.stringify({{x, y, width, height}});
            }})()"""
        })
        clip = json.loads(res["result"]["result"]["value"])
        res = self._send("Page.captureScreenshot", {
            "format": "png", "fromSurface": True, "clip": clip
        })
        with open(path, "wb") as f:
            f.write(base64.b64decode(res["result"]["data"]))
        return path

    def navigate(self, url):
        self._send("Page.navigate", {"url": url})

    def reload(self):
        self._send("Page.reload")

    def get_url(self):
        res = self._send("Runtime.evaluate", {"expression": "window.location.href"})
        return res["result"]["result"].get("value")

    def get_html(self, selector=None):
        if selector:
            expr = f"document.querySelector({json.dumps(selector)})?.outerHTML || null"
        else:
            expr = "document.documentElement.outerHTML"
        return self.evaluate(expr)

    def get_cookies(self):
        res = self._send("Network.getCookies")
        return [
            {"name": c["name"], "value": c["value"], "domain": c["domain"],
             "path": c["path"], "secure": c.get("secure", False)}
            for c in res.get("result", {}).get("cookies", [])
        ]

    def clear_cookies(self):
        self._send("Network.clearBrowserCookies")

    def get_local_storage(self, key=None):
        if key:
            return self.evaluate(f"localStorage.getItem({json.dumps(key)})")
        return self.evaluate("JSON.stringify(Object.fromEntries(Object.entries(localStorage)))")

    def set_local_storage(self, key, value):
        return self.evaluate(f"localStorage.setItem({json.dumps(key)}, {json.dumps(value)})")

    def get_session_storage(self, key=None):
        if key:
            return self.evaluate(f"sessionStorage.getItem({json.dumps(key)})")
        return self.evaluate("JSON.stringify(Object.fromEntries(Object.entries(sessionStorage)))")

    def wait_for_navigation(self, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            state = self.evaluate("document.readyState")
            if state == "complete":
                return True
            time.sleep(0.2)
        return False

    # ─── JS 执行 ─────────────────────────────────────────

    def evaluate(self, expression, await_promise=False):
        res = self._send(
            "Runtime.evaluate",
            {"expression": expression, "awaitPromise": await_promise},
        )
        result = res.get("result", {})
        if "exceptionDetails" in result:
            exc = result["exceptionDetails"]
            text = exc.get("text", "")
            if "exception" in exc:
                text += ": " + exc["exception"].get("description", "")
            raise CDPJSError(text)
        return result.get("result", {}).get("value")

    def evaluate_async(self, expression):
        return self.evaluate(expression, await_promise=True)

    # ─── DOM 查询 ────────────────────────────────────────

    def query_selector(self, selector):
        return self.evaluate(
            f"""(function() {{
                const el = document.querySelector({json.dumps(selector)});
                return el ? el.innerText : null;
            }})()"""
        )

    def query_selector_all(self, selector):
        result = self.evaluate(
            f"JSON.stringify(Array.from(document.querySelectorAll({json.dumps(selector)})).map(el => el.innerText))"
        )
        if result:
            return json.loads(result)
        return []

    def is_visible(self, selector):
        """检查元素是否可见（存在、非隐藏、有尺寸）。"""
        return self.evaluate(
            f"""(function() {{
                const el = document.querySelector({json.dumps(selector)});
                if (!el) return false;
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') return false;
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            }})()"""
        )

    def is_enabled(self, selector):
        """检查元素是否未被禁用。"""
        return self.evaluate(
            f"""(function() {{
                const el = document.querySelector({json.dumps(selector)});
                return el ? !el.disabled : false;
            }})()"""
        )

    def get_attribute(self, selector, attr):
        """获取元素的属性值。"""
        return self.evaluate(
            f"""(function() {{
                const el = document.querySelector({json.dumps(selector)});
                return el ? el.getAttribute({json.dumps(attr)}) : null;
            }})()"""
        )

    # ─── DOM 操作 ────────────────────────────────────────

    def click(self, selector):
        return self.evaluate(
            f"""(function() {{
                const el = document.querySelector({json.dumps(selector)});
                if (!el) throw new Error('Element not found: ' + {json.dumps(selector)});
                el.click();
                return true;
            }})()"""
        )

    def fill(self, selector, value):
        escaped = json.dumps(value)
        return self.evaluate(
            f"""(function() {{
                const el = document.querySelector({json.dumps(selector)});
                if (!el) throw new Error('Element not found: ' + {json.dumps(selector)});
                el.value = {escaped};
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                return true;
            }})()"""
        )

    def clear(self, selector):
        """清空 input/textarea 输入框。"""
        return self.evaluate(
            f"""(function() {{
                const el = document.querySelector({json.dumps(selector)});
                if (!el) throw new Error('Element not found: ' + {json.dumps(selector)});
                el.value = '';
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                return true;
            }})()"""
        )

    def hover(self, selector):
        """触发元素的 mouseover 事件。"""
        return self.evaluate(
            f"""(function() {{
                const el = document.querySelector({json.dumps(selector)});
                if (!el) throw new Error('Element not found: ' + {json.dumps(selector)});
                el.dispatchEvent(new MouseEvent('mouseover', {{bubbles: true}}));
                return true;
            }})()"""
        )

    def select_option(self, selector, value):
        escaped = json.dumps(value)
        return self.evaluate(
            f"""(function() {{
                const el = document.querySelector({json.dumps(selector)});
                if (!el) throw new Error('Element not found: ' + {json.dumps(selector)});
                el.value = {escaped};
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                return true;
            }})()"""
        )

    def wait_for_selector(self, selector, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            found = self.evaluate(
                f"document.querySelector({json.dumps(selector)}) !== null"
            )
            if found:
                return True
            time.sleep(0.2)
        return False

    def wait_for_text(self, text, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            body = self.evaluate("document.body.innerText")
            if body and text in body:
                return True
            time.sleep(0.2)
        return False

    def wait_for_function(self, condition, timeout=5, interval=0.2):
        """等待 JS 表达式返回真值。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = self.evaluate(condition)
            if result:
                return True
            time.sleep(interval)
        return False

    def scroll_into_view(self, selector):
        return self.evaluate(
            f"""(function() {{
                const el = document.querySelector({json.dumps(selector)});
                if (!el) throw new Error('Element not found: ' + {json.dumps(selector)});
                el.scrollIntoView({{behavior: 'instant', block: 'center'}});
                return true;
            }})()"""
        )

    def scroll_to_bottom(self):
        """滚动到页面底部。"""
        return self.evaluate("window.scrollTo(0, document.body.scrollHeight); true;")

    def scroll_to_top(self):
        """滚动到页面顶部。"""
        return self.evaluate("window.scrollTo(0, 0); true;")

    # ─── 对话框处理 ─────────────────────────────────────

    def handle_dialog(self, accept=True, prompt_text=""):
        self._send("Page.handleJavaScriptDialog", {
            "accept": accept,
            "promptText": prompt_text if prompt_text else None,
        })

    def click_and_handle_dialog(self, selector, accept=True, delay=0.5):
        self.click(selector)
        time.sleep(delay)
        self.handle_dialog(accept=accept)

    # ─── 日志 & 网络 ─────────────────────────────────────

    def get_events(self, timeout=1.0):
        """获取自上次调用以来的全部 CDP 事件（console、network 等）。

        返回原始事件字典；需要过滤视图时用 get_console_logs() /
        get_network_errors()。
        """
        return self._collect_events(timeout=timeout)

    def get_console_logs(self, timeout=1.0):
        events = self._collect_events(timeout=timeout)
        logs = []
        for ev in events:
            if ev["method"] == "Console.messageAdded":
                msg = ev["params"]["message"]
            elif ev["method"] == "Log.entryAdded":
                msg = ev["params"]["entry"]
            else:
                continue
            logs.append({
                "level": msg.get("level", "log"),
                "text": msg.get("text", ""),
            })
        return logs

    def get_console_errors(self, timeout=1.0):
        return [
            log for log in self.get_console_logs(timeout=timeout)
            if log["level"] in ("error", "warning")
        ]

    def get_network_errors(self, timeout=1.0):
        events = self._collect_events(timeout=timeout)
        # Network.loadingFailed 事件不含 URL，需用 requestId 关联
        # Network.requestWillBeSent 记录获取请求地址
        url_by_id = {
            ev["params"]["requestId"]: ev["params"]["request"].get("url", "")
            for ev in events
            if ev["method"] == "Network.requestWillBeSent"
        }
        return [
            {
                "url": url_by_id.get(ev["params"].get("requestId", ""), ""),
                "errorText": ev["params"].get("errorText", ""),
                "type": ev["params"].get("type", ""),
            }
            for ev in events
            if ev["method"] == "Network.loadingFailed"
        ]

    def get_network_requests(self, timeout=1.0):
        """获取全部网络请求及其响应。"""
        events = self._collect_events(timeout=timeout)
        requests = {}
        for ev in events:
            if ev["method"] == "Network.requestWillBeSent":
                req = ev["params"]["request"]
                requests[ev["params"]["requestId"]] = {
                    "url": req.get("url", ""),
                    "method": req.get("method", ""),
                    "type": ev["params"].get("type", ""),
                    "status": None,
                }
            elif ev["method"] == "Network.responseReceived":
                rid = ev["params"]["requestId"]
                if rid in requests:
                    requests[rid]["status"] = ev["params"]["response"]["status"]
        return [r for r in requests.values()]

    def wait(self, seconds):
        time.sleep(seconds)
        self._collect_events(timeout=0.1)

    # ─── 生命周期 ───────────────────────────────────────

    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
