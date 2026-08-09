#!/usr/bin/env python3
"""routerman 技能全功能 E2E 测试脚本。

覆盖 routerman 技能全部命令：登录、端口转发增删改查与开关、父母控制增删改查与开关。

安全设计：
- 不硬编码任何凭据，运行时从 --env 指定的文件读取（复用 routerman.load_config）。
- 密码 / SID 只断言非空并掩码显示，绝不打印明文。
- 所有增删改只在脚本自己创建的 SkillTest_* 测试规则上进行，现有用户规则零写入。
- 修改测试先取规则当前值 V0，改成 V1 验证后再按 V0 还原并验证。
- try/finally 兜底清理：即使中途失败也会重新登录并删除已创建的测试规则。

用法：
    python3 test_routerman_e2e.py --env /path/to/.env
可选参数：
    --pf-client <IP>   端口转发测试用内网主机 IP（默认从现有规则复用）
    --pc-mac <MAC>     父母控制测试用已关联设备 MAC（默认从现有规则复用）
    --only <关键字>    只运行名称包含该关键字的用例
"""
import argparse
import os
import random
import re
import sys
import time

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.normpath(os.path.join(TESTS_DIR, "..", "scripts"))
sys.path.insert(0, SCRIPTS_DIR)

from routerman import (  # noqa: E402
    Router,
    load_config,
    device_list,
    pf_apply,
    pf_delete,
    pf_list,
    pf_switch,
    pc_apply,
    pc_delete,
    pc_list,
    pc_switch,
)

_created = []
RESULTS = []


def run_case(name, fn, *args):
    try:
        status, detail = fn(*args)
    except Exception as exc:
        status, detail = "FAIL", f"{type(exc).__name__}: {exc}"
    RESULTS.append((name, status))
    print(f"[{status:4}] {name} -- {detail}")
    return status


def _cleanup(cfg):
    if not _created:
        return
    print("\n[清理] 开始兜底删除已创建的测试规则 ...")
    try:
        r = Router(cfg)
        r.login()
    except Exception as exc:
        print(f"[清理] 无法重新登录: {exc}")
        return
    for kind, inst_id in list(_created):
        try:
            if kind == "pf":
                r.enter_feature("portforwarding")
                ok, err = pf_delete(r, inst_id)
                print(f"[清理] 删除端口转发 {inst_id}: {'OK' if ok else err}")
            else:
                r.enter_feature("parentctrl")
                ok, err = pc_delete(r, inst_id)
                print(f"[清理] 删除父母控制 {inst_id}: {'OK' if ok else err}")
            if ok:
                _created.remove((kind, inst_id))
        except Exception as exc:
            print(f"[清理] 删除 {inst_id} 失败: {exc}")


def t_config(env_path):
    cfg = load_config(env_path)
    missing = [k for k in ("ROUTER_ADDR", "ROUTER_BRAND", "ROUTER_LOGIN_USER",
                           "ROUTER_LOGIN_PASSWORD") if not cfg.get(k)]
    if missing:
        return "FAIL", f".env 缺少配置: {missing}"
    pw = cfg["ROUTER_LOGIN_PASSWORD"]
    masked = "*" * 6
    return ("PASS",
            f"ADDR={cfg['ROUTER_ADDR']} BRAND={cfg['ROUTER_BRAND']} "
            f"USER={cfg['ROUTER_LOGIN_USER']} PASSWORD={masked}({len(pw)}位，掩码)")


def t_login(r):
    sid = r.login()
    if not sid:
        return "FAIL", "登录未获得 SID"
    return "PASS", f"SID={sid[:4]}...（掩码）"


def t_pf_list(r):
    r.enter_feature("portforwarding")
    items = pf_list(r)
    required = ("_InstID", "Alias", "Protocol", "InternalClient",
                "ExternalPort", "InternalPort", "Enable")
    for it in items:
        for k in required:
            if k not in it:
                return "FAIL", f"规则 {it.get('_InstID', '?')} 缺少字段 {k}"
    return "PASS", f"共 {len(items)} 条规则，字段完整"


