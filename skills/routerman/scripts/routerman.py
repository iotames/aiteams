#!/usr/bin/env python3
"""routerman 技能核心脚本：ZTE 路由器登录与常用操作。

支持：登录并获取会话凭证、端口转发增删改查、父母控制增删改查。
全部通过 curl 直接调用 HTTP 接口，仅依赖系统自带 curl 与 Python 标准库。
"""
import argparse
import hashlib
import os
import re
import subprocess
import sys
import tempfile

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
    """执行 curl，返回 (响应头, 响应体)。"""
    hdr_f = os.path.join(TMP_DIR, "_hdr.txt")
    body_f = os.path.join(TMP_DIR, "_body.txt")
    subprocess.run(
        ["curl", "-s", "-D", hdr_f, "-o", body_f, "--insecure"] + args,
        capture_output=True,
    )
    hdr = open(hdr_f, encoding="utf-8", errors="replace").read()
    body = open(body_f, encoding="utf-8", errors="replace").read()
    return hdr, body


def _cookies_of(hdr):
    cookies = {}
    for line in hdr.splitlines():
        m = re.match(r"^Set-Cookie:\s*([^=;]+)=([^;]*)", line, re.I)
        if m:
            cookies[m.group(1)] = m.group(2)
    return cookies


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


class Router:
    """ZTE 路由器 HTTP API 客户端。"""

    def __init__(self, cfg):
        self.cfg = cfg
        self.base = cfg.get("ROUTER_ADDR", BASE).rstrip("/")
        self.cookies = {"_TESTCOOKIESUPPORT": "1"}
        self.session_token = ""

    # ---------- 底层请求 ----------
    def get(self, path, extra_headers=None):
        args = ["-b", _cookie_str(self.cookies)]
        h = {"User-Agent": UA}
        if extra_headers:
            h.update(extra_headers)
        for k, v in h.items():
            args += ["-H", f"{k}: {v}"]
        args += [self.base + path]
        hdr, body = _curl(args)
        self.cookies.update(_cookies_of(hdr))
        return hdr, body

    def post(self, path, body_data, extra_headers=None):
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
        return hdr, body

    # ---------- 登录流程 ----------
    def login(self):
        """完整登录流程，成功返回 SID。"""
        # 1. 首页拿 SID
        hdr, _ = self.get("/")
        if "SID" not in self.cookies:
            raise RuntimeError("访问首页未获取到 SID")
        # 2. logintoken
        hdr, body = self.get(
            "/function_module/login_module/login_page/logintoken_lua.lua",
            {"X-Requested-With": "XMLHttpRequest"},
        )
        m = re.search(r"<ajax_response_xml_root>([^<]*)</ajax_response_xml_root>", body)
        xml_obj = m.group(1) if m else ""
        # 3. 登录页 _sessionTOKEN
        hdr, page = self.get("/")
        m = re.search(r'name="_sessionTOKEN"[^>]*value="([^"]*)"', page)
        stoken = m.group(1) if m else ""
        # 4. 登录
        penc = sha256(self.cfg["ROUTER_LOGIN_PASSWORD"] + xml_obj)
        lbody = (
            f"Username={self.cfg['ROUTER_LOGIN_USER']}&Password={penc}"
            f"&action=login&Frm_Logintoken=&captchaCode=&_sessionTOKEN={stoken}"
        )
        hdr, body = self.post("/", lbody, {"Origin": self.base, "Referer": self.base + "/"})
        first = hdr.splitlines()[0]
        if "302" not in first:
            raise RuntimeError(f"登录失败: {first}\n{body[:300]}")
        # 5. 切高级模式
        self.post("/", "IF_ModeSwitch=Advanced", {"Origin": self.base, "Referer": self.base + "/"})
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
    sub = parser.add_subparsers(dest="cmd")

    # 登录
    sub.add_parser("login", help="登录并输出 SID")

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
    r = Router(cfg)
    r.login()
    print(f"登录成功 SID: {r.cookies['SID'][:16]}...", file=sys.stderr)

    feature = None
    if args.cmd.startswith("pf"):
        feature = "portforwarding"
    elif args.cmd.startswith("pc"):
        feature = "parentctrl"
    if feature:
        r.enter_feature(feature)

    if args.cmd == "login":
        return
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


if __name__ == "__main__":
    main()
