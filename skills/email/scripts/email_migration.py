#!/usr/bin/env python3
"""大规模企业邮箱迁移辅助脚本（腾讯企业邮 IMAP → Exchange Online）。

子命令：
  validate  校验源 CSV（官方三列必填，附加列原样透传）
  generate  生成 EXO 迁移 CSV（Password=源密码，附加列如 TargetEmailPassword 透传）
  split     按批拆分迁移 CSV（默认 50 人/批，供小批量验证与分批迁移）
  analyze   解析分析批处理统计，筛超限名单（默认 >45GB 或 >50 万条）
  probe     连接源 IMAP 逐账号摸底（文件夹/邮件数/占用字节），附逐账号汇总表
  check     只验证源 IMAP 登录可用性（登录即登出，不统计邮件），支持多个 CSV
  backfill  把 probe 汇总表统计列按 UserName=email 回填源清单
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
import subprocess
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


def validate(
    path: Path, *, quiet: bool = False, ignore_target_email: bool = False
) -> tuple[list[str], list[dict[str, str]], list[str]]:
    """校验源 CSV，返回 (表头, 行, 错误列表)。错误列表非空时调用方应终止。

    ignore_target_email: 跳过 EmailAddress 的空值/重复校验（源 IMAP 探测等
    只需 UserName/Password 的场景，目标邮箱未填不应阻断）。
    """
    header, rows = load_csv(path)
    errors: list[str] = []

    required = [c for c in REQUIRED_COLUMNS if not (ignore_target_email and c == "EmailAddress")]
    missing = [c for c in required if c not in header]
    if missing:
        errors.append(f"缺少必填列: {', '.join(missing)}")
        return header, rows, errors

    empty_required = [c for c in required if any(not (r.get(c) or "").strip() for r in rows)]
    if empty_required:
        errors.append(f"存在必填列空值: {', '.join(empty_required)}")

    if not ignore_target_email:
        dup_target = _find_duplicates(r.get("EmailAddress", "").strip() for r in rows)
        if dup_target:
            errors.append(f"EmailAddress 重复 {len(dup_target)} 项")
    dup_source = _find_duplicates(r.get("UserName", "").strip() for r in rows)
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



def cmd_backfill(args: argparse.Namespace) -> int:
    """把 probe 汇总表（email_check_success_*.csv）的统计列回填到源清单 CSV。

    按 源清单.UserName = 汇总表.email 匹配（去首尾空格、忽略大小写）；
    匹配不到或探测失败的行统计列留空。只增补统计列，不改动原有列（含密码），文件就地更新。
    """
    summary_path = Path(args.summary)
    fn = Path(args.csv)
    for p in (summary_path, fn):
        if not p.is_file():
            print(f"[错误] 文件不存在: {p}")
            return 1
    try:
        with summary_path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            summary = list(reader)
            summary_fields = list(reader.fieldnames or [])
    except OSError as e:
        print(f"[错误] 汇总表读取失败: {e}")
        return 1
    if "email" not in summary_fields:
        print(f"[错误] 汇总表缺少 email 列（实际表头: {', '.join(summary_fields) or '空'}）: {summary_path}")
        return 1
    data = {
        (r.get("email") or "").strip().lower(): r
        for r in summary
    }
    try:
        with fn.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames or [])
            rows = list(reader)
    except OSError as e:
        print(f"[错误] 源清单读取失败: {e}")
        return 1
    if not rows:
        print(f"[错误] {fn} 无数据行")
        return 1
    if any(None in r for r in rows):
        # 行字段多于表头时 DictWriter 会中途失败，就地更新会把源文件截断，必须先中止
        print(f"[错误] {fn} 存在列数多于表头的行，已中止回填（请先修正该 CSV）")
        return 1
    stat_cols = ["total_count", "total_size", "size_text(MB)"]
    header = fieldnames + [c for c in stat_cols if c not in fieldnames]
    filled = 0
    for r in rows:
        d = data.get((r.get("UserName") or "").strip().lower())
        if d and d.get("total_count"):  # "0" 亦有效（0 封邮箱照常回填）；空串=探测失败，留空
            for c in stat_cols:
                r[c] = d.get(c, "")
            filled += 1
    with fn.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(rows)
    print(f"[OK] 回填 {filled}/{len(rows)} 行 → {fn}")
    if filled < len(rows):
        print(f"[提示] {len(rows) - filled} 行未回填（汇总表无匹配或该账号探测失败，统计列留空）")
    return 0


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


def _fetch_size_sum(m: imaplib.IMAP4_SSL, count: int) -> int:
    """统计当前已 select 文件夹的邮件字节总量。

    FETCH 1:* (RFC822.SIZE) 是 RFC 3501 强制支持项，腾讯 IMAP 必然可用，
    整个文件夹一次网络往返；仅当个别服务端对超大范围报错时，才退到分批区间。
    返回 0 表示统计失败（count>0 却拿不到尺寸）。
    """
    def _sum(rdata) -> int:
        text = b" ".join(d for d in rdata if isinstance(d, bytes)).decode("utf-8", "replace")
        return sum(int(x) for x in re.findall(r"RFC822\.SIZE\s+(\d+)", text))

    try:
        _rt, rdata = m.fetch("1:*", "(RFC822.SIZE)")
        return _sum(rdata)
    except Exception:
        pass
    total = 0
    batch_size = 2000
    try:
        for start in range(1, count + 1, batch_size):
            end = min(start + batch_size - 1, count)
            _rt, rdata = m.fetch(f"{start}:{end}", "(RFC822.SIZE)")
            total += _sum(rdata)
    except Exception:
        # 分批也拿不到：按本函数约定返回 0=统计失败，上层保留邮件数、尺寸记 0，不误标 SELECT 异常
        return 0
    return total


RETRY_WAIT_SECONDS = 3

PROBE_EPILOG = """probe 可选参数说明（多拿什么数据 / 是否增加耗时）：
  --manifest <csv>  额外产出「目标邮箱」列（EmailAddress）；只读本地文件，不增加联网耗时。
  --detail          产出逐文件夹明细 probe_report_*.csv（默认开）；采集本就逐文件夹进行，不增加联网耗时，
                    只是多落一个几百 KB 的底账文件（源侧逐文件夹对账/失败原因追溯的唯一来源）。
  --no-detail       不产出逐文件夹明细；省一个文件，但源侧逐文件夹底账缺失，后续核对只能重跑 probe。
  --no-size         跳过 SIZE 累加，只统计邮件数；更快（大账号每文件夹可省数秒），
                    但汇总表与迁移报告拿不到「空间占用」，验收报告不可用。
  --retry N         账号连接失败后重试 N 次（每次间隔 3 秒）；提升弱网/节流下成功率，明显增加耗时。
  --timeout S       单账号连接超时（默认 30 秒）；调小更快失败，调大适合慢账号/大账号。
  --host/--port     源 IMAP 服务器与端口（默认腾讯企业邮），不改变耗时。
  --output DIR      产物根目录（默认 output，内部自动拼 email-migration/ 子目录）。
