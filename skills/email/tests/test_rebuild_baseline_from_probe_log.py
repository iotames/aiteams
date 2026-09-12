"""probe 日志 → 基线 CSV 重建脚本测试（纯本地，不联网、不读真实名单）。"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import rebuild_baseline_from_probe_log as rb  # noqa: E402

LOG_TEXT = "\n".join([
    "[OK] 日志: /tmp/probe_20260911_123424.log",
    "[1/3] a@src.example.com: 探测中…",
    "    - INBOX: 10 封 / 1.0 MB",
    "    - &UXZO1mWHTvZZOQ-: 5 封 / 0.5 MB",
    "[OK] a@src.example.com: 文件夹 2 个，邮件总数 15，空间占用 1.53 MB",
    "[2/3] b@src.example.com: 探测中…",
    "    - INBOX: 3 封 / 0.2 MB",
    "[警告] b@src.example.com: 连接失败（SSLError: boom）",
    "[3/3] c@src.example.com: 探测中…",
    "    - INBOX: 7 封 / 0.7 MB",
    "[OK] 探测报告: /tmp/probe_report_20260911_130044.csv",
])


def _write_log(tmp_path: Path) -> Path:
    p = tmp_path / "probe_20260911_123424.log"
    p.write_text(LOG_TEXT, encoding="utf-8")
    return p


def test_parse_log_summary_overrides_folder_sum(tmp_path):
    details, acct, order, failed, stamp = rb.parse_log(_write_log(tmp_path))
    assert stamp == "20260911_130044"
    assert acct["a@src.example.com"]["count"] == 15
    assert acct["a@src.example.com"]["size"] == round(1.53 * 1048576)
    assert acct["c@src.example.com"]["count"] == 7
    assert failed == ["b@src.example.com"]
    assert order["a@src.example.com"] == 1
    assert len(details) == 5
    assert any(d["Status"].startswith("失败") for d in details)


def test_folder_names_kept_raw_utf7(tmp_path):
    details, *_ = rb.parse_log(_write_log(tmp_path))
    names = [d["FolderName"] for d in details if d["SourceEmail"] == "a@src.example.com"]
    assert names == ["INBOX", "&UXZO1mWHTvZZOQ-"]
    counts = [d["MailCount"] for d in details if d["SourceEmail"] == "a@src.example.com"]
    assert counts == ["10", "5"]


def test_main_writes_baseline_csvs(tmp_path, monkeypatch):
    log = _write_log(tmp_path)
    out = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["rebuild_baseline_from_probe_log.py", str(log), "--output", str(out)])
    assert rb.main() == 0
    summary = out / "email-migration" / "email_check_success_20260911_130044.csv"
    detail = out / "email-migration" / "probe_report_20260911_130044.csv"
    assert summary.exists() and detail.exists()
    assert summary.read_bytes().startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(summary.open(encoding="utf-8-sig")))
    by_email = {r["email"]: r for r in rows}
    assert set(by_email) == {"a@src.example.com", "b@src.example.com", "c@src.example.com"}
    assert by_email["a@src.example.com"]["total_count"] == "15"
    assert by_email["b@src.example.com"]["total_count"] == ""
    assert by_email["c@src.example.com"]["total_count"] == "7"
    assert list(csv.DictReader(detail.open(encoding="utf-8-sig")))[0]["SourceEmail"] == "a@src.example.com"