def t_pc_list(r):
    r.enter_feature("parentctrl")
    items = pc_list(r)
    required = ("_InstID", "Name", "ChildId", "Week",
                "StartHour", "StartMin", "EndHour", "EndMin", "FilterMode", "Enable")
    for it in items:
        for k in required:
            if k not in it:
                return "FAIL", f"规则 {it.get('_InstID', '?')} 缺少字段 {k}"
    return "PASS", f"共 {len(items)} 条规则，字段完整"


def t_dev_list(r):
    items = device_list(r)
    required = ("_InstID", "MACAddress", "IPAddress", "HostName", "Active", "Interface")
    if not items:
        return "FAIL", "未获取到任何已关联设备"
    for it in items:
        for k in required:
            if k not in it:
                return "FAIL", f"设备 {it.get('_InstID', '?')} 缺少字段 {k}"
        if not it["MACAddress"]:
            return "FAIL", f"设备 {it.get('_InstID', '?')} MAC 为空"
    return "PASS", f"共 {len(items)} 台设备，MAC/IP 字段完整"


def t_preempt_detect(r):
    """只读探测：检测是否被其他用户占用。不踢出（避免影响他人会话）。"""
    sessions = r.detect_preempt()
    if sessions is None:
        return "PASS", "无其他用户占用，登录正常"
    for s in sessions:
        if not all(k in s for k in ("sessid", "label", "ip", "user")):
            return "FAIL", f"占用会话字段不完整: {s}"
        if not re.fullmatch(r"[0-9a-fA-F]{64}", s["sessid"]):
            return "FAIL", f"sessid 格式异常: {s['sessid']}"
    return "PASS", f"检测到 {len(sessions)} 个占用会话（仅探测，未踢出）"


def _free_pf_ports(items, count=2):
    used = set()
    for it in items:
        for key in ("ExternalPort", "ExternalPortEndRange"):
            try:
                used.add(int(it.get(key)))
            except (TypeError, ValueError):
                pass
    return [p for p in range(30000, 50000) if p not in used][:count]


