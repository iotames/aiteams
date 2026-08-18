#!/usr/bin/env python3
"""大规模企业邮箱迁移辅助脚本（腾讯企业邮 IMAP → Exchange Online）。

子命令：
  validate  校验源 CSV（官方三列必填，附加列原样透传）
  generate  生成 EXO 迁移 CSV（Password=源密码，附加列如 TargetEmailPassword 透传）
  split     按批拆分迁移 CSV（默认 50 人/批，供小批量验证与分批迁移）
  analyze   解析分析批处理统计，筛超限名单（默认 >45GB 或 >50 万条）
  verify    迁移后核对报告（文件夹统计，含已删除邮件覆盖情况）
  state     读写阶段状态文件，供交互式工作流在人工切会话时共享进度

交互式闭环说明：
  技能产出精排 PowerShell 命令 → 你粘贴执行 → 结果导出到 output/email-migration/
  → 脚本消费该文件（analyze/verify/probe）→ 技能据结果推进 state → 进入下一阶段。
  output/ 已入 .gitignore，含密码产物不会进仓库。

安全约束：
  - 密码仅在本机代码内流转，任何输出/日志不得出现密码原文
  - 含密码的产物默认写入 <cwd>/output/email-migration/（已被 .gitignore 忽略）

可配置项（不写死，均可用环境变量或命令行覆盖）：
  - EMAIL_MIGRATION_REQUIRED_COLS    必填列（默认 EmailAddress,UserName,Password）
  - EMAIL_MIGRATION_SUBDIR           输出子目录（默认 email-migration）
  - EMAIL_MIGRATION_OUTPUT           输出根目录（默认 output）
  - EMAIL_MIGRATION_IMAP_HOST/_PORT  源 IMAP 服务器（默认 imap.exmail.qq.com:993 SSL）
  - CLI: --size-gb/--count/--batch-size/--host/--port/--output
"""

from __future__ import annotations

import argparse
import csv
import imaplib
import re
import ssl
import sys
from datetime import datetime
from pathlib import Path

# 官方 IMAP 迁移 CSV 必填列（可用环境变量 EMAIL_MIGRATION_REQUIRED_COLS 覆盖，逗号分隔）
def _required_columns() -> tuple[str, ...]:
    import os
    raw = os.environ.get("EMAIL_MIGRATION_REQUIRED_COLS", "EmailAddress,UserName,Password")
    return tuple(c.strip() for c in raw.split(",") if c.strip())


REQUIRED_COLUMNS = _required_columns()

# 输出子目录（可用环境变量 EMAIL_MIGRATION_SUBDIR 覆盖，避免强绑定为 email-migration）
def _output_subdir() -> str:
    import os
    return os.environ.get("EMAIL_MIGRATION_SUBDIR", "email-migration")


# 输出根目录默认值（可用 EMAIL_MIGRATION_OUTPUT 覆盖）
def _output_default() -> str:
    import os
    return os.environ.get("EMAIL_MIGRATION_OUTPUT", "output")


# 源 IMAP 主机/端口默认值（可用 EMAIL_MIGRATION_IMAP_HOST / _PORT 覆盖，非强绑定腾讯）
def _imap_host_default() -> str:
    import os
    return os.environ.get("EMAIL_MIGRATION_IMAP_HOST", "imap.exmail.qq.com")


def _imap_port_default() -> int:
    import os
    return int(os.environ.get("EMAIL_MIGRATION_IMAP_PORT", "993"))


# 官方迁移硬限制：单邮箱最多 50 万项、单封最大 35MB；超限判断阈值留 5GB 余量
# 均可通过 --size-gb / --count / --batch-size 覆盖，见 build_parser
DEFAULT_SIZE_THRESHOLD_GB = 45
DEFAULT_COUNT_THRESHOLD = 500_000
DEFAULT_BATCH_SIZE = 50

# 交互式工作流阶段顺序（state 文件据此校验与推进入口）
PHASES = ["phase0", "phase1", "phase2", "phase3", "phase4"]
PHASE_LABELS = {
    "phase0": "阶段0-前置检查",
    "phase1": "阶段1-分析与超限识别",
    "phase2": "阶段2-小批量验证",
    "phase3": "阶段3-分批正式迁移",
    "phase4": "阶段4-收尾核对",
}
DEFAULT_STATE_FILE = "email-migration-state.json"


