"""极简 CDP 采集器：面向「注入钩子 + 持续观察网络」的场景。

为什么不复用 chromedp 技能的 CDPClient：它的 ``_recv_response`` 会为每条命令
循环收包直到等到对应 id，与「reload 后连续采集几十秒事件」的用法互相阻塞，
实践中会直接挂住。本模块用裸 WebSocket 自己收发，采集期只做收包。

依赖：websocket-client（``pip install websocket-client``）
"""

from __future__ import annotations

import json
import select
import time
import urllib.request

import websocket


class CaptureError(RuntimeError):
    """采集过程中的可预期错误（连不上、找不到页面、CDP 命令报错）。"""


class Page:
    """一个已连接的 CDP page 目标。

    :param port: Chrome 远程调试端口
    :param host: 调试端口所在主机
    :param match: 用于定位标签页的 URL 片段。**必填**——同域多标签页时
        不带它就会连错页；只在 ``type == "page"`` 的目标里匹配。
    :param timeout: 单条 CDP 命令的等待上限（秒）
    """

    def __init__(self, port: int = 9222, host: str = "127.0.0.1",
                 match: str | None = None, timeout: float = 15.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._id = 0
        self._drained: list[dict] = []

        targets = json.loads(
            urllib.request.urlopen(f"http://{host}:{port}/json/list", timeout=5).read()
        )
        pages = [t for t in targets if t.get("type") == "page"]
        target = None
        if match:
            for t in pages:
                if match in t.get("url", ""):
                    target = t
                    break
        if target is None and match is None and pages:
            target = pages[0]
        if target is None:
            urls = "\n".join(f"  {t.get('url', '')[:120]}" for t in pages)
            raise CaptureError(
                f"没有匹配 {match!r} 的 page 标签页，当前打开的页面：\n{urls}"
            )
        self.target_id = target["id"]
        self.url = target.get("url", "")
        self.ws = websocket.create_connection(
            target["webSocketDebuggerUrl"], timeout=timeout
        )

    # ─── 命令收发 ────────────────────────────────────────

    def send(self, method: str, params: dict | None = None) -> dict:
        """发送一条 CDP 命令并等待其响应；期间收到的事件先丢弃。"""
        self._id += 1
        msg: dict = {"id": self._id, "method": method}
        if params:
            msg["params"] = params
        self.ws.send(json.dumps(msg))
        deadline = time.time() + self.timeout
        self.ws.settimeout(self.timeout)
        while time.time() < deadline:
            try:
                resp = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException as exc:
                raise CaptureError(f"CDP 命令 {method} 超时") from exc
            if resp.get("id") == self._id:
                if "error" in resp:
                    raise CaptureError(f"CDP 命令 {method} 报错：{resp['error']}")
                return resp.get("result", {})
        raise CaptureError(f"CDP 命令 {method} 超时")

    # ─── 采集 ────────────────────────────────────────────

    def install_hook(self, source: str) -> None:
        """注入在每个新文档开始执行前运行的脚本（reload 后生效）。"""
        self.send("Page.addScriptToEvaluateOnNewDocument", {"source": source})

    def reload(self) -> None:
        self.send("Page.reload", {"ignoreCache": False})

    def collect(self, seconds: float) -> list[dict]:
        """持续收包指定秒数，返回期间收到的全部事件。

        必须先用 ``select`` 确认 socket 可读再 ``recv()``：如果在读一帧消息的
        中途超时中断，WebSocket 连接会错位，后续所有 CDP 命令都会「莫名超时」。
        期间若弹出 JS 对话框（alert/confirm/beforeunload），渲染进程会被阻塞，
        这里顺手接受掉，避免整轮采集白跑。
        """
        events: list[dict] = []
        sock = self.ws.sock
        deadline = time.time() + seconds
        while time.time() < deadline:
            ready, _, _ = select.select([sock], [], [], min(0.5, max(0.0, deadline - time.time())))
            if not ready:
                continue
            self.ws.settimeout(self.timeout)
            resp = json.loads(self.ws.recv())
            if resp.get("method") == "Page.javascriptDialogOpening":
                self.send_nowait("Page.handleJavaScriptDialog", {"accept": True})
                continue
            if resp.get("method"):
                events.append(resp)
        return events

    def send_nowait(self, method: str, params: dict | None = None) -> None:
        """发出命令但不等待响应（响应会在后续收包时作为带 id 的消息出现并被忽略）。"""
        self._id += 1
        msg: dict = {"id": self._id, "method": method}
        if params:
            msg["params"] = params
        self.ws.send(json.dumps(msg))

    def evaluate(self, expression: str):
        """执行 JS 表达式并返回其值（按值传递）。"""
        self.dismiss_dialogs()
        res = self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        })
        if res.get("exceptionDetails"):
            raise CaptureError(f"JS 执行出错：{res['exceptionDetails'].get('text')}")
        return res.get("result", {}).get("value")

    def dismiss_dialogs(self) -> None:
        """有 JS 弹窗（alert/confirm/beforeunload）就接受掉。

        弹窗打开期间渲染进程被阻塞，`Runtime.evaluate` 会一直等到超时——表现为
        「命令莫名超时」。没有弹窗时该命令会报错，忽略即可。
        """
        try:
            self.send("Page.handleJavaScriptDialog", {"accept": True})
        except CaptureError:
            pass

    def click(self, x: float, y: float) -> None:
        """在页面坐标 (x, y) 派发一次真实鼠标点击。

        关键用途：CDP 触发的 `Page.reload` 不携带用户激活，Chrome 的自动播放策略
        会拒绝 `video.play()`（NotAllowedError）。派发真实输入事件能取得用户激活，
        播放器才会真正拉流、解密。JS 里合成的 `element.click()` 不算数。
        """
        for kind in ("mousePressed", "mouseReleased"):
            self.send("Input.dispatchMouseEvent", {
                "type": kind, "x": x, "y": y,
                "button": "left", "buttons": 1, "clickCount": 1,
            })

    def response_body(self, request_id: str) -> tuple[bytes, bool]:
        """取某条已完成请求的响应体，返回 (原始字节, 是否 base64 编码)。"""
        res = self.send("Network.getResponseBody", {"requestId": request_id})
        body = res.get("body", "")
        if res.get("base64Encoded"):
            import base64
            return base64.b64decode(body), True
        return body.encode("utf-8", "replace"), False

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass


def split_events(events: list[dict]) -> dict:
    """把原始事件按用途拆分，返回 ``{"requests": {id: url}, "responses": {id: evt}}``。"""
    requests: dict[str, str] = {}
    responses: dict[str, dict] = {}
    for evt in events:
        method = evt.get("method")
        params = evt.get("params", {})
        if method == "Network.requestWillBeSent":
            requests[params["requestId"]] = params["request"]["url"]
        elif method == "Network.responseReceived":
            responses[params["requestId"]] = params["response"]
    return {"requests": requests, "responses": responses}