def t_pf_lifecycle(r, cfg, pf_client, ts):
    r.enter_feature("portforwarding")
    items = pf_list(r)
    if not pf_client:
        for it in items:
            if it.get("InternalClient"):
                pf_client = it["InternalClient"]
                break
        if not pf_client:
            pf_client = "192.168.2.100"
            print(f"        ^ 无现有规则可用，端口转发测试内网IP兜底为 {pf_client}")
    ports = _free_pf_ports(items)
    if len(ports) < 2:
        return "FAIL", "空闲测试端口不足"
    ext, ext2 = ports
    alias = f"SkillTest_{ts}"

    r.enter_feature("portforwarding")
    ok, err = pf_apply(r, alias, "TCP", pf_client, ext, internal_port=ext)
    if not ok:
        return "FAIL", f"新增失败: {err}"

    r.enter_feature("portforwarding")
    mine = next((it for it in pf_list(r) if it.get("Alias") == alias), None)
    if not mine:
        return "FAIL", "新增后列表中未找到该规则"
    inst_id = mine["_InstID"]
    _created.append(("pf", inst_id))

    alias_mod = alias + "_mod"
    r.enter_feature("portforwarding")
    ok, err = pf_apply(r, alias_mod, "TCP", pf_client, ext2, internal_port=ext2, inst_id=inst_id)
    if not ok:
        return "FAIL", f"修改失败: {err}"
    r.enter_feature("portforwarding")
    mine = next((it for it in pf_list(r) if it.get("_InstID") == inst_id), None)
    if not mine or mine.get("Alias") != alias_mod or mine.get("ExternalPort") != str(ext2):
        return "FAIL", f"修改未生效: {mine}"

    r.enter_feature("portforwarding")
    ok, err = pf_apply(r, alias, "TCP", pf_client, ext, internal_port=ext, inst_id=inst_id)
    if not ok:
        return "FAIL", f"还原失败: {err}"
    r.enter_feature("portforwarding")
    mine = next((it for it in pf_list(r) if it.get("_InstID") == inst_id), None)
    if not mine or mine.get("Alias") != alias or mine.get("ExternalPort") != str(ext):
        return "FAIL", f"还原未生效: {mine}"

    r.enter_feature("portforwarding")
    ok, err = pf_switch(r, inst_id, 0)
    if not ok:
        return "FAIL", f"关闭开关失败: {err}"
    r.enter_feature("portforwarding")
    mine = next((it for it in pf_list(r) if it.get("_InstID") == inst_id), None)
    if not mine or mine.get("Enable") != "0":
        return "FAIL", f"开关关闭未生效: {mine}"

    r.enter_feature("portforwarding")
    ok, err = pf_switch(r, inst_id, 1)
    if not ok:
        return "FAIL", f"开启开关失败: {err}"
    r.enter_feature("portforwarding")
    mine = next((it for it in pf_list(r) if it.get("_InstID") == inst_id), None)
    if not mine or mine.get("Enable") != "1":
        return "FAIL", f"开关开启未生效: {mine}"

    r.enter_feature("portforwarding")
    ok, err = pf_delete(r, inst_id)
    if not ok:
        return "FAIL", f"删除失败: {err}"
    r.enter_feature("portforwarding")
    if any(it.get("_InstID") == inst_id for it in pf_list(r)):
        return "FAIL", "删除后列表中仍存在该规则"
    _created.remove(("pf", inst_id))
    return "PASS", f"新增→验证→修改→还原→开关→删除 全部通过（测试端口 {ext}）"


def t_pc_lifecycle(r, cfg, pc_mac, ts):
    r.enter_feature("parentctrl")
    items = pc_list(r)
    if not pc_mac:
        for it in items:
            if it.get("ChildId"):
                pc_mac = it["ChildId"]
                break
    if not pc_mac:
        devs = device_list(r)
        for d in devs:
            if d.get("MACAddress"):
                pc_mac = d["MACAddress"]
                break
        if pc_mac:
            print(f"        ^ 从已关联设备列表取测试 MAC: {pc_mac}")
        else:
            return "SKIP", "无现有父母控制规则可用的已关联 MAC，可用 --pc-mac 指定后重跑"
    name = f"SkillTest_{ts}"

    r.enter_feature("parentctrl")
    ok, err = pc_apply(r, name, pc_mac, "127", 8, 0, 20, 0,
                       filter_mode="NotAllowed", enable=1)
    if not ok:
        return "FAIL", f"新增失败: {err}"

    r.enter_feature("parentctrl")
    mine = next((it for it in pc_list(r) if it.get("Name") == name), None)
    if not mine:
        return "FAIL", "新增后列表中未找到该规则"
    inst_id = mine["_InstID"]
    _created.append(("pc", inst_id))

    name_mod = name + "_mod"
    r.enter_feature("parentctrl")
    ok, err = pc_apply(r, name_mod, pc_mac, "127", 9, 0, 21, 0,
                       filter_mode="NotAllowed", enable=1, inst_id=inst_id)
    if not ok:
        return "FAIL", f"修改失败: {err}"
    r.enter_feature("parentctrl")
    mine = next((it for it in pc_list(r) if it.get("_InstID") == inst_id), None)
    if not mine or mine.get("Name") != name_mod or mine.get("StartHour") != "9":
        return "FAIL", f"修改未生效: {mine}"

    r.enter_feature("parentctrl")
    ok, err = pc_apply(r, name, pc_mac, "127", 8, 0, 20, 0,
                       filter_mode="NotAllowed", enable=1, inst_id=inst_id)
    if not ok:
        return "FAIL", f"还原失败: {err}"
    r.enter_feature("parentctrl")
    mine = next((it for it in pc_list(r) if it.get("_InstID") == inst_id), None)
    if not mine or mine.get("Name") != name or mine.get("StartHour") != "8":
        return "FAIL", f"还原未生效: {mine}"

    r.enter_feature("parentctrl")
    ok, err = pc_switch(r, inst_id, 0)
    if not ok:
        return "FAIL", f"关闭开关失败: {err}"
    r.enter_feature("parentctrl")
    mine = next((it for it in pc_list(r) if it.get("_InstID") == inst_id), None)
    if not mine or mine.get("Enable") != "0":
        return "FAIL", f"开关关闭未生效: {mine}"

    r.enter_feature("parentctrl")
    ok, err = pc_switch(r, inst_id, 1)
    if not ok:
        return "FAIL", f"开启开关失败: {err}"
    r.enter_feature("parentctrl")
    mine = next((it for it in pc_list(r) if it.get("_InstID") == inst_id), None)
    if not mine or mine.get("Enable") != "1":
        return "FAIL", f"开关开启未生效: {mine}"

    r.enter_feature("parentctrl")
    ok, err = pc_delete(r, inst_id)
    if not ok:
        return "FAIL", f"删除失败: {err}"
    r.enter_feature("parentctrl")
    if any(it.get("_InstID") == inst_id for it in pc_list(r)):
        return "FAIL", "删除后列表中仍存在该规则"
    _created.remove(("pc", inst_id))
    return "PASS", "新增→验证→修改→还原→开关→删除 全部通过"


