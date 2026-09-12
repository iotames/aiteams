# -*- coding: utf-8 -*-
"""从 probe 日志重建基线 CSV（probe 产物 CSV 被清理后的兜底，口径同 probe 子命令）。

用法：
  python rebuild_baseline_from_probe_log.py <probe 日志> [--output <产物根目录>]

产出：
  email_check_success_<原时间戳>.csv  账号级汇总：email,total_count,total_size,size_text(MB)
  probe_report_<原时间戳>.csv         逐文件夹明细：SourceEmail,FolderName,MailCount,MailSizeBytes,Status

时间戳沿用日志内“探测报告:”标注的原时间戳，缺省取当前时间。密码不进任何产物。
"""
import argparse
import csv
import re
from datetime import datetime
from pathlib import Path

ACCT_RE = re.compile(r"^\[(\d+)/(\d+)\] (\S+): 探测中")
FOLDER_RE = re.compile(r"^ {4}- (.+): (\d+) 封 / ([\d.]+) MB$")
SUMMARY_RE = re.compile(r"^\[OK\] (\S+): 文件夹 \d+ 个，邮件总数 (\d+)，空间占用 ([\d.]+) MB")
FAIL_RE = re.compile(r"^\[警告\] (\S+): 连接失败(.*)$")
REPORT_RE = re.compile(r"probe_report_(\d{8}_\d{6})\.csv")


def write_csv(path: Path, header, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def parse_log(path: Path):
    details, acct, order, failed, stamp, cur = [], {}, {}, [], None, None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = REPORT_RE.search(line)
        if m:
            stamp = m.group(1)
        m = ACCT_RE.match(line)
        if m:
            cur = m.group(3)
            order.setdefault(cur, int(m.group(1)))
            acct.setdefault(cur, {"count": 0, "size": 0})
            continue
        m = FOLDER_RE.match(line)
        if m and cur:
            name, count, mb = m.group(1), int(m.group(2)), float(m.group(3))
            details.append({"SourceEmail": cur, "FolderName": name, "MailCount": str(count),
                            "MailSizeBytes": str(round(mb * 1048576)), "Status": "OK"})
            acct[cur]["count"] += count
            acct[cur]["size"] += round(mb * 1048576)
            continue
        m = SUMMARY_RE.match(line)
        if m:
            user, total, mb = m.group(1), int(m.group(2)), float(m.group(3))
            order.setdefault(user, len(order) + 1)
            acct[user] = {"count": total, "size": round(mb * 1048576)}
            cur = None
            continue
        m = FAIL_RE.match(line)
        if m:
            failed.append(m.group(1))
            acct.pop(m.group(1), None)  # 账号级连接失败：已采到的残缺计数不可当基线，一律置空
            order.setdefault(m.group(1), len(order) + 1)
            details.append({"SourceEmail": m.group(1), "FolderName": "", "MailCount": "",
                            "MailSizeBytes": "", "Status": "失败" + m.group(2)})
            cur = None
    return details, acct, order, failed, stamp


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--output", default="output", help="产物根目录（其下 email-migration/ 子目录）")
    args = ap.parse_args()

    log_path = Path(args.log)
    details, acct, order, failed, stamp = parse_log(log_path)
    if not acct:
        print("[错误] 日志中未解析到任何账号基线，请确认是 probe 日志")
        return 1
    stamp = stamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.output) / "email-migration"

    summary = []
    for user in sorted(acct, key=lambda u: order.get(u, 999)):
        a = acct[user]
        summary.append({"email": user, "total_count": str(a["count"]),
                        "total_size": str(a["size"]), "size_text(MB)": f"{a['size'] / 1048576:.2f}"})
    for user in failed:
        if user not in acct:
            summary.append({"email": user, "total_count": "", "total_size": "", "size_text(MB)": ""})
    sum_path = out_dir / f"email_check_success_{stamp}.csv"
    write_csv(sum_path, ["email", "total_count", "total_size", "size_text(MB)"], summary)

    det_path = out_dir / f"probe_report_{stamp}.csv"
    write_csv(det_path, ["SourceEmail", "FolderName", "MailCount", "MailSizeBytes", "Status"], details)

    total = sum(a["count"] for a in acct.values())
    size = sum(a["size"] for a in acct.values())
    print(f"[OK] 账号数 {len(acct)}（失败 {len(failed)}），邮件总数 {total}，空间占用 {size / 1048576:.2f} MB")
    if failed:
        print("[提示] 失败账号: " + ", ".join(failed))
    print(f"[OK] 汇总表: {sum_path}")
    print(f"[OK] 探测报告: {det_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
