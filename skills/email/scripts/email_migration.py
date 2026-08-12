#!/usr/bin/env python3
"""大规模企业邮箱迁移辅助脚本（腾讯企业邮 IMAP → Exchange Online）。

子命令：
  validate  校验源 CSV（官方三列必填，附加列原样透传）
  generate  生成 EXO 迁移 CSV（Password=源密码，附加列如 TargetEmailPassword 透传）
  split     按批拆分迁移 CSV（默认 50 人/批，供小批量验证与分批迁移）
  analyze   解析分析批处理统计，筛超限名单（默认 >45GB 或 >50 万条）
  verify    迁移后核对报告（文件夹统计，含已删除邮件覆盖情况）

安全约束：
  - 密码仅在本机代码内流转，任何输出/日志不得出现密码原文
  - 含密码的产物默认写入 <cwd>/output/email-migration/（已被 .gitignore 忽略）
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

# 官方 IMAP 迁移 CSV 必填列
REQUIRED_COLUMNS = ("EmailAddress", "UserName", "Password")

# 官方迁移硬限制：单邮箱最多 50 万项、单封最大 35MB；超限判断阈值留 5GB 余量
DEFAULT_SIZE_THRESHOLD_GB = 45
DEFAULT_COUNT_THRESHOLD = 500_000
DEFAULT_BATCH_SIZE = 50


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
    out_dir = Path(args.output) / "email-migration"
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

    out_dir = Path(args.output) / "email-migration" / "batches"
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

    out_dir = Path(args.output) / "email-migration"
    out = out_dir / f"analysis_report_{_now_stamp()}.csv"
    write_csv(out, list(report[0].keys()) if report else [identity_col, "EstimatedTotalCount", "EstimatedTotalSizeBytes", "OverSizeLimit", "OverCountLimit"], report)
    print(f"[OK] 分析报告: {out}")
    print(f"[OK] 统计邮箱数: {len(report)}，超 {args.size_gb}GB: {over_size}，超 {args.count} 条: {over_count}")
    if args.show_identities:
        for r in report:
            if r["OverSizeLimit"] == "是" or r["OverCountLimit"] == "是":
                print(f"  - {r[identity_col]} (条数 {r['EstimatedTotalCount']}, 大小 {r['EstimatedTotalSizeBytes']} bytes)")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """核对文件夹统计 CSV（列: Identity/EmailAddress, FolderPath, ItemsInFolder），输出逐邮箱报告。"""
    header, rows = load_csv(Path(args.csv))
    identity_col = next((c for c in ("Identity", "EmailAddress") if c in header), None)
    folder_col = next((c for c in ("FolderPath", "Name") if c in header), None)
    items_col = next((c for c in ("ItemsInFolder", "ItemsInFolderAndSubfolders", "Items") if c in header), None)
    if not identity_col or not folder_col or not items_col:
        print("[错误] 文件夹统计 CSV 缺少必需列（Identity/EmailAddress、FolderPath、ItemsInFolder）")
        return 1

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
        fl = folder.lower()
        if "inbox" in fl:
            mb["inbox"] += items
        elif "deleted" in fl or "trash" in fl or "已删除" in fl:
            mb["deleted"] += items
        else:
            mb["other"] += items

    report_header = ["EmailAddress", "FolderCount", "InboxItems", "DeletedItems", "OtherItems", "EmptyTarget", "DeletedItemsNotCleared"]
    report: list[dict[str, str]] = []
    for ident, mb in sorted(per_mailbox.items()):
        empty = mb["folders"] == 0
        deleted_not_cleared = mb["deleted"] > 0
        report.append({
            "EmailAddress": ident,
            "FolderCount": str(mb["folders"]),
            "InboxItems": str(mb["inbox"]),
            "DeletedItems": str(mb["deleted"]),
            "OtherItems": str(mb["other"]),
            "EmptyTarget": "是" if empty else "否",
            "DeletedItemsNotCleared": "是" if deleted_not_cleared else "否",
        })

    out_dir = Path(args.output) / "email-migration"
    out = out_dir / f"verify_report_{_now_stamp()}.csv"
    write_csv(out, report_header, report)
    print(f"[OK] 核对报告: {out}")
    print(f"[OK] 覆盖邮箱数: {len(report)}")
    empty_n = sum(1 for r in report if r["EmptyTarget"] == "是")
    deleted_n = sum(1 for r in report if r["DeletedItemsNotCleared"] == "是")
    if empty_n:
        print(f"[警告] 空目标邮箱: {empty_n} 个（需人工确认是否迁移失败）")
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


def _parse_list_folder(line: bytes) -> str | None:
    """解析 IMAP LIST 行，返回文件夹名（imaplib UTF-7 解码）。"""
    text = line.decode("utf-8", "replace").strip()
    match = re.search(r'"([^"]*)"\s*$', text)
    if match:
        raw = match.group(1)
        try:
            return imaplib.UTF7.decode(raw)
        except Exception:
            return raw
    return None


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
                folder_rows: list[tuple[str, int]] = []
                for line in folders:
                    name = _parse_list_folder(line)
                    if not name:
                        continue
                    try:
                        typ, data = m.select(name, readonly=True)
                        if typ != "OK":
                            details.append({"SourceEmail": user, "FolderName": name, "MailCount": "", "Status": f"SELECT 失败: {typ}"})
                            continue
                        count = int(data[0]) if data and data[0] else 0
                        folder_rows.append((name, count))
                    except Exception as e:
                        details.append({"SourceEmail": user, "FolderName": name, "MailCount": "", "Status": f"SELECT 异常: {e.__class__.__name__}"})
                m.logout()
            total = sum(c for _n, c in folder_rows)
            print(f"[OK] {_mask_email(user)}: 文件夹 {len(folder_rows)} 个，邮件总数 {total}")
            for name, count in folder_rows:
                details.append({"SourceEmail": user, "FolderName": name, "MailCount": str(count), "Status": "OK"})
        except (imaplib.IMAP4.error, OSError, ssl.SSLError) as e:
            print(f"[警告] {_mask_email(user)}: 连接失败（{e.__class__.__name__}）")
            details.append({"SourceEmail": user, "FolderName": "", "MailCount": "", "Status": f"失败: {e.__class__.__name__}"})

    out_dir = Path(args.output) / "email-migration"
    out = out_dir / f"probe_report_{_now_stamp()}.csv"
    write_csv(out, ["SourceEmail", "FolderName", "MailCount", "Status"], details)
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
    p_generate.add_argument("--output", default="output", help="产物根目录（默认 <cwd>/output）")
    p_generate.add_argument("--dry-run", action="store_true", help="只校验不写文件")
    p_generate.set_defaults(func=cmd_generate)

    p_split = sub.add_parser("split", help="按批拆分迁移 CSV")
    p_split.add_argument("csv", help="迁移 CSV 路径")
    p_split.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help=f"每批人数（默认 {DEFAULT_BATCH_SIZE}）")
    p_split.add_argument("--output", default="output", help="产物根目录（默认 <cwd>/output）")
    p_split.set_defaults(func=cmd_split)

    p_analyze = sub.add_parser("analyze", help="解析迁移分析统计，筛超限名单")
    p_analyze.add_argument("csv", help="Get-MigrationUserStatistics 导出的统计 CSV")
    p_analyze.add_argument("--size-gb", type=float, default=DEFAULT_SIZE_THRESHOLD_GB, help=f"大小阈值 GB（默认 {DEFAULT_SIZE_THRESHOLD_GB}）")
    p_analyze.add_argument("--count", type=int, default=DEFAULT_COUNT_THRESHOLD, help=f"条数阈值（默认 {DEFAULT_COUNT_THRESHOLD}，可调）")
    p_analyze.add_argument("--output", default="output", help="产物根目录（默认 <cwd>/output）")
    p_analyze.add_argument("--show-identities", action="store_true", help="在终端列出超限邮箱（默认只写入报告文件）")
    p_analyze.set_defaults(func=cmd_analyze)

    p_verify = sub.add_parser("verify", help="生成迁移后文件夹核对报告")
    p_verify.add_argument("csv", help="Get-MailboxFolderStatistics 导出的文件夹统计 CSV")
    p_verify.add_argument("--output", default="output", help="产物根目录（默认 <cwd>/output）")
    p_verify.set_defaults(func=cmd_verify)

    p_probe = sub.add_parser("probe", help="连接源 IMAP，逐账号统计文件夹与邮件数（迁移前容量摸底）")
    p_probe.add_argument("csv", help="源 CSV 路径")
    p_probe.add_argument("--host", default="imap.exmail.qq.com", help="源 IMAP 服务器（默认腾讯企业邮）")
    p_probe.add_argument("--port", type=int, default=993, help="源 IMAP 端口（默认 993 SSL）")
    p_probe.add_argument("--timeout", type=int, default=30, help="单账号连接超时秒数（默认 30）")
    p_probe.add_argument("--output", default="output", help="产物根目录（默认 <cwd>/output）")
    p_probe.set_defaults(func=cmd_probe)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