"""


def _probe_one_account(user: str, password: str, *, host: str, port: int, timeout: int, ctx, collect_size: bool):
    """探测单个源账号，返回 (folder_rows, 明细行, 错误信息)。

    folder_rows: [(文件夹名, 邮件数, 字节数)]；错误信息为空字符串表示成功。
    密码只在本函数内存中流转，不进入任何返回值、日志或产物。
    """
    folder_rows: list[tuple[str, int, int]] = []
    detail_rows: list[dict[str, str]] = []
    try:
        with imaplib.IMAP4_SSL(host, port, ssl_context=ctx, timeout=timeout) as m:
            m.login(user, password)
            _typ, folders = m.list()
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
                        detail_rows.append({"SourceEmail": user, "FolderName": name, "MailCount": "", "MailSizeBytes": "", "Status": f"SELECT 失败: {typ}"})
                        continue
                    count = int(data[0]) if data and data[0] else 0
                    size = _fetch_size_sum(m, count) if (count > 0 and collect_size) else 0
                    folder_rows.append((name, count, size))
                    if collect_size:
                        print(f"    - {name}: {count} 封 / {size/1048576:.1f} MB", flush=True)
                    else:
                        print(f"    - {name}: {count} 封（未采集空间占用）", flush=True)
                except Exception as e:
                    detail_rows.append({"SourceEmail": user, "FolderName": name, "MailCount": "", "MailSizeBytes": "", "Status": f"SELECT 异常: {e.__class__.__name__}"})
            m.logout()
    except (imaplib.IMAP4.error, OSError, ssl.SSLError, ValueError) as e:
        # ValueError 同 check：账号/密码含非 ASCII 字符时 imaplib 内部直接抛编码错
        # 密码不参与任何输出；错误详情只含服务端返回文本
        return [], detail_rows, f"{e.__class__.__name__}: {e}"
    return folder_rows, detail_rows, ""


def cmd_probe(args: argparse.Namespace) -> int:
    """连接源 IMAP 服务器，逐账号统计文件夹与邮件数（密码仅在内存，不落盘）。"""
    src = Path(args.csv)
    # probe 是迁移前摸底，只依赖源账号（UserName/Password），目标邮箱列无需填写
    try:
        _header, rows, errors = validate(src, quiet=True, ignore_target_email=True)
    except (OSError, ValueError, csv.Error) as e:
        print(f"[错误] 源 CSV 读取失败（{e.__class__.__name__}: {e}），未执行探测：{src}")
        return 1
    if errors:
        print("[错误] 源 CSV 校验失败，未执行探测：")
        for e in errors:
            print(f"  - {e}")
        return 1

    ctx = ssl.create_default_context()
    details: list[dict[str, str]] = []
    n_total = len(rows)
    attempts = max(0, args.retry) + 1
    failed: list[str] = []
    for idx, r in enumerate(rows, 1):
        user = (r.get("UserName") or "").strip()
        password = (r.get("Password") or "").strip()
        print(f"[{idx}/{n_total}] {user}: 探测中…", flush=True)
        folder_rows: list[tuple[str, int, int]] = []
        account_details: list[dict[str, str]] = []
        err = ""
        for attempt in range(1, attempts + 1):
            folder_rows, account_details, err = _probe_one_account(
                user, password, host=args.host, port=args.port, timeout=args.timeout,
                ctx=ctx, collect_size=not args.no_size)
            if not err:
                break
            if attempt < attempts:
                print(f"[重试] {user}: 第 {attempt}/{attempts} 次失败（{err}），{RETRY_WAIT_SECONDS}s 后重试", flush=True)
                time.sleep(RETRY_WAIT_SECONDS)
        details.extend(account_details)
        if err:
            print(f"[警告] {user}: 连接失败（{err}）")
            details.append({"SourceEmail": user, "FolderName": "", "MailCount": "", "MailSizeBytes": "", "Status": f"失败: {err}"})
            failed.append(user)
            continue
        total = sum(c for _n, c, _s in folder_rows)
        total_size = sum(s for _n, _c, s in folder_rows)
        total_mb = total_size / 1024 / 1024
        if args.no_size:
            print(f"[OK] {user}: 文件夹 {len(folder_rows)} 个，邮件总数 {total}（未采集空间占用）")
        else:
            print(f"[OK] {user}: 文件夹 {len(folder_rows)} 个，邮件总数 {total}，空间占用 {total_mb:.2f} MB")
        for name, count, size in folder_rows:
            details.append({"SourceEmail": user, "FolderName": name, "MailCount": str(count),
                            "MailSizeBytes": (str(size) if not args.no_size else ""), "Status": "OK"})

    out_dir = Path(args.output) / _output_subdir()
    stamp = _now_stamp()
    detail_out = out_dir / f"probe_report_{stamp}.csv"
    if failed:
        print(f"[提示] 失败 {len(failed)}/{n_total} 个: {', '.join(failed)}")
    if args.detail:
        write_csv(detail_out, ["SourceEmail", "FolderName", "MailCount", "MailSizeBytes", "Status"], details)
    else:
        print("[提示] 已按 --no-detail 跳过逐文件夹明细 CSV：源侧逐文件夹底账未落盘，后续核对需重跑 probe")
    # 逐账号汇总表（不含密码），与探测报告同时间戳配对；失败账号拿不到数据，三项留空。
    # 提供 --manifest（password.csv 类源清单）时补 EmailAddress（目标邮箱）列；密码列永不出现在产物中。
    target_by_user: dict[str, str] = {}
    if getattr(args, "manifest", None):
        try:
            _mh, _mrows, _merrs = validate(Path(args.manifest), quiet=True, ignore_target_email=True)
        except OSError as e:
            print(f"[警告] manifest 读取失败（{e}），汇总表将不含 EmailAddress 列")
            _mh, _mrows, _merrs = [], [], ["读取失败"]
        if _merrs or "EmailAddress" not in _mh:
            _why = "；".join(_merrs) or "缺少 EmailAddress 列"
            print(f"[警告] manifest 不可用（{_why}），忽略之，汇总表将不含 EmailAddress 列")
            _mrows = []
        target_by_user = {
            (r.get("UserName") or "").strip().lower(): (r.get("EmailAddress") or "").strip()
            for r in _mrows
        }
    acct: dict[str, dict[str, int]] = {}
    for d in details:
        if d["Status"] != "OK":
            continue
        a = acct.setdefault(d["SourceEmail"], {"count": 0, "size": 0})
        a["count"] += int(d["MailCount"] or 0)
        a["size"] += int(d["MailSizeBytes"] or 0)
    summary_header = ["EmailAddress", "email", "total_count", "total_size", "size_text(MB)"] if target_by_user else ["email", "total_count", "total_size", "size_text(MB)"]
    summary_out = out_dir / f"email_check_success_{stamp}.csv"
    summary_rows = []
    for user in (r.get("UserName", "").strip() for r in rows):
        if not user:
            continue
        has = user in acct
        row = {
            "email": user,
            "total_count": str(acct[user]["count"]) if has else "",
            "total_size": (str(acct[user]["size"]) if (has and not args.no_size) else ""),
            "size_text(MB)": (f"{acct[user]['size'] / 1048576:.2f}" if (has and not args.no_size) else ""),
        }
        if target_by_user:
            row["EmailAddress"] = target_by_user.get(user.lower(), "")
        summary_rows.append(row)
    write_csv(summary_out, summary_header, summary_rows)
    print(f"[OK] 汇总表: {summary_out}")
    if args.detail:
        print(f"[OK] 探测报告: {detail_out}")
    print("[提示] 邮件总数受腾讯'收取范围'影响：若为'最近30天'，看到的只是近30天邮件")
    return 0
def _login_fail_hint(detail: str) -> str:
    """把 LOGIN 失败的服务端报错翻译成排查方向（腾讯合并多种原因为一个报错）。"""
    if "Login fail" in detail:
        return ("可能原因（按腾讯后台排查顺序）："
                "1) 账号状态异常/被禁用；"
                "2) 客户端设置未开启 IMAP/SMTP 服务；"
                "3) 密码错误（若开启'安全登录'，IMAP 须用客户端专用密码，网页密码无效）；"
                "4) 登录频率限制（稍等冷却后重测）")
    if "timeout" in detail.lower() or "refused" in detail.lower() or "unreachable" in detail.lower():
        return "可能原因：网络不通或服务器地址/端口有误（也与账号无关，先查网络）"
    if "ascii" in detail.lower() and "encode" in detail.lower():
        return "可能原因：账号或密码含非 ASCII 字符（如中文/全角），无法经 IMAP LOGIN 发送，请确认是否用错密码"
    return ""


def cmd_check(args: argparse.Namespace) -> int:
    """逐账号只验证源 IMAP 登录可用性（登录即登出），不统计邮件，用于改密后快速验凭据。"""
    ctx = ssl.create_default_context()
    results: list[dict[str, str]] = []
    skipped: list[str] = []
    for csv_path in args.csv:
        src = Path(csv_path)
        try:
            _header, rows, errors = validate(src, quiet=True, ignore_target_email=True)
        except (OSError, ValueError, csv.Error) as e:
            # 文件不存在/编码不符（如 GBK）/格式坏：只跳过该文件，其余照常验证，报告照常生成
            print(f"[错误] {src} 读取失败，跳过该文件（{e.__class__.__name__}: {e}）")
            skipped.append(src.name)
            continue
        if errors:
            # 单个文件校验失败只跳过该文件，其余文件照常验证，报告照常生成
            print(f"[错误] {src} 校验失败，跳过该文件：")
            for e in errors:
                print(f"  - {e}")
            skipped.append(src.name)
            continue
        for idx, r in enumerate(rows, 1):
            user = (r.get("UserName") or "").strip()
            password = (r.get("Password") or "").strip()
            target = (r.get("EmailAddress") or "").strip()
            print(f"[{idx}/{len(rows)}] {src.name}:{user}: 验证中…", flush=True)
            status, detail = "OK", ""
            m = None
            try:
                m = imaplib.IMAP4_SSL(args.host, args.port, ssl_context=ctx, timeout=args.timeout)
                m.login(user, password)
                try:
                    # LOGIN/NOOP 应答 OK 都不代表可用：腾讯对 IMAP 服务未开启的
                    # 账号连 NOOP 都会应答，随后才断会话。以 SELECT INBOX（只读）
                    # 为准——能否打开邮箱正是迁移搬运的必要条件
                    _typ, _data = m.select("INBOX", readonly=True)
                except (imaplib.IMAP4.error, OSError, ssl.SSLError) as e:
                    status = "会话被拒"
                    detail = f"LOGIN 已应答但邮箱不可访问（{e.__class__.__name__}: {e}），疑似 IMAP/SMTP 服务未开启或被限制"
                    print(f"[警告] {user}: {detail}")
                    print(f"[提示] {user}: 请到 邮箱设置→客户端设置 勾选'开启IMAP/SMTP服务'并保存，再重测")
                else:
                    if _typ != "OK":
                        # 注意：现版本 imaplib 对 SELECT 的 NO/BAD 应答不抛异常而是
                        # 返回非 OK typ（实测 3.13），必须显式判定，否则打不开的邮箱被误判可用
                        status = "会话被拒"
                        detail = f"LOGIN 已应答但 SELECT INBOX 被拒（{_typ}），邮箱不可打开，疑似 IMAP/SMTP 服务未开启或被限制"
                        print(f"[警告] {user}: {detail}")
                        print(f"[提示] {user}: 请到 邮箱设置→客户端设置 勾选'开启IMAP/SMTP服务'并保存，再重测")
                    else:
                        try:
                            # 实测结论：服务未开启时腾讯会应答 LOGIN/NOOP/SELECT，
                            # 但在 LOGOUT 收尾时直接掐线（EOF）；服务开启后 LOGOUT 正常。
                            # 因此 LOGIN 后任何阶段断连都指向服务未开启，不作良性处理
                            m.logout()
                        except (imaplib.IMAP4.error, OSError, ssl.SSLError) as e:
                            status = "会话被拒"
                            detail = f"LOGIN 后会话中途断连（{e.__class__.__name__}: {e}），实测指向 IMAP/SMTP 服务未开启"
                            print(f"[警告] {user}: {detail}")
                            print(f"[提示] {user}: 请到 邮箱设置→客户端设置 勾选'开启IMAP/SMTP服务'并保存，再重测")
            except (imaplib.IMAP4.error, OSError, ssl.SSLError, ValueError) as e:
                # ValueError：账号/密码含非 ASCII 字符时 imaplib 内部按 ASCII 编码直接抛
                # UnicodeEncodeError（不含原文，无泄露），捕获后按单账号失败继续
                status = "失败"
                # 密码不参与任何输出；错误详情只含异常类名与服务端返回文本
                detail = f"{e.__class__.__name__}: {e}"
                print(f"[警告] {user}: {detail}")
                hint = _login_fail_hint(detail)
                if hint:
                    print(f"[提示] {user}: {hint}")
            finally:
                # 不用 with/__exit__ 收尾：imaplib 把连接层错误包装成 abort（非 OSError），
                # __exit__ 对已死连接补发的 LOGOUT 会以 abort 逃逸并覆盖上方判定。
                # 按状态显式清理：已 LOGOUT 则无事可做；连接已坏时 shutdown() 不发任何命令
                if m is not None and m.state != "LOGOUT":
                    try:
                        m.shutdown()
                    except Exception:
                        pass
            results.append({"SourceFile": src.name, "EmailAddress": target, "UserName": user, "Status": status, "Detail": detail})

    failed = [r for r in results if r["Status"] != "OK"]
    print(f"\n[OK] 验证完成：通过 {len(results) - len(failed)}/{len(results)} 个")
    if failed:
        print(f"[提示] 失败 {len(failed)} 个: {', '.join(r['UserName'] for r in failed)}")
    if skipped:
        print(f"[提示] 跳过 {len(skipped)} 个校验失败的文件（其中账号未验证）: {', '.join(skipped)}")
    out_dir = Path(args.output) / _output_subdir()
    out = out_dir / f"check_report_{_now_stamp()}.csv"
    write_csv(out, ["SourceFile", "EmailAddress", "UserName", "Status", "Detail"], results)
    print(f"[OK] 可用性报告: {out}")
    if skipped:
        return 1  # 有文件校验失败被跳过；已验证账号的结果仍写入上方报告
    return 0 if not failed else 2


REPORT_EPILOG = """数据来源与时效（本命令只做「取数 → 出报告」，不重复摸底）：
  基线      = 产物目录内最新的 email_check_success_*.csv（即最近一次 probe 摸底结果），
              其文件名与更新时间会写入报告概要（基线文件 / 基线数据时间）。
  目标统计  = user_stats.csv、target_stats.csv（在 EXO 会话内用 scripts/exo_tasks.ps1 导出）。
  需要「最新摸底数据」时：先跑 probe（约 20~30 分钟，只读源端），再执行本命令；否则直接复用现有 CSV。
  --dry-run 只校验输入与时效，不生成报告。
