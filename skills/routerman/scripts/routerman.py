#!/usr/bin/env python3
"""routerman 技能核心脚本：ZTE 路由器登录与常用操作。

支持：登录并获取会话凭证、端口转发增删改查、父母控制增删改查。
全部通过 curl 直接调用 HTTP 接口，仅依赖系统自带 curl 与 Python 标准库。
"""
import argparse
import hashlib
import html
import os
import re
import subprocess
import sys
import tempfile
import time

BASE = "http://192.168.2.1"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36")
TMP_DIR = tempfile.mkdtemp(prefix="routerman_")

# 功能页面 -> getpage 的 nextpage 值 -> 后端接口
PAGES = {
    "portforwarding": {
        "nextpage": "Internet_PortForwarding_t.lp",
        "api": "/common_page/PortForwarding_lua.lua",
    },
    "parentctrl": {
        "nextpage": "Internet_Parent_Ctrl_t.lp",
        "api": "/common_page/ParentCtrl_lua.lua",
    },
}

CONFIG_KEYS = ("ROUTER_ADDR", "ROUTER_BRAND", "ROUTER_LOGIN_USER", "ROUTER_LOGIN_PASSWORD", "ROUTER_TOKEN")

DEFAULT_CONFIG = {
    "ROUTER_ADDR": "http://192.168.2.1",
    "ROUTER_BRAND": "ZTE",
    "ROUTER_LOGIN_USER": "admin",
    "ROUTER_LOGIN_PASSWORD": "123456",
}


def load_config(env_path=None):
    """加载配置：env 文件 -> 系统环境变量 顺序，后者覆盖前者。"""
    cfg = dict(DEFAULT_CONFIG)
    if env_path and os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                if k.strip() in CONFIG_KEYS:
                    cfg[k.strip()] = v.strip()
    for key in CONFIG_KEYS:
        if os.environ.get(key):
            cfg[key] = os.environ[key]
    return cfg


def sha256(s):
    return hashlib.sha256(s.encode()).hexdigest()