def _default_state() -> dict:
    return {"phase": "phase0", "done": {}, "pending_confirm": [], "notes": []}


def load_state(path: Path) -> dict:
    import json
    if not path.exists():
        return _default_state()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_state()


def write_state(path: Path, state: dict) -> None:
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _phase_to_index(p: str) -> int:
    return PHASES.index(p) if p in PHASES else 0


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """读取 CSV（兼容 UTF-8 BOM），返回表头与行字典列表。"""
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return header, rows


def write_csv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    """写出 CSV（UTF-8 BOM），保证 Excel/Exchange Online 均可识别。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def validate(path: Path, *, quiet: bool = False) -> tuple[list[str], list[dict[str, str]], list[str]]:
    """校验源 CSV，返回 (表头, 行, 错误列表)。错误列表非空时调用方应终止。"""
    header, rows = load_csv(path)
    errors: list[str] = []

    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        errors.append(f"缺少必填列: {', '.join(missing)}")
        return header, rows, errors

    empty_required = [c for c in REQUIRED_COLUMNS if any(not (r.get(c) or "").strip() for r in rows)]
    if empty_required:
        errors.append(f"存在必填列空值: {', '.join(empty_required)}")

    dup_target = _find_duplicates(r.get("EmailAddress", "").strip() for r in rows)
    dup_source = _find_duplicates(r.get("UserName", "").strip() for r in rows)
    if dup_target:
        errors.append(f"EmailAddress 重复 {len(dup_target)} 项")
    if dup_source:
        errors.append(f"UserName 重复 {len(dup_source)} 项")

    if not quiet:
        extra = [c for c in header if c not in REQUIRED_COLUMNS]
        print(f"[OK] 表头: {', '.join(header)}")
        print(f"[OK] 数据行: {len(rows)}")
        if extra:
            print(f"[提示] 附加列（将原样透传，官方命令需 -AllowUnknownColumnsInCsv $true）: {', '.join(extra)}")
        if errors:
            for e in errors:
                print(f"[错误] {e}")
    return header, rows, errors


def _find_duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    dup: list[str] = []
    for v in values:
        if not v:
            continue
        if v.lower() in seen and v.lower() not in dup:
            dup.append(v.lower())
        seen.add(v.lower())
    return dup


def cmd_validate(args: argparse.Namespace) -> int:
    _header, _rows, errors = validate(Path(args.csv))
    return 1 if errors else 0


def cmd_generate(args: argparse.Namespace) -> int:
    src = Path(args.csv)
    header, rows, errors = validate(src, quiet=True)
    if errors:
        print("[错误] 源 CSV 校验失败，未生成迁移文件：")
        for e in errors:
            print(f"  - {e}")
        return 1

    # 官方三列在前，附加列按源文件顺序透传
    ordered = list(REQUIRED_COLUMNS) + [c for c in header if c not in REQUIRED_COLUMNS]
    out_dir = Path(args.output) / _output_subdir()
    if args.dry_run:
        print(f"[OK] 校验通过（dry-run，不写文件）: {len(rows)} 行")
        return 0

    out = out_dir / f"migration_{_now_stamp()}.csv"
    write_csv(out, ordered, rows)
    print(f"[OK] 已生成迁移 CSV: {out}")
    print(f"[OK] 数据行: {len(rows)}")
    extra = [c for c in ordered if c not in REQUIRED_COLUMNS]
    if extra:
        print(f"[提示] 透传附加列（官方命令需 -AllowUnknownColumnsInCsv $true）: {', '.join(extra)}")
    print("[提示] 该文件含源邮箱密码，请勿提交仓库、勿在日志中打印")
    return 0


def cmd_split(args: argparse.Namespace) -> int:
    src = Path(args.csv)
    header, rows, errors = validate(src, quiet=True)
    if errors:
        print("[错误] CSV 校验失败，未拆分：")
        for e in errors:
            print(f"  - {e}")
        return 1

    batch_size = args.batch_size
    if batch_size <= 0:
        print("[错误] --batch-size 必须为正整数")
        return 2

    out_dir = Path(args.output) / _output_subdir() / "batches"
    out_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    for i, start in enumerate(range(0, len(rows), batch_size), start=1):
        chunk = rows[start : start + batch_size]
        out = out_dir / f"batch_{i:03d}.csv"
        write_csv(out, header, chunk)
        total += len(chunk)
        print(f"[OK] {out}  共 {len(chunk)} 行")
    print(f"[OK] 共拆分 {max(1, (len(rows) + batch_size - 1) // batch_size)} 批，合计 {total} 行")
    return 0


def _parse_size_bytes(raw: str) -> int:
    """解析 EstimatedTotalTransferSize 的格式化值，如 '28.45 GB (30,551,458,399 bytes)'。"""
    text = (raw or "").strip()
    m = re.search(r"\(([\d,]+)\s*bytes\)", text)
    if m:
        return int(m.group(1).replace(",", ""))
    m = re.search(r"([\d.]+)\s*(GB|MB|KB|B)", text, re.IGNORECASE)
    if m:
        value = float(m.group(1))
        unit = m.group(2).upper()
        return int(value * {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}[unit])
    # 纯数字（字节）或带千分位数字：直接当字节数
    digits = text.replace(",", "").strip()
    if digits and digits.isdigit():
        return int(digits)
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    header, rows = load_csv(Path(args.csv))
    identity_col = next((c for c in ("Identity", "EmailAddress") if c in header), None)
    count_col = next((c for c in ("EstimatedTotalCount", "TotalItemsInSourceMailboxCount") if c in header), None)
    size_col = next((c for c in ("EstimatedTotalSize", "EstimatedTotalTransferSize") if c in header), None)
    if not identity_col or not count_col or not size_col:
        print(f"[错误] 统计 CSV 缺少必需列（Identity/EmailAddress、EstimatedTotalCount、EstimatedTotalSize）")
        print(f"      实际表头: {', '.join(header)}")
        return 1

    size_limit = args.size_gb * 1024**3
    report: list[dict[str, str]] = []
    over_size = over_count = 0
    for r in rows:
        size_bytes = _parse_size_bytes(r.get(size_col, ""))
        try:
            count = int(float((r.get(count_col) or "0").replace(",", "")))
        except ValueError:
            count = 0
        flag_size = size_bytes > size_limit
        flag_count = count > args.count
        report.append({
            identity_col: r.get(identity_col, ""),
            "EstimatedTotalCount": str(count),
            "EstimatedTotalSizeBytes": str(size_bytes),
            "OverSizeLimit": "是" if flag_size else "否",
            "OverCountLimit": "是" if flag_count else "否",
        })
        over_size += flag_size
        over_count += flag_count

    out_dir = Path(args.output) / _output_subdir()
    out = out_dir / f"analysis_report_{_now_stamp()}.csv"
    write_csv(out, list(report[0].keys()) if report else [identity_col, "EstimatedTotalCount", "EstimatedTotalSizeBytes", "OverSizeLimit", "OverCountLimit"], report)
    print(f"[OK] 分析报告: {out}")
    print(f"[OK] 统计邮箱数: {len(report)}，超 {args.size_gb}GB: {over_size}，超 {args.count} 条: {over_count}")
    if args.show_identities:
        for r in report:
            if r["OverSizeLimit"] == "是" or r["OverCountLimit"] == "是":
                print(f"  - {r[identity_col]} (条数 {r['EstimatedTotalCount']}, 大小 {r['EstimatedTotalSizeBytes']} bytes)")
    return 0


def _normalize_folder(folder: str) -> str:
    """归一化文件夹路径：去掉首尾斜杠，按路径段精确判分类别。

    用路径段精确匹配而非子串匹配，避免「收件箱备份」等含关键词的文件夹被误判为收件箱。
    首段为 Inbox/收件箱 = 收件箱；其余按 Deleted/Trash/已删除/档案标记分类，否则归为其他。
    """
    segments = [s for s in re.split(r"[/\\]+", folder.strip()) if s]
    if not segments:
        return "other"
    first = segments[0].lower()
    if first == "inbox" or first == "收件箱":
        return "inbox"
    if any(k in first for k in ("deleted", "trash", "已删除")):
        return "deleted"
    # 注意：仅按首段分类，`/Inbox/sub` 首段为 inbox 会并入收件箱，`/Sent Items/sub` 首段非 inbox 则归 other。
    return "other"


def cmd_verify(args: argparse.Namespace) -> int:
    """核对文件夹统计 CSV（列: Identity/EmailAddress, FolderPath, ItemsInFolder），输出逐邮箱报告。

    提供 --manifest（迁移名单 CSV，含 EmailAddress 列）时：
      - 名单中有、但统计 CSV 中完全缺失的邮箱 → 标记为失败候选（MissingInStats=是，疑似迁移失败/未导出）。
      - EmptyTarget 定义为该邮箱所有文件夹 items 总和为 0。
    不提供 manifest 时保持现状，EmptyTarget 同样按 items 总和判断（不再使用 folders==0）。
    """
    header, rows = load_csv(Path(args.csv))
    identity_col = next((c for c in ("Identity", "EmailAddress") if c in header), None)
    folder_col = next((c for c in ("FolderPath", "Name") if c in header), None)
    items_col = next((c for c in ("ItemsInFolder", "ItemsInFolderAndSubfolders", "Items") if c in header), None)
    if not identity_col or not folder_col or not items_col:
        print("[错误] 文件夹统计 CSV 缺少必需列（Identity/EmailAddress、FolderPath、ItemsInFolder）")
        return 1

    # 读取迁移名单（可选）：用于探测名单中有但统计中缺失的邮箱
    manifest_set: set[str] | None = None
    if args.manifest:
        m_header, m_rows = load_csv(Path(args.manifest))
        m_addr_col = next((c for c in ("EmailAddress", "Identity") if c in m_header), None)
        if m_addr_col is None:
            print(f"[错误] manifest 缺少 EmailAddress 列，实际表头: {', '.join(m_header)}")
            return 1
        manifest_set = {r.get(m_addr_col, "").strip().lower() for r in m_rows if r.get(m_addr_col, "").strip()}

    per_mailbox: dict[str, dict[str, int]] = {}
    for r in rows:
        ident = r.get(identity_col, "").strip().lower()
        folder = r.get(folder_col, "").strip()
        try:
            items = int(float((r.get(items_col) or "0").replace(",", "")))
        except ValueError:
            items = 0
        mb = per_mailbox.setdefault(ident, {"folders": 0, "inbox": 0, "deleted": 0, "other": 0})
        mb["folders"] += 1
        cat = _normalize_folder(folder)
        mb[cat] += items

    report_header = ["EmailAddress", "FolderCount", "InboxItems", "DeletedItems", "OtherItems", "EmptyTarget", "DeletedItemsNotCleared"]
    if manifest_set is not None:
        report_header.append("MissingInStats")

    report: list[dict[str, str]] = []
    # 先喂入名单中但统计缺失的邮箱（失败候选），再按字母序输出统计中的邮箱
    if manifest_set is not None:
        missing_n = 0
        for ident in sorted(manifest_set):
            if ident not in per_mailbox:
                report.append({
                    "EmailAddress": ident,
                    "FolderCount": "0",
                    "InboxItems": "0",
                    "DeletedItems": "0",
                    "OtherItems": "0",
                    "EmptyTarget": "是",
                    "DeletedItemsNotCleared": "否",
                    "MissingInStats": "是",
                })
                missing_n += 1
    for ident, mb in sorted(per_mailbox.items()):
        # 空目标定义：该邮箱所有文件夹 items 总和为 0（而非 folders==0，避免漏报真正空目标）
        empty = (mb["inbox"] + mb["deleted"] + mb["other"]) == 0
        deleted_not_cleared = mb["deleted"] > 0
        row = {
            "EmailAddress": ident,
            "FolderCount": str(mb["folders"]),
            "InboxItems": str(mb["inbox"]),
            "DeletedItems": str(mb["deleted"]),
            "OtherItems": str(mb["other"]),
            "EmptyTarget": "是" if empty else "否",
            "DeletedItemsNotCleared": "是" if deleted_not_cleared else "否",
        }
        if manifest_set is not None:
            row["MissingInStats"] = "否"
        report.append(row)

    out_dir = Path(args.output) / _output_subdir()
    out = out_dir / f"verify_report_{_now_stamp()}.csv"
    write_csv(out, report_header, report)
    print(f"[OK] 核对报告: {out}")
    print(f"[OK] 覆盖邮箱数: {len(report)}")
    empty_n = sum(1 for r in report if r["EmptyTarget"] == "是")
    deleted_n = sum(1 for r in report if r["DeletedItemsNotCleared"] == "是")
    if empty_n:
        print(f"[警告] 空目标邮箱: {empty_n} 个（需人工确认是否迁移失败）")
    if manifest_set is not None:
        missing_n = sum(1 for r in report if r["MissingInStats"] == "是")
        if missing_n:
            print(f"[警告] 名单中有但统计缺失的邮箱 {missing_n} 个（疑似迁移失败/未导出）")
    if deleted_n:
        print(f"[提示] 已删除邮件有内容: {deleted_n} 个（确认这些邮件是否应进入目标邮箱）")
    return 0


def _mask_email(addr: str) -> str:
    """终端脱敏显示：本地部分只保留首尾字符，域名完整。"""
    local, _, domain = addr.partition("@")
    if not domain:
        return "***"
    if len(local) <= 2:
        return local[0] + "***@" + domain
    return local[:1] + "***" + local[-1:] + "@" + domain


def _parse_list_folder(line: bytes) -> tuple[str, str] | None:
    """解析 IMAP LIST 行，返回 (解码显示名, 原始编码名)。

    select 必须用原始编码名（与服务端一致）；腾讯手写中文/特殊文件夹名用
    imaplib 解码后仍含乱码，直接 select 会失败，因此 select 用 raw_name，
    仅展示用解码名。
    """
    text = line.decode("utf-8", "replace").strip()
    # 邮箱名可能带引号（含空格/特殊字符时服务端强制）或无引号（纯简单名，如 INBOX）。
    # 只认带引号会静默丢弃不带引号的真实文件夹 → probe 低估邮件数，故两者都支持。
    quoted = re.search(r'"([^"]*)"\s*$', text)
    if quoted:
        raw = quoted.group(1)
    else:
        fields = text.split()
        if len(fields) < 2:
            return None
        raw = fields[-1]
    try:
        decoded = imaplib.UTF7.decode(raw)
    except Exception:
        decoded = raw
    return decoded, raw


def _needs_quote(name: str) -> bool:
    """IMAP select/status 的邮箱名参数含空格或特殊字符时必须加引号，否则报 parameters 错。"""
    return any(ch in name for ch in ' \t"%*[]{}')



def cmd_state(args: argparse.Namespace) -> int:
    """读写交互式阶段状态：人工切会话时用共享的 output 状态文件记住进度。"""
    path = Path(args.output) / _output_subdir() / "state" / args.state_file
    state = load_state(path)

    if args.phase and args.phase not in PHASES:
        print(f"[错误] 未知阶段: {args.phase}（可选 {', '.join(PHASES)}）")
        return 2

    phase_changed = False
    if args.phase:
        state["phase"] = args.phase
        phase_changed = True
        print(f"[OK] 跳转至: {args.phase}（{PHASE_LABELS.get(args.phase, '')}）")

    if args.advance:
        # advance 标记当前 phase 完成（若本调用同时指定了 --phase，则完成新置的阶段）
        state["done"][state["phase"]] = True
        print(f"[OK] 完成阶段 {state['phase']}（{PHASE_LABELS.get(state['phase'], '')}）")
        idx = _phase_to_index(state["phase"])
        if idx + 1 < len(PHASES):
            state["phase"] = PHASES[idx + 1]
            print(f"[OK] 已推进至: {state['phase']}（{PHASE_LABELS.get(state['phase'], '')}）")
        else:
            print("[OK] 已到达最终阶段（收尾后由 verify 确认完成）")
        phase_changed = True

    if args.note:
        state["notes"].append(args.note)
        print(f"[OK] 已记录备注: {args.note}")

    if args.todo:
        t = args.todo
        if t not in state["pending_confirm"]:
            state["pending_confirm"].append(t)
        print(f"[OK] 待确认: {t}")
        write_state(path, state)
        return 0

    if args.confirm:
        c = args.confirm
        if c in state["pending_confirm"]:
            state["pending_confirm"].remove(c)
            print(f"[OK] 已确认: {c}")
        else:
            print(f"[提示] 待确认列表中没有: {c}")

    write_state(path, state)
    print(f"[OK] 状态文件: {path}")
    print(f"[OK] 当前阶段: {state['phase']}（{PHASE_LABELS.get(state['phase'], '')}）")
    print(f"[OK] 已完成阶段: {', '.join(state.get('done', {})) if state.get('done') else '无'}")
    if state.get("pending_confirm"):
        print(f"[提示] 待确认项: {', '.join(state['pending_confirm'])}")
    else:
        print("[OK] 无待确认项")
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    """连接源 IMAP 服务器，逐账号统计文件夹与邮件数（密码仅在内存，不落盘）。"""
    src = Path(args.csv)
    _header, rows, errors = validate(src, quiet=True)
    if errors:
        print("[错误] 源 CSV 校验失败，未执行探测：")
        for e in errors:
            print(f"  - {e}")
        return 1

    ctx = ssl.create_default_context()
    details: list[dict[str, str]] = []
    for r in rows:
        user = (r.get("UserName") or "").strip()
        password = (r.get("Password") or "").strip()
        try:
            with imaplib.IMAP4_SSL(args.host, args.port, ssl_context=ctx, timeout=args.timeout) as m:
                m.login(user, password)
                _typ, folders = m.list()
                folder_rows: list[tuple[str, int, int]] = []
                for line in folders:
                    parsed = _parse_list_folder(line)
                    if not parsed:
                        continue
                    name, raw_name = parsed
                    # imaplib select/status 不会自动加引号：名字含空格/特殊符时服务端报
                    # 'BAD EXAMINE parameters'，需手动加双引号包裹（有空格等字符才需要）
                    mailbox = f'"{raw_name}"' if _needs_quote(raw_name) else raw_name
                    try:
                        typ, data = m.select(mailbox, readonly=True)
                        if typ != "OK":
                            details.append({"SourceEmail": user, "FolderName": name, "MailCount": "", "MailSizeBytes": "", "Status": f"SELECT 失败: {typ}"})
                            continue
                        count = int(data[0]) if data and data[0] else 0
                        size = 0
                        if count > 0:
                            # 优先 STATUS (MESSAGES SIZE) 单次拿字节；失败/为 0 再逐封 RFC822.SIZE 求和
                            try:
                                _st, sndata = m.status(mailbox, "(MESSAGES SIZE)")
                                sm = re.search(r"SIZE\s+(\d+)", sndata[0].decode("utf-8", "replace") if sndata else "")
                                if sm:
                                    size = int(sm.group(1))
                            except Exception:
                                size = 0
                            if size == 0:
                                try:
                                    _t, nums = m.search(None, "ALL")
                                    ids = (nums[0] or b"").split() if nums and nums[0] else []
                                    for i in ids:
                                        _rt, rdata = m.fetch(i, "(RFC822.SIZE)")
                                        sm2 = re.search(r"RFC822.SIZE\s+(\d+)", rdata[0].decode("utf-8", "replace") if rdata else "")
                                        if sm2:
                                            size += int(sm2.group(1))
                                except Exception:
                                    size = 0
                        folder_rows.append((name, count, size))
                    except Exception as e:
                        details.append({"SourceEmail": user, "FolderName": name, "MailCount": "", "MailSizeBytes": "", "Status": f"SELECT 异常: {e.__class__.__name__}"})
                m.logout()
            total = sum(c for _n, c, _s in folder_rows)
            total_size = sum(s for _n, _c, s in folder_rows)
            total_mb = total_size / 1024 / 1024
            print(f"[OK] {_mask_email(user)}: 文件夹 {len(folder_rows)} 个，邮件总数 {total}，空间占用 {total_mb:.2f} MB")
            for name, count, size in folder_rows:
                details.append({"SourceEmail": user, "FolderName": name, "MailCount": str(count), "MailSizeBytes": str(size), "Status": "OK"})
        except (imaplib.IMAP4.error, OSError, ssl.SSLError) as e:
            print(f"[警告] {_mask_email(user)}: 连接失败（{e.__class__.__name__}）")
            details.append({"SourceEmail": user, "FolderName": "", "MailCount": "", "MailSizeBytes": "", "Status": f"失败: {e.__class__.__name__}"})

    out_dir = Path(args.output) / _output_subdir()
    out = out_dir / f"probe_report_{_now_stamp()}.csv"
    write_csv(out, ["SourceEmail", "FolderName", "MailCount", "MailSizeBytes", "Status"], details)
    print(f"[OK] 探测报告: {out}")
    print("[提示] 邮件总数受腾讯'收取范围'影响：若为'最近30天'，看到的只是近30天邮件")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="大规模企业邮箱迁移辅助脚本")
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="校验源 CSV（官方三列必填）")
    p_validate.add_argument("csv", help="源 CSV 路径")
    p_validate.set_defaults(func=cmd_validate)

    p_generate = sub.add_parser("generate", help="生成 EXO 迁移 CSV（含密码，附加列透传）")
    p_generate.add_argument("csv", help="源 CSV 路径")
    p_generate.add_argument("--output", default=_output_default(), help="产物根目录（可环境变量 EMAIL_MIGRATION_OUTPUT 覆盖）")
    p_generate.add_argument("--dry-run", action="store_true", help="只校验不写文件")
    p_generate.set_defaults(func=cmd_generate)

    p_split = sub.add_parser("split", help="按批拆分迁移 CSV")
    p_split.add_argument("csv", help="迁移 CSV 路径")
    p_split.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help=f"每批人数（默认 {DEFAULT_BATCH_SIZE}）")
    p_split.add_argument("--output", default=_output_default(), help="产物根目录（可环境变量 EMAIL_MIGRATION_OUTPUT 覆盖）")
    p_split.set_defaults(func=cmd_split)

    p_analyze = sub.add_parser("analyze", help="解析迁移分析统计，筛超限名单")
    p_analyze.add_argument("csv", help="Get-MigrationUserStatistics 导出的统计 CSV")
    p_analyze.add_argument("--size-gb", type=float, default=DEFAULT_SIZE_THRESHOLD_GB, help=f"大小阈值 GB（默认 {DEFAULT_SIZE_THRESHOLD_GB}）")
    p_analyze.add_argument("--count", type=int, default=DEFAULT_COUNT_THRESHOLD, help=f"条数阈值（默认 {DEFAULT_COUNT_THRESHOLD}，可调）")
    p_analyze.add_argument("--output", default=_output_default(), help="产物根目录（可环境变量 EMAIL_MIGRATION_OUTPUT 覆盖）")
    p_analyze.add_argument("--show-identities", action="store_true", help="在终端列出超限邮箱（默认只写入报告文件）")
    p_analyze.set_defaults(func=cmd_analyze)

    p_verify = sub.add_parser("verify", help="生成迁移后文件夹核对报告")
    p_verify.add_argument("csv", help="Get-MailboxFolderStatistics 导出的文件夹统计 CSV")
    p_verify.add_argument("--manifest", default=None, help="迁移名单 CSV（含 EmailAddress 列）；提供时额外探测名单中但统计缺失的邮箱（失败候选）")
    p_verify.add_argument("--output", default=_output_default(), help="产物根目录（可环境变量 EMAIL_MIGRATION_OUTPUT 覆盖）")
    p_verify.set_defaults(func=cmd_verify)

    p_probe = sub.add_parser("probe", help="连接源 IMAP，逐账号统计文件夹与邮件数（迁移前容量摸底）")
    p_probe.add_argument("csv", help="源 CSV 路径")
    p_probe.add_argument("--host", default=_imap_host_default(), help=f"源 IMAP 服务器（默认 {_imap_host_default()}，可环境变量覆盖）")
    p_probe.add_argument("--port", type=int, default=_imap_port_default(), help=f"源 IMAP 端口（默认 {_imap_port_default()} SSL）")
    p_probe.add_argument("--timeout", type=int, default=30, help="单账号连接超时秒数（默认 30）")
    p_probe.add_argument("--output", default=_output_default(), help="产物根目录")
    p_probe.set_defaults(func=cmd_probe)

    p_state = sub.add_parser("state", help="读写交互式阶段状态（跨会话共享进度）")
    p_state.add_argument("--output", default=_output_default(), help="产物根目录（可环境变量 EMAIL_MIGRATION_OUTPUT 覆盖）")
    p_state.add_argument("--state-file", default=DEFAULT_STATE_FILE, help=f"状态文件名（默认 {DEFAULT_STATE_FILE}）")
    p_state.add_argument("--phase", choices=PHASES, help=f"跳转到指定阶段: {'/'.join(PHASES)}")
    p_state.add_argument("--advance", action="store_true", help="标记当前阶段完成并推进到下一阶段")
    p_state.add_argument("--note", help="记录一条备注")
    p_state.add_argument("--todo", help="新增一条待确认项")
    p_state.add_argument("--confirm", help="标记一条待确认项已确认")
    p_state.set_defaults(func=cmd_state)

    return parser


def main(argv: list[str] | None = None) -> int:
    # 终端输出统一 UTF-8，避免 Windows 非 UTF-8 控制台中文乱码（纯显示层，不影响文件写入/解析）。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