"""


def _latest_file(out_dir: Path, pattern: str) -> Path | None:
    files = sorted(out_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _fmt_mtime(p: Path) -> str:
    return datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y/%m/%d %H:%M")


def cmd_report(args: argparse.Namespace) -> int:
    """生成最终迁移汇总报告：取最近一次摸底 CSV 与最新统计文件，打印时效后转交报告脚本。"""
    out_dir = Path(args.output) / _output_subdir()
    if not out_dir.exists():
        print(f"[错误] 产物目录不存在：{out_dir}")
        return 1
    baseline = Path(args.baseline) if args.baseline else _latest_file(out_dir, "email_check_success_*.csv")
    user_stats = Path(args.user_stats) if args.user_stats else (out_dir / "user_stats.csv")
    target_stats = Path(args.target_stats) if args.target_stats else (out_dir / "target_stats.csv")
    missing = [str(p) for p in (baseline, user_stats, target_stats) if not p or not Path(p).exists()]
    if missing:
        print("[错误] 报告输入缺失，未生成：")
        for m in missing:
            print(f"  - {m}")
        print("  基线由 probe 产出；user_stats/target_stats 在 EXO 会话内用 scripts/exo_tasks.ps1 导出。")
        return 1

    print("[输入] 数据时效（本地时区）：")
    print(f"  - 基线：{baseline.name}（更新于 {_fmt_mtime(baseline)}）")
    print(f"  - 逐用户统计：{user_stats.name}（更新于 {_fmt_mtime(user_stats)}）")
    print(f"  - 目标落库：{target_stats.name}（更新于 {_fmt_mtime(target_stats)}）")
    print("[说明] 直接复用最近一次摸底结果，不重跑 probe；其更新时间会写入报告概要。")

    if user_stats.stat().st_mtime < baseline.stat().st_mtime:
        print("[警告] 统计文件早于基线：统计可能未覆盖最新摸底范围，建议先在 EXO 会话重跑 exo_tasks.ps1 导出再出报告。")
    if args.max_age_min > 0:
        now = datetime.now()
        for label, p in (("基线", baseline), ("逐用户统计", user_stats), ("目标落库", target_stats)):
            age_min = (now - datetime.fromtimestamp(p.stat().st_mtime)).total_seconds() / 60
            if age_min > args.max_age_min:
                print(f"[警告] {label} 已 {age_min:.0f} 分钟未更新（阈值 {args.max_age_min} 分钟）。")

    if args.dry_run:
        print("[完成] --dry-run：仅校验输入与时效，未生成报告。")
        return 0

    out_xlsx = args.out or str(out_dir / f"迁移数据汇总报告_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")
    argv = [
        sys.executable, str(Path(__file__).with_name("gen_migration_report.py")),
        "--user-stats", str(user_stats), "--target-stats", str(target_stats),
        "--baseline", str(baseline), "--out", out_xlsx,
        "--extra-row", f"基线文件={baseline.name}",
        "--extra-row", f"基线数据时间={_fmt_mtime(baseline)}",
    ]
    if args.batch:
        argv += ["--batch", args.batch]
    if args.note:
        argv += ["--note", args.note]
    if args.last_sync:
        argv += ["--last-sync", args.last_sync]
    print("[执行] 生成报告…")
    rc = subprocess.run(argv).returncode
    if rc != 0:
        print(f"[错误] 报告生成失败（exit {rc}）")
        return rc
    print(f"[OK] 报告：{out_xlsx}")
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

    p_probe = sub.add_parser("probe", help="连接源 IMAP，逐账号统计文件夹与邮件数（迁移前容量摸底）", epilog=PROBE_EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    p_probe.add_argument("csv", help="源 CSV 路径")
    p_probe.add_argument("--host", default=_imap_host_default(), help=f"源 IMAP 服务器（默认 {_imap_host_default()}，可环境变量覆盖）")
    p_probe.add_argument("--port", type=int, default=_imap_port_default(), help=f"源 IMAP 端口（默认 {_imap_port_default()} SSL）")
    p_probe.add_argument("--timeout", type=int, default=30, help="单账号连接超时秒数（默认 30）")
    p_probe.add_argument("--output", default=_output_default(), help="产物根目录")
    p_probe.add_argument("--manifest", default=None, help="源清单 CSV（如 password.csv）；提供时汇总表补 EmailAddress（目标邮箱）列，密码不进任何产物")
    p_probe.add_argument("--detail", dest="detail", action="store_true", default=True, help="产出逐文件夹明细 probe_report_*.csv（默认开；不增加联网耗时）")
    p_probe.add_argument("--no-detail", dest="detail", action="store_false", help="不产出逐文件夹明细（省文件，但源侧底账缺失）")
    p_probe.add_argument("--no-size", action="store_true", help="跳过 SIZE 累加只统计邮件数：更快，但无空间占用数据")
    p_probe.add_argument("--retry", type=int, default=0, help="账号连接失败后的重试次数（默认 0，每次间隔 3 秒，增加耗时）")
    p_probe.set_defaults(func=cmd_probe)

    p_report = sub.add_parser("report", help="生成最终迁移汇总报告（取最近一次摸底 CSV 与最新统计文件）", epilog=REPORT_EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    p_report.add_argument("--output", default=_output_default(), help="产物根目录（默认 output，内部自动拼 email-migration/ 子目录）")
    p_report.add_argument("--baseline", default=None, help="指定基线 CSV（默认取产物目录内最新的 email_check_success_*.csv）")
    p_report.add_argument("--user-stats", default=None, help="指定 user_stats.csv（默认取产物目录内该文件名）")
    p_report.add_argument("--target-stats", default=None, help="指定 target_stats.csv（默认取产物目录内该文件名）")
    p_report.add_argument("--out", default=None, help="输出 xlsx 路径（默认 <产物目录>/迁移数据汇总报告_<时间戳>.xlsx）")
    p_report.add_argument("--batch", default="", help="批次名（写入概要）")
    p_report.add_argument("--note", default="", help="概要备注")
    p_report.add_argument("--last-sync", default="", help="最近同步时间（覆盖概要显示值）")
    p_report.add_argument("--max-age-min", type=int, default=0, help="输入文件超 N 分钟未更新则告警（0=不检查）")
    p_report.add_argument("--dry-run", action="store_true", help="只校验输入与数据时效，不生成报告")
    p_report.set_defaults(func=cmd_report)

    p_check = sub.add_parser("check", help="只验证源 IMAP 登录可用性（登录即登出，不统计邮件），支持多个 CSV")
    p_check.add_argument("csv", nargs="+", help="源 CSV 路径（可传多个，如 password-1.csv password-2.csv …）")
    p_check.add_argument("--host", default=_imap_host_default(), help=f"源 IMAP 服务器（默认 {_imap_host_default()}，可环境变量覆盖）")
    p_check.add_argument("--port", type=int, default=_imap_port_default(), help=f"源 IMAP 端口（默认 {_imap_port_default()} SSL）")
    p_check.add_argument("--timeout", type=int, default=30, help="单账号连接超时秒数（默认 30）")
    p_check.add_argument("--output", default=_output_default(), help="产物根目录")
    p_check.set_defaults(func=cmd_check)

    p_backfill = sub.add_parser("backfill", help="把汇总表统计列（total_count 等）回填到源清单 CSV（按 UserName=email 匹配）")
    p_backfill.add_argument("summary", help="汇总表 CSV（email_check_success_*.csv）")
    p_backfill.add_argument("csv", help="待回填的源清单 CSV（就地更新，建议先备份）")
    p_backfill.set_defaults(func=cmd_backfill)

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


class _Tee:
    """把终端输出同步落到日志文件，命令运行中即可 tail 观测实时状态。"""

    def __init__(self, *streams):
        self._streams = streams

    def write(self, s):
        for st in self._streams:
            st.write(s)
        return len(s)

    def flush(self):
        for st in self._streams:
            st.flush()


def _setup_tee_log(args: argparse.Namespace, cmd_name: str) -> None:
    """所有命令输出落盘 output/<产物根>/logs/<命令>_<时间戳>.log。"""
    logs_dir = Path(args.output) / _output_subdir() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{cmd_name}_{_now_stamp()}.log"
    fh = open(log_path, "w", encoding="utf-8")
    sys.stdout = _Tee(sys.stdout, fh)
    sys.stderr = _Tee(sys.stderr, fh)
    print(f"[OK] 日志: {log_path}")


def main(argv: list[str] | None = None) -> int:
    # 终端输出统一 UTF-8，避免 Windows 非 UTF-8 控制台中文乱码（纯显示层，不影响文件写入/解析）。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass
    args = build_parser().parse_args(argv)
    if hasattr(args, "output"):
        _setup_tee_log(args, getattr(args, "command", args.func.__name__.removeprefix("cmd_")))
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
