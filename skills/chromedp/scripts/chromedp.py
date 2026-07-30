"""
Chromedp — Chrome DevTools Protocol helper for browser debugging.

Usage:
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


# ─── Error hierarchy ──────────────────────────────────────

class CDPError(Exception):
    """Base error for all CDP operations."""
    pass

class CDPConnectionError(CDPError):
    """WebSocket connection or transport failure."""
    pass

class CDPTimeoutError(CDPError):
    """CDP command timed out."""
    pass

class CDPJSError(CDPError):
    """JavaScript execution error."""
    pass


# ─── Chrome launcher ──────────────────────────────────────

def chromedp_find_chrome(browser="auto"):
    """Locate the system Chrome/Edge binary.

    Args:
        browser: ``"auto"`` (default, scan all), ``"chrome"`` (Chrome only),
                 ``"edge"`` (Edge only).

    Supports Linux (APT/Snap/Linglong) and Windows (Chrome/Edge standard paths).
    Falls back to ``where`` command on Windows when standard paths fail.
    Returns (launch_command_prefix_list, binary_path) or raises FileNotFoundError.
    """
    browser = browser.lower().strip()
    if browser not in ("auto", "chrome", "edge"):
        raise ValueError(f"browser must be 'auto', 'chrome', or 'edge', got {browser!r}")

    # ── Linux paths (Chrome/Chromium only) ──
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

        # ── Linux linglong (Chrome only) ──
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

    # ── Windows paths ──
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

        # ── Windows fallback: ``where`` command ──
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
    """Launch Chrome/Edge with remote debugging enabled.

    Args:
        url: Initial URL to navigate to.
        port: Remote debugging port.
        user_data_dir: Custom profile directory (auto tempdir if None).
        extra_flags: Additional command-line flags.
        timeout: Seconds to wait for debug port readiness per attempt.
        headless: Force headless mode (auto-detects display otherwise).
        browser: ``"auto"`` (default), ``"chrome"``, or ``"edge"``.

    Auto-detects display environment: desktop OS (Windows) defaults to headed
    mode; Linux checks DISPLAY/WAYLAND_DISPLAY environment variables.
    Pass headless=True to force headless mode regardless.

    Retries connecting to the debug port up to 3 times if Chrome is slow to start.
    Returns the Popen handle. Caller should kill it when done.
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


# ─── CDP Client ───────────────────────────────────────────

class CDPClient:
    """Connect to Chrome via CDP. All events are buffered to prevent loss."""

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
        """Re-establish WebSocket connection to the same target after a drop."""
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
        """Send a CDP command, return its response.

        Non-response messages (events) are buffered in self._event_buffer
        to prevent data loss. Retries once on WebSocket error.
        """
        self._msg_id += 1
        msg = {"id": self._msg_id, "method": method}
        if params:
            msg["params"] = params

        for attempt in range(2):
            try:
                self.ws.send(json.dumps(msg))
                return self._recv_response(self._msg_id)
            except websocket.WebSocketException as e:
                if attempt == 1:
                    raise CDPConnectionError(
                        f'CDP command "{method}" failed after retry: {e}'
                    )
                self._reconnect_ws()

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
        """Drain buffered events and read fresh ones from the WebSocket.

        Returns ALL events (console, network, etc.) since last call.
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
        """List all open tabs/pages."""
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
        """Switch to a different tab by ID or URL filter.

        Returns True on success. Raises CDPError if not found.
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
        """Open a new tab. If url is given, navigate to it."""
        new_url = f"http://{self.host}:{self.port}/json/new"
        if url:
            new_url += "?" + urllib.parse.urlencode({"url": url})
        try:
            info = json.loads(urllib.request.urlopen(new_url, timeout=5).read())
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
        """Set the browser viewport size."""
        self._send("Emulation.setDeviceMetricsOverride", {
            "width": width, "height": height,
            "deviceScaleFactor": 1, "mobile": False,
        })

    def screenshot(self, path):
        res = self._send("Page.captureScreenshot", {"format": "png", "fromSurface": True})
        with open(path, "wb") as f:
            f.write(base64.b64decode(res["result"]["data"]))
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
        """Check if an element is visible (exists, not hidden, has size)."""
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
        """Check if an element is not disabled."""
        return self.evaluate(
            f"""(function() {{
                const el = document.querySelector({json.dumps(selector)});
                return el ? !el.disabled : false;
            }})()"""
        )

    def get_attribute(self, selector, attr):
        """Get an attribute value from an element."""
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
        """Clear an input/textarea field."""
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
        """Trigger mouseover event on an element."""
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
        """Wait for a JS expression to return a truthy value."""
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
        """Scroll to the bottom of the page."""
        return self.evaluate("window.scrollTo(0, document.body.scrollHeight); true;")

    def scroll_to_top(self):
        """Scroll to the top of the page."""
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
        """Get ALL CDP events (console, network, etc.) since last call.

        Returns raw event dicts. Use get_console_logs() / get_network_errors()
        for filtered views.
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
        return [
            {
                "url": ev["params"].get("documentURL", ""),
                "errorText": ev["params"].get("errorText", ""),
                "type": ev["params"].get("type", ""),
            }
            for ev in events
            if ev["method"] == "Network.loadingFailed"
        ]

    def get_network_requests(self, timeout=1.0):
        """Get all network requests and their responses."""
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