def _curl(args):
    """执行 curl，返回 (响应头, 响应体)。

    带超时保护（默认 10s，可用环境变量 ROUTER_TIMEOUT 覆盖），
    超时、连接失败或无响应时抛 RuntimeError，绝不无限挂起。
    """
    try:
        timeout = float(os.environ.get("ROUTER_TIMEOUT", "10"))
    except ValueError:
        timeout = 10.0
    if timeout < 1:
        timeout = 10.0
    hdr_f = os.path.join(TMP_DIR, "_hdr.txt")
    body_f = os.path.join(TMP_DIR, "_body.txt")
    proc = subprocess.run(
        ["curl", "-s", "-D", hdr_f, "-o", body_f, "--insecure",
         "--max-time", str(timeout)] + args,
        capture_output=True,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode(errors="replace").strip()
        raise RuntimeError(
            f"路由器请求失败(curl 退出码 {proc.returncode}, 超时 {timeout:.0f}s)"
            + (f": {err}" if err else "")
            + "，请检查路由器地址与网络连通性"
        )
    try:
        hdr = open(hdr_f, encoding="utf-8", errors="replace").read()
        body = open(body_f, encoding="utf-8", errors="replace").read()
    except FileNotFoundError:
        raise RuntimeError(f"路由器无响应（超时 {timeout:.0f}s）")
    return hdr, body


def _cookies_of(hdr):
    cookies = {}
    for line in hdr.splitlines():
        m = re.match(r"^Set-Cookie:\s*([^=;]+)=([^;]*)", line, re.I)
        if m:
            cookies[m.group(1)] = m.group(2)
    return cookies


# ---------- 进度日志（统一走 stderr，stdout 保持机器可解析） ----------

def _elapsed(start):
    """从 start 到现在的耗时字符串。"""
    return f"{time.time() - start:.1f}s"


def _log(msg):
    """进度/调试日志 → stderr。结果输出一律走 stdout，互不干扰。"""
    print(f"[routerman] {msg}", file=sys.stderr)


def _step(i, total, desc):
    """打印阶段进度（如 [1/3] 登录路由器 ...），返回本步开始时间。"""
    _log(f"[{i}/{total}] {desc} ...")
    return time.time()


def _step_done(t0, extra=""):
    """打印阶段完成与耗时（如 完成 (0.8s)），可带附加信息。"""
    _log(f"    完成 ({_elapsed(t0)})" + (f" {extra}" if extra else ""))


def _cookie_str(cookies):
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def _split_root(xml):
    """解析响应 XML 根元素。"""
    m = re.search(r"<ajax_response_xml_root>(.*)</ajax_response_xml_root>", xml, re.S)
    return m.group(1) if m else xml


def _error_info(xml):
    """提取错误信息。成功返回 (True, "")，失败返回 (False, 错误详情)。"""
    m = re.search(r"<IF_ERRORID>(-?\d+)</IF_ERRORID>", xml)
    err_id = m.group(1) if m else "?"
    m = re.search(r"<IF_ERRORTYPE>([^<]*)</IF_ERRORTYPE>", xml)
    err_type = m.group(1) if m else ""
    m = re.search(r"<IF_ERRORSTR>([^<]*)</IF_ERRORSTR>", xml)
    err_str = m.group(1) if m else ""
    m = re.search(r"<IF_ERRORPARAM>([^<]*)</IF_ERRORPARAM>", xml)
    err_param = m.group(1) if m else ""
    if err_str == "SUCC" and err_param == "SUCC":
        return True, ""
    detail = f"IF_ERRORID={err_id} TYPE={err_type} STR={err_str} PARAM={err_param}"
    if err_param and err_param != "SUCC":
        detail += f" 字段={err_param}"
    return False, detail


class PreemptRequired(RuntimeError):
    """登录时发现其他用户正在设置设备，需要先抢占(踢出)其会话。

    Attributes:
        sessions: 在线会话列表，每项含 sessid / label / ip / user。
    """

    def __init__(self, sessions):
        self.sessions = sessions
        msg = "其他用户正在设置设备，需抢占会话: " + "、".join(
            f"{s.get('ip', '?')}({s.get('user', '?')})" for s in sessions
        )
        super().__init__(msg)


def parse_preempt_sessions(page):
    """从登录返回的抢占页 HTML 中解析在线会话列表。

    抢占页特征：`<div id="Level">` 内每个会话一个 radio，
    `name="preempt_sessid" value=<sessid>`，label 为 `IP(用户名)`。
    非抢占页返回 None。
    """
    block = re.search(r'<div id="Level">(.*?)</div>', page, re.S)
    if not block:
        return None
    inner = block.group(1)
    if "preempt_sessid" not in inner:
        return None
    sessions = []
    radios = re.findall(
        r'<input[^>]*name="preempt_sessid"[^>]*value="?([0-9a-fA-F]+)"?', inner
    )
    labels = re.findall(r'<label[^>]*>([^<]*)</label>', inner)
    for i, sid in enumerate(radios):
        label = html.unescape(labels[i]) if i < len(labels) else ""
        m = re.match(r"^(.+?)\((.+)\)$", label)
        ip, user = m.groups() if m else (label, "")
        sessions.append({"sessid": sid, "label": label, "ip": ip, "user": user})
    return sessions or None


class Router:
    """ZTE 路由器 HTTP API 客户端。

    verbose=True 时打印每个 HTTP 请求的 method/path/状态行/耗时到 stderr。
    """

    def __init__(self, cfg, verbose=False):
        self.cfg = cfg
        self.base = cfg.get("ROUTER_ADDR", BASE).rstrip("/")
        self.cookies = {"_TESTCOOKIESUPPORT": "1"}
        self.session_token = ""
        self.verbose = verbose

    def _req_log(self, method, path, hdr, t0):
        if not self.verbose:
            return
        first = hdr.splitlines()[0] if hdr else "(无响应)"
        _log(f"  {method} {path} -> {first} ({_elapsed(t0)})")

    # ---------- 底层请求 ----------
    def get(self, path, extra_headers=None):
        t0 = time.time()
        args = ["-b", _cookie_str(self.cookies)]
        h = {"User-Agent": UA}
        if extra_headers:
            h.update(extra_headers)
        for k, v in h.items():
            args += ["-H", f"{k}: {v}"]
        args += [self.base + path]
        hdr, body = _curl(args)
        self.cookies.update(_cookies_of(hdr))
        self._req_log("GET", path, hdr, t0)
        return hdr, body

    def post(self, path, body_data, extra_headers=None):
        t0 = time.time()
        args = ["-X", "POST", "--data-raw", body_data,
                "-H", f"Check: {sha256(body_data)}",
                "-H", "Content-Type: application/x-www-form-urlencoded"]
        h = {"User-Agent": UA}
        if extra_headers:
            h.update(extra_headers)
        for k, v in h.items():
            args += ["-H", f"{k}: {v}"]
        args += ["-b", _cookie_str(self.cookies)]
        args += [self.base + path]
        hdr, body = _curl(args)
        self.cookies.update(_cookies_of(hdr))
        self._req_log("POST", path, hdr, t0)
        return hdr, body

    # ---------- 登录流程 ----------
    def _login_request(self):
        """登录步骤 1-4：访问首页拿 SID、logintoken、提取页面 token、提交登录。
        返回 (响应头, 响应体)。"""
        hdr, _ = self.get("/")
        if "SID" not in self.cookies:
            raise RuntimeError("访问首页未获取到 SID")
        hdr, body = self.get(
            "/function_module/login_module/login_page/logintoken_lua.lua",
            {"X-Requested-With": "XMLHttpRequest"},
        )
        m = re.search(r"<ajax_response_xml_root>([^<]*)</ajax_response_xml_root>", body)
        xml_obj = m.group(1) if m else ""
        hdr, page = self.get("/")
        m = re.search(r'name="_sessionTOKEN"[^>]*value="([^"]*)"', page)
        stoken = m.group(1) if m else ""
        penc = sha256(self.cfg["ROUTER_LOGIN_PASSWORD"] + xml_obj)
        lbody = (
            f"Username={self.cfg['ROUTER_LOGIN_USER']}&Password={penc}"
            f"&action=login&Frm_Logintoken=&captchaCode=&_sessionTOKEN={stoken}"
        )
        hdr, body = self.post("/", lbody, {"Origin": self.base, "Referer": self.base + "/"})
        return hdr, body

    def _switch_advanced(self):
        """步骤 5：切换高级模式。"""
        self.post("/", "IF_ModeSwitch=Advanced",
                  {"Origin": self.base, "Referer": self.base + "/"})

    def login(self, auto_preempt=False, _retries=0):
        """完整登录流程，成功返回 SID。

        auto_preempt=True 时，若检测到其他用户占用，自动抢占踢出全部占用会话后继续登录；
        否则检测到占用时抛出 PreemptRequired（含会话列表）。

        抢占踢出最多重试 3 轮：若占用方反复重登导致始终抢占不成功，抛 PreemptRequired。
        """
        hdr, body = self._login_request()
        first = hdr.splitlines()[0]
        if "302" in first:
            self._switch_advanced()
            return self.cookies.get("SID")
        sessions = parse_preempt_sessions(body)
        if not sessions:
            raise RuntimeError(f"登录失败: {first}\n{body[:300]}")
        if not auto_preempt:
            raise PreemptRequired(sessions)
        if _retries >= 3:
            raise PreemptRequired(sessions)
        for s in sessions:
            self.preempt_kick(s["sessid"])
        return self.login(auto_preempt=True, _retries=_retries + 1)

    def detect_preempt(self):
        """执行登录请求，检测是否被其他用户占用。

        返回：占用会话列表（未占用返回 None）。仅探测，不切换高级模式。
        """
        hdr, body = self._login_request()
        if "302" in hdr.splitlines()[0]:
            return None
        return parse_preempt_sessions(body)

    def preempt_kick(self, sessid):
        """抢占踢出指定会话（POST preempt_sessid + action=preempt）。返回新 SID。

        需先通过 _login_request / detect_preempt 触发抢占页拿到 sessid。
        """
        body = f"preempt_sessid={sessid}&action=preempt"
        hdr, _ = self.post("/", body, {"Origin": self.base, "Referer": self.base + "/"})
        first = hdr.splitlines()[0]
        if "302" not in first:
            raise RuntimeError(f"抢占踢出失败: {first}")
        return self.cookies.get("SID")

    # ---------- 功能页面 ----------
    def enter_feature(self, feature):
        """进入指定功能页，提取会话 token。返回页面 HTML。"""
        if feature not in PAGES:
            raise ValueError(f"不支持的功能: {feature}，可选: {list(PAGES)}")
        page = self.get_page(PAGES[feature]["nextpage"])
        self.session_token = self.extract_session_token(page)
        return page

    def get_page(self, nextpage):
        hdr, page = self.get(
            f"/getpage.lua?pid=1002&nextpage={nextpage}",
            {"Referer": self.base + "/", "X-Requested-With": "XMLHttpRequest"},
        )
        return page

    def extract_session_token(self, page):
        toks = re.findall(r'_sessionTmpToken\s*=\s*"((?:\\x[0-9a-fA-F]{2})*)"', page)
        if toks:
            return bytes(toks[-1], "utf-8").decode("unicode_escape")
        return ""

    def api_get(self, lua_path, referer="/"):
        return self.get(lua_path, {"Referer": self.base + referer, "X-Requested-With": "XMLHttpRequest"})

    def api_post(self, lua_path, form_fields, referer="/"):
        if isinstance(form_fields, dict):
            pairs = list(form_fields.items())
        else:
            pairs = list(form_fields)
        body = "&".join(f"{k}={v}" for k, v in pairs)
        if self.session_token:
            body += "&_sessionTOKEN=" + self.session_token
        return self.post(lua_path, body, {"Referer": self.base + referer, "X-Requested-With": "XMLHttpRequest"})


# ==================== 已关联设备 ====================

def device_list(r):
    """查询路由器已关联设备列表（含 MAC 地址）。

    用于父母控制新增前获取已关联设备的 MAC：ChildId 必须是
    该列表中的 MAC，虚拟 MAC 会校验失败。

    返回字段（去掉 _LuQUID_ 前缀）：
      _InstID, ConnectType, AliasName, InterfaceID, Active,
      IPAddress, HostName, MACAddress, DevName, IPV6Address,
      InterfaceType, InternetAccess, Band, DevMeshType, Interface
    """
    ts = int(time.time() * 1000)
    hdr, body = r.get(
        "/common_page/Query_AccessDevice_lua.lua?_=" + str(ts),
        {"Referer": self_ref(r), "X-Requested-With": "XMLHttpRequest",
         "Accept": "application/xml, text/xml, */*; q=0.01"},
    )
    items = []
    m = re.search(r"<OBJ_LAN_ACCESS_ID>(.*?)</OBJ_LAN_ACCESS_ID>", body, re.S)
    if m:
        for inst in re.findall(r"<Instance>(.*?)</Instance>", m.group(1), re.S):
            d = dict(re.findall(r"<ParaName>([^<]*)</ParaName><ParaValue>([^<]*)</ParaValue>", inst))
            items.append({k.replace("_LuQUID_", ""): v for k, v in d.items()})
    return items


def self_ref(r):
    return r.base + "/getpage.lua?pid=1002&nextpage=Internet_Parent_Ctrl_t.lp"


# ==================== 端口转发 ====================

def pf_list(r):
    """端口转发查询列表。"""
    hdr, body = r.api_get(PAGES["portforwarding"]["api"])
    items = []
    for inst in re.findall(r"<Instance>(.*?)</Instance>", body, re.S):
        d = dict(re.findall(r"<ParaName>([^<]*)</ParaName><ParaValue>([^<]*)</ParaValue>", inst))
        items.append(d)
    return items


def pf_apply(r, alias, protocol, internal_client, external_port,
             external_port_end=None, internal_port=None, internal_port_end=None,
             enable=1, inst_id="-1"):
    """端口转发新增/修改。inst_id=-1 为新增，否则修改对应实例。"""
    end_ext = external_port_end if external_port_end else external_port
    end_int = internal_port_end if internal_port_end else internal_port
    fields = [
        ("IF_ACTION", "Apply"),
        ("Alias", alias),
        ("Protocol", protocol),
        ("InternalClient", internal_client),
        ("ExternalPort", str(external_port)),
        ("ExternalPortEndRange", str(end_ext)),
        ("InternalPort", str(internal_port if internal_port else external_port)),
        ("InternalPortEndRange", str(end_int)),
        ("Enable", str(enable)),
        ("_InstID", inst_id),
    ]
    hdr, body = r.api_post(PAGES["portforwarding"]["api"], fields)
    return _error_info(body), body


def pf_delete(r, inst_id, alias="", protocol="TCP", internal_client="",
              external_port="", internal_port="", enable=1):
    """端口转发删除。"""
    fields = [
        ("IF_ACTION", "Delete"),
        ("_InstID", inst_id),
        ("Alias", alias),
        ("Protocol", protocol),
        ("InternalClient", internal_client),
        ("ExternalPort", str(external_port)),
        ("ExternalPortEndRange", str(external_port)),
        ("InternalPort", str(internal_port)),
        ("InternalPortEndRange", str(internal_port)),
        ("Enable", str(enable)),
    ]
    hdr, body = r.api_post(PAGES["portforwarding"]["api"], fields)
    return _error_info(body), body


def pf_switch(r, inst_id, enable):
    """端口转发开启/关闭开关。"""
    fields = [
        ("IF_ACTION", "Apply"),
        ("Enable", str(enable)),
        ("_InstID", inst_id),
    ]
    hdr, body = r.api_post(PAGES["portforwarding"]["api"], fields)
    return _error_info(body), body


# ==================== 父母控制 ====================

def pc_list(r):
    """父母控制查询列表。"""
    hdr, body = r.api_get(PAGES["parentctrl"]["api"])
    items = []
    for inst in re.findall(r"<Instance>(.*?)</Instance>", body, re.S):
        d = dict(re.findall(r"<ParaName>([^<]*)</ParaName><ParaValue>([^<]*)</ParaValue>", inst))
        items.append(d)
    return items


def pc_apply(r, name, child_id, week, start_hour, start_min, end_hour, end_min,
             filter_mode="NotAllowed", enable=1, inst_id="-1", urls=None):
    """父母控制新增/修改。

    child_id 必须是路由器已关联设备的 MAC（虚拟 MAC 会校验失败）。
    week: 周历十进制值，7 位二进制 (Su Mo Tu We Th Fr Sa)，每天=127。
    urls: FilterMode=BlackList/WhiteList 时的 URL 列表。
    """
    fields = [
        ("IF_ACTION", "Apply"),
        ("Name", name),
        ("ChildId", child_id),
        ("Week", str(week)),
        ("StartHour", str(start_hour)),
        ("StartMin", str(start_min)),
        ("EndHour", str(end_hour)),
        ("EndMin", str(end_min)),
        ("FilterMode", filter_mode),
        ("Enable", str(enable)),
        ("_InstID", inst_id),
    ]
    if filter_mode != "NotAllowed":
        urls = urls or []
        fields.append(("URLCnt", str(len(urls))))
        for i, url in enumerate(urls[:32]):
            fields.append((f"URL{i}", url))
    hdr, body = r.api_post(PAGES["parentctrl"]["api"], fields)
    return _error_info(body), body


def pc_delete(r, inst_id, name="", child_id="", week="127", start_hour="", start_min="",
              end_hour="", end_min="", filter_mode="NotAllowed", enable=1):
    """父母控制删除。"""
    fields = [
        ("IF_ACTION", "Delete"),
        ("_InstID", inst_id),
        ("Name", name),
        ("ChildId", child_id),
        ("Week", str(week)),
        ("StartHour", str(start_hour)),
        ("StartMin", str(start_min)),
        ("EndHour", str(end_hour)),
        ("EndMin", str(end_min)),
        ("FilterMode", filter_mode),
        ("Enable", str(enable)),
    ]
    hdr, body = r.api_post(PAGES["parentctrl"]["api"], fields)
    return _error_info(body), body


def pc_switch(r, inst_id, enable):
    """父母控制开启/关闭开关。"""
    fields = [
        ("IF_ACTION", "Apply"),
        ("Enable", str(enable)),
        ("_InstID", inst_id),
    ]
    hdr, body = r.api_post(PAGES["parentctrl"]["api"], fields)
    return _error_info(body), body


# ==================== CLI ====================

def _print_items(items):
    for it in items:
        print(it)


def main():
    parser = argparse.ArgumentParser(description="ZTE 路由器常用操作")
    parser.add_argument("--env", default=".env", help="env 文件路径（默认 .env）")
    parser.add_argument("--verbose", action="store_true",
                        help="打印每个 HTTP 请求详情到 stderr")
    sub = parser.add_subparsers(dest="cmd")

    # 登录
    sub.add_parser("login", help="登录并输出 SID")

    # 会话抢占（踢出其他登录用户）
    sub.add_parser("kick-list", help="检测是否被其他用户占用，列出占用会话")
    p_kick = sub.add_parser("kick", help="抢占踢出占用会话并登录（默认踢全部）")
    p_kick.add_argument("--sessid", help="仅踢出指定会话（可省略，默认踢全部占用会话）")

    # 已关联设备
    sub.add_parser("dev-list", help="已关联设备列表（含 MAC，供父母控制使用）")

    # 端口转发
    p_pf = sub.add_parser("pf-list", help="端口转发列表")
    p_pf_add = sub.add_parser("pf-add", help="端口转发新增")
    p_pf_add.add_argument("--alias", required=True)
    p_pf_add.add_argument("--protocol", default="TCP", choices=["TCP", "UDP", "BOTH"])
    p_pf_add.add_argument("--internal-client", required=True)
    p_pf_add.add_argument("--external-port", required=True)
    p_pf_add.add_argument("--internal-port", required=True)
    p_pf_add.add_argument("--enable", type=int, default=1, choices=[0, 1])
    p_pf_mod = sub.add_parser("pf-mod", help="端口转发修改（按实例ID）")
    p_pf_mod.add_argument("--inst-id", required=True)
    p_pf_mod.add_argument("--alias", required=True)
    p_pf_mod.add_argument("--protocol", default="TCP", choices=["TCP", "UDP", "BOTH"])
    p_pf_mod.add_argument("--internal-client", required=True)
    p_pf_mod.add_argument("--external-port", required=True)
    p_pf_mod.add_argument("--internal-port", required=True)
    p_pf_mod.add_argument("--enable", type=int, default=1, choices=[0, 1])
    p_pf_del = sub.add_parser("pf-del", help="端口转发删除")
    p_pf_del.add_argument("--inst-id", required=True)
    p_pf_sw = sub.add_parser("pf-switch", help="端口转发开关")
    p_pf_sw.add_argument("--inst-id", required=True)
    p_pf_sw.add_argument("--enable", type=int, required=True, choices=[0, 1])

    # 父母控制
    sub.add_parser("pc-list", help="父母控制列表")
    p_pc_add = sub.add_parser("pc-add", help="父母控制新增")
    p_pc_add.add_argument("--name", required=True)
    p_pc_add.add_argument("--mac", required=True, help="已关联设备的 MAC")
    p_pc_add.add_argument("--week", default="127", help="周历十进制值，每天=127")
    p_pc_add.add_argument("--start", default="8:0")
    p_pc_add.add_argument("--end", default="20:0")
    p_pc_add.add_argument("--mode", default="NotAllowed",
                          choices=["NotAllowed", "BlackList", "WhiteList"])
    p_pc_add.add_argument("--url", action="append", default=[], help="URL（黑/白名单时重复使用）")
    p_pc_add.add_argument("--enable", type=int, default=1, choices=[0, 1])
    p_pc_mod = sub.add_parser("pc-mod", help="父母控制修改（按实例ID）")
    p_pc_mod.add_argument("--inst-id", required=True)
    p_pc_mod.add_argument("--name", required=True)
    p_pc_mod.add_argument("--mac", required=True)
    p_pc_mod.add_argument("--week", default="127")
    p_pc_mod.add_argument("--start", default="8:0")
    p_pc_mod.add_argument("--end", default="20:0")
    p_pc_mod.add_argument("--mode", default="NotAllowed",
                          choices=["NotAllowed", "BlackList", "WhiteList"])
    p_pc_mod.add_argument("--url", action="append", default=[])
    p_pc_mod.add_argument("--enable", type=int, default=1, choices=[0, 1])
    p_pc_del = sub.add_parser("pc-del", help="父母控制删除")
    p_pc_del.add_argument("--inst-id", required=True)
    p_pc_sw = sub.add_parser("pc-switch", help="父母控制开关")
    p_pc_sw.add_argument("--inst-id", required=True)
    p_pc_sw.add_argument("--enable", type=int, required=True, choices=[0, 1])

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(1)

    cfg = load_config(args.env)
    r = Router(cfg, verbose=args.verbose)

    # kick-list：只检测，不登录
    if args.cmd == "kick-list":
        start_all = time.time()
        t0 = _step(1, 1, "探测是否被其他用户占用")
        try:
            sessions = r.detect_preempt()
        except RuntimeError as e:
            _log(f"    失败: {e}")
            print(f"FAIL: {e}")
            sys.exit(1)
        _step_done(t0)
        _log(f"总耗时 {_elapsed(start_all)}")
        if not sessions:
            print("无其他用户占用，登录正常")
            return
        print(f"检测到 {len(sessions)} 个占用会话:")
        for s in sessions:
            print(f"  sessid={s['sessid']}  {s['label']}")
        return

    # kick：抢占踢出后登录
    if args.cmd == "kick":
        start_all = time.time()
        total = 3 if args.sessid else 2
        i = 1
        try:
            if args.sessid:
                t0 = _step(i, total, "探测占用会话")
                sessions = r.detect_preempt() or []
                _step_done(t0)
                i += 1
                if not sessions:
                    t0 = _step(i, total, "登录路由器")
                    sid = r.login()
                    _step_done(t0, f"SID: {sid[:16]}...")
                    _log(f"总耗时 {_elapsed(start_all)}")
                    print("无其他用户占用，登录正常")
                    return
                if not any(s["sessid"] == args.sessid for s in sessions):
                    print(f"FAIL: 指定会话 {args.sessid} 不在占用列表:")
                    for s in sessions:
                        print(f"  sessid={s['sessid']}  {s['label']}")
                    sys.exit(1)
                t0 = _step(i, total, f"踢出会话 {args.sessid[:16]}...")
                r.preempt_kick(args.sessid)
                _step_done(t0)
                i += 1
                t0 = _step(i, total, "重新登录")
                sid = r.login()
                _step_done(t0, f"SID: {sid[:16]}...")
                _log(f"总耗时 {_elapsed(start_all)}")
                print(f"OK: 已踢出 {args.sessid[:16]}... 并登录，SID: {sid[:16]}...")
            else:
                t0 = _step(i, total, "登录并抢占踢出占用会话")
                sid = r.login(auto_preempt=True)
                _step_done(t0, f"SID: {sid[:16]}...")
                _log(f"总耗时 {_elapsed(start_all)}")
                print(f"OK: 抢占成功，已登录 SID: {sid[:16]}...")
        except PreemptRequired as e:
            print("FAIL: 仍有会话占用:", e)
            print("可执行 kick-list 查看，或 kick --sessid <id> 指定踢出")
            sys.exit(1)
        except RuntimeError as e:
            print(f"FAIL: {e}")
            sys.exit(1)
        return

    start_all = time.time()
    cmd_verbs = {
        "login": "登录",
        "dev-list": "查询已关联设备",
        "pf-list": "查询端口转发列表", "pf-add": "新增端口转发", "pf-mod": "修改端口转发",
        "pf-del": "删除端口转发", "pf-switch": "切换端口转发开关",
        "pc-list": "查询父母控制列表", "pc-add": "新增父母控制", "pc-mod": "修改父母控制",
        "pc-del": "删除父母控制", "pc-switch": "切换父母控制开关",
    }
    feature = None
    if args.cmd.startswith("pf"):
        feature = "portforwarding"
    elif args.cmd.startswith("pc"):
        feature = "parentctrl"

    total = 1 if args.cmd == "login" else 2 + (1 if feature else 0)
    i = 1

    t0 = _step(i, total, f"登录路由器 {cfg.get('ROUTER_ADDR', BASE)}")
    try:
        sid = r.login(auto_preempt=False)
    except PreemptRequired as e:
        _log(f"    失败: {e}")
        print(f"FAIL: 其他用户正在设置设备: {e}")
        print("可执行 kick-list 查看占用，或 kick 抢占后重试")
        sys.exit(1)
    except RuntimeError as e:
        _log(f"    失败: {e}")
        print(f"FAIL: {e}")
        sys.exit(1)
    _step_done(t0, f"SID: {sid[:16]}...")
    i += 1

    if feature:
        t0 = _step(i, total, f"进入功能页 {feature}")
        try:
            r.enter_feature(feature)
        except RuntimeError as e:
            _log(f"    失败: {e}")
            print(f"FAIL: {e}")
            sys.exit(1)
        _step_done(t0)
        i += 1

    if args.cmd == "login":
        print(f"OK: 登录成功，SID: {sid[:16]}...")
        _log(f"总耗时 {_elapsed(start_all)}")
        return

    t0 = _step(i, total, f"执行 {cmd_verbs.get(args.cmd, args.cmd)}")
    try:
        if args.cmd == "dev-list":
            _print_items(device_list(r))
        elif args.cmd == "pf-list":
            _print_items(pf_list(r))
        elif args.cmd == "pf-add":
            ok, err = pf_apply(r, args.alias, args.protocol, args.internal_client,
                               args.external_port, internal_port=args.internal_port, enable=args.enable)
            print("OK: 新增成功" if ok else f"FAIL: {err}")
        elif args.cmd == "pf-mod":
            ok, err = pf_apply(r, args.alias, args.protocol, args.internal_client,
                               args.external_port, internal_port=args.internal_port,
                               enable=args.enable, inst_id=args.inst_id)
            print("OK: 修改成功" if ok else f"FAIL: {err}")
        elif args.cmd == "pf-del":
            ok, err = pf_delete(r, args.inst_id)
            print("OK: 删除成功" if ok else f"FAIL: {err}")
        elif args.cmd == "pf-switch":
            ok, err = pf_switch(r, args.inst_id, args.enable)
            print("OK: 开关设置成功" if ok else f"FAIL: {err}")
        elif args.cmd == "pc-list":
            _print_items(pc_list(r))
        elif args.cmd in ("pc-add", "pc-mod"):
            start = args.start.split(":"); sh, sm = int(start[0]), int(start[1])
            end = args.end.split(":"); eh, em = int(end[0]), int(end[1])
            inst_id = args.inst_id if args.cmd == "pc-mod" else "-1"
            ok, err = pc_apply(r, args.name, args.mac, args.week, sh, sm, eh, em,
                               filter_mode=args.mode, enable=args.enable,
                               inst_id=inst_id, urls=args.url)
            print("OK: 保存成功" if ok else f"FAIL: {err}")
        elif args.cmd == "pc-del":
            ok, err = pc_delete(r, args.inst_id)
            print("OK: 删除成功" if ok else f"FAIL: {err}")
        elif args.cmd == "pc-switch":
            ok, err = pc_switch(r, args.inst_id, args.enable)
            print("OK: 开关设置成功" if ok else f"FAIL: {err}")
        else:
            parser.print_help()
            sys.exit(1)
    except RuntimeError as e:
        _log(f"    失败: {e}")
        print(f"FAIL: {e}")
        sys.exit(1)

    _step_done(t0)
    _log(f"总耗时 {_elapsed(start_all)}")


if __name__ == "__main__":
    main()