def main():
    ap = argparse.ArgumentParser(description="routerman 技能全功能 E2E 测试")
    ap.add_argument("--env", default=".env", help="env 文件路径（默认 .env）")
    ap.add_argument("--pf-client", default="", help="端口转发测试用内网主机 IP")
    ap.add_argument("--pc-mac", default="", help="父母控制测试用已关联设备 MAC")
    ap.add_argument("--only", default="", help="只运行名称包含该关键字的用例")
    args = ap.parse_args()

    if not os.path.exists(args.env):
        print(f"错误: env 文件不存在: {args.env}")
        sys.exit(2)

    cfg = load_config(args.env)
    ts = time.strftime("%Y%m%d%H%M%S") + str(random.randint(100, 999))

    cases = [
        ("配置加载", t_config, (args.env,)),
        ("登录", t_login, ()),
        ("已关联设备列表(只读)", t_dev_list, ()),
        ("会话占用探测(只读)", t_preempt_detect, ()),
        ("端口转发列表(只读)", t_pf_list, ()),
        ("父母控制列表(只读)", t_pc_list, ()),
        ("端口转发 增改还原开关删", t_pf_lifecycle, (cfg, args.pf_client, ts)),
        ("父母控制 增改还原开关删", t_pc_lifecycle, (cfg, args.pc_mac, ts)),
    ]

    print("=" * 64)
    print("routerman 技能全功能 E2E 测试")
    print("=" * 64)

    r = Router(cfg)
    try:
        for name, fn, fargs in cases:
            if args.only and args.only not in name:
                continue
            if fn is t_config:
                run_case(name, fn, *fargs)
            else:
                run_case(name, fn, r, *fargs)
    finally:
        _cleanup(cfg)

    print("-" * 64)
    passed = sum(1 for _, s in RESULTS if s == "PASS")
    failed = sum(1 for _, s in RESULTS if s == "FAIL")
    skipped = sum(1 for _, s in RESULTS if s == "SKIP")
    print(f"总计: {len(RESULTS)} 用例 | PASS {passed} | FAIL {failed} | SKIP {skipped}")
    for name, s in RESULTS:
        mark = "✔" if s == "PASS" else ("✘" if s == "FAIL" else "·")
        print(f"  {mark} {s:4} {name}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
