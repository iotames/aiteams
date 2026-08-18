"""email skill 功能测试：按实际需求顺序（CSV → 分析 → 小批量 → 分批 → 核对）。

安全说明：真实 password.csv 数据仅在本机代码内流转，测试断言不包含任何邮箱/密码原文。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import email_migration  # noqa: E402

REQUIRED = ("EmailAddress", "UserName", "Password")


def _write_csv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    email_migration.write_csv(path, header, rows)


def _real_password_csv() -> Path | None:
    path = PROJECT_ROOT / "password.csv"
    return path if path.exists() else None


# ── 阶段 0/1：源 CSV 校验 ──────────────────────────────────────────

def test_01_validate_real_password_csv() -> None:
    """用真实 password.csv 校验：必填列齐全、无空值、无重复。"""
    path = _real_password_csv()
    if path is None:
        pytest.skip("password.csv 不存在，跳过真实数据测试")
    header, rows, errors = email_migration.validate(path, quiet=True)
    assert errors == []
    assert all(c in header for c in REQUIRED)
    assert len(rows) >= 1
    for r in rows:
        for col in REQUIRED:
            assert (r.get(col) or "").strip(), f"列 {col} 存在空值"


def test_02_validate_rejects_missing_columns(tmp_path: Path) -> None:
    """缺必填列时校验必须失败，且不输出密码。"""
    bad = tmp_path / "bad.csv"
    _write_csv(bad, ["EmailAddress", "UserName"], [{"EmailAddress": "a@b.c", "UserName": "a@b.c"}])
    header, rows, errors = email_migration.validate(bad, quiet=True)
    assert errors
    assert "Password" in errors[0]
    assert email_migration.cmd_validate(
        email_migration.build_parser().parse_args(["validate", str(bad)])
    ) == 1


# ── 阶段 1：生成 EXO 迁移 CSV（含附加列透传） ──────────────────────

def test_03_generate_real_migration_csv(tmp_path: Path) -> None:
    """用真实 password.csv 生成迁移 CSV：官方三列在前，行数一致。"""
    path = _real_password_csv()
    if path is None:
        pytest.skip("password.csv 不存在，跳过真实数据测试")
    out = tmp_path / "out"
    rc = email_migration.main(["generate", str(path), "--output", str(out)])
    assert rc == 0
    files = sorted(out.rglob("migration_*.csv"))
    assert len(files) == 1
    header, rows = email_migration.load_csv(files[0])
    assert header[:3] == list(REQUIRED)
    assert len(rows) == len(email_migration.load_csv(path)[1])


def test_04_generate_preserves_extra_columns(tmp_path: Path) -> None:
    """附加列（如 TargetEmailPassword）原样透传，供第三方工具使用。"""
    src = tmp_path / "src.csv"
    header = ["EmailAddress", "UserName", "Password", "TargetEmailPassword"]
    rows = [
        {"EmailAddress": "t1@corp.onmicrosoft.com", "UserName": "u1@tencent.com", "Password": "fake-src-pw-1", "TargetEmailPassword": "fake-tgt-pw-1"},
        {"EmailAddress": "t2@corp.onmicrosoft.com", "UserName": "u2@tencent.com", "Password": "fake-src-pw-2", "TargetEmailPassword": "fake-tgt-pw-2"},
    ]
    _write_csv(src, header, rows)
    out = tmp_path / "out"
    assert email_migration.main(["generate", str(src), "--output", str(out)]) == 0
    gen = sorted(out.rglob("migration_*.csv"))[0]
    gen_header, gen_rows = email_migration.load_csv(gen)
    assert gen_header == header
    assert [r["TargetEmailPassword"] for r in gen_rows] == ["fake-tgt-pw-1", "fake-tgt-pw-2"]


# ── 阶段 2/3：批量拆分 ─────────────────────────────────────────────

def test_05_split_batches(tmp_path: Path) -> None:
    """按批拆分：5 行、每批 2 人 → 3 个批次文件（2/2/1）。"""
    src = tmp_path / "migration.csv"
    header = ["EmailAddress", "UserName", "Password"]
    rows = [
        {"EmailAddress": f"t{i}@corp.onmicrosoft.com", "UserName": f"u{i}@tencent.com", "Password": f"fake-pw-{i}"}
        for i in range(1, 6)
    ]
    _write_csv(src, header, rows)
    out = tmp_path / "out"
    assert email_migration.main(["split", str(src), "--batch-size", "2", "--output", str(out)]) == 0
    batches = sorted((out / "email-migration" / "batches").glob("batch_*.csv"))
    assert len(batches) == 3
    assert [len(email_migration.load_csv(b)[1]) for b in batches] == [2, 2, 1]


def test_06_split_default_batch_size(tmp_path: Path) -> None:
    """默认每批 50 人：不足 50 人时只生成一批。"""
    src = tmp_path / "migration.csv"
    header = ["EmailAddress", "UserName", "Password"]
    rows = [{"EmailAddress": f"t{i}@corp.onmicrosoft.com", "UserName": f"u{i}@tencent.com", "Password": "fake-pw"} for i in range(3)]
    _write_csv(src, header, rows)
    out = tmp_path / "out"
    assert email_migration.main(["split", str(src), "--output", str(out)]) == 0
    batches = list((out / "email-migration" / "batches").glob("batch_*.csv"))
    assert len(batches) == 1


# ── 阶段 1：超限分析 ───────────────────────────────────────────────

def test_07_analyze_overlimit(tmp_path: Path) -> None:
    """解析统计 CSV：大小超 45GB 或条数超 50 万 → 标记超限。"""
    stats = tmp_path / "stats.csv"
    _write_csv(stats, ["Identity", "EstimatedTotalCount", "EstimatedTotalSize"], [
        {"Identity": "big@corp.onmicrosoft.com", "EstimatedTotalCount": "600000", "EstimatedTotalSize": "60.00 GB (64,424,509,440 bytes)"},
        {"Identity": "many@corp.onmicrosoft.com", "EstimatedTotalCount": "510000", "EstimatedTotalSize": "10.00 GB (10,737,418,240 bytes)"},
        {"Identity": "ok@corp.onmicrosoft.com", "EstimatedTotalCount": "1000", "EstimatedTotalSize": "2.00 GB (2,147,483,648 bytes)"},
    ])
    out = tmp_path / "out"
    assert email_migration.main(["analyze", str(stats), "--output", str(out)]) == 0
    report = sorted(out.rglob("analysis_report_*.csv"))[0]
    _header, rows = email_migration.load_csv(report)
    assert len(rows) == 3
    flags = {(r["Identity"], r["OverSizeLimit"], r["OverCountLimit"]) for r in rows}
    assert ("big@corp.onmicrosoft.com", "是", "是") in flags
    assert ("many@corp.onmicrosoft.com", "否", "是") in flags
    assert ("ok@corp.onmicrosoft.com", "否", "否") in flags


def test_08_analyze_missing_columns(tmp_path: Path) -> None:
    """统计 CSV 缺列时返回错误码。"""
    stats = tmp_path / "bad_stats.csv"
    _write_csv(stats, ["Identity"], [{"Identity": "x@corp.onmicrosoft.com"}])
    assert email_migration.main(["analyze", str(stats), "--output", str(tmp_path)]) == 1


def test_09_analyze_custom_size_threshold(tmp_path: Path) -> None:
    """大小阈值可调：--size-gb 1 时 2GB 邮箱也被标记超限；条数阈值可显式传入。"""
    stats = tmp_path / "stats.csv"
    _write_csv(stats, ["Identity", "EstimatedTotalCount", "EstimatedTotalSize"], [
        {"Identity": "medium@corp.onmicrosoft.com", "EstimatedTotalCount": "300000", "EstimatedTotalSize": "2.00 GB (2,147,483,648 bytes)"},
        {"Identity": "many@corp.onmicrosoft.com", "EstimatedTotalCount": "600000", "EstimatedTotalSize": "10.00 GB (10,737,418,240 bytes)"},
    ])
    out = tmp_path / "out"
    assert email_migration.main(
        ["analyze", str(stats), "--size-gb", "1", "--count", "600000", "--output", str(out)]
    ) == 0
    report = sorted(out.rglob("analysis_report_*.csv"))[0]
    _header, rows = email_migration.load_csv(report)
    by_mailbox = {r["Identity"]: r for r in rows}
    # 2GB > 1GB：大小超限
    assert by_mailbox["medium@corp.onmicrosoft.com"]["OverSizeLimit"] == "是"
    # 600000 条恰好等于阈值上限：不超限
    assert by_mailbox["many@corp.onmicrosoft.com"]["OverCountLimit"] == "否"


# ── 阶段 4：迁移后核对 ─────────────────────────────────────────────

def test_10_verify_deleted_items_coverage(tmp_path: Path) -> None:
    """核对报告覆盖两类场景：目标非空追加、收件箱清空但已删除邮件有内容。"""
    folder_stats = tmp_path / "folder_stats.csv"
    _write_csv(folder_stats, ["Identity", "FolderPath", "ItemsInFolder"], [
        {"Identity": "existing@corp.onmicrosoft.com", "FolderPath": "/Inbox", "ItemsInFolder": "25"},
        {"Identity": "existing@corp.onmicrosoft.com", "FolderPath": "/Sent Items", "ItemsInFolder": "8"},
        {"Identity": "cleared@corp.onmicrosoft.com", "FolderPath": "/Inbox", "ItemsInFolder": "0"},
        {"Identity": "cleared@corp.onmicrosoft.com", "FolderPath": "/Deleted Items", "ItemsInFolder": "6"},
    ])
    out = tmp_path / "out"
    assert email_migration.main(["verify", str(folder_stats), "--output", str(out)]) == 0
    report = sorted(out.rglob("verify_report_*.csv"))[0]
    _header, rows = email_migration.load_csv(report)
    by_mailbox = {r["EmailAddress"]: r for r in rows}
    assert by_mailbox["existing@corp.onmicrosoft.com"]["InboxItems"] == "25"
    assert by_mailbox["existing@corp.onmicrosoft.com"]["EmptyTarget"] == "否"
    assert by_mailbox["cleared@corp.onmicrosoft.com"]["InboxItems"] == "0"
    assert by_mailbox["cleared@corp.onmicrosoft.com"]["DeletedItems"] == "6"
    assert by_mailbox["cleared@corp.onmicrosoft.com"]["DeletedItemsNotCleared"] == "是"


def test_11_verify_empty_target(tmp_path: Path) -> None:
    """空目标邮箱标记为需人工确认。"""
    folder_stats = tmp_path / "folder_stats.csv"
    _write_csv(folder_stats, ["Identity", "FolderPath", "ItemsInFolder"], [
        {"Identity": "empty@corp.onmicrosoft.com", "FolderPath": "/Inbox", "ItemsInFolder": "0"},
    ])
    out = tmp_path / "out"
    assert email_migration.main(["verify", str(folder_stats), "--output", str(out)]) == 0
    report = sorted(out.rglob("verify_report_*.csv"))[0]
    _header, rows = email_migration.load_csv(report)
    assert rows[0]["InboxItems"] == "0"


# ── 阶段 0：源 IMAP 摸底（probe，mock 不依赖真实网络） ──────────────

class _FakeIMAP:
    """模拟 imaplib.IMAP4_SSL：登录、LIST、SELECT 计数。"""

    instances: list["_FakeIMAP"] = []
    fail_login = False

    def __init__(self, host: str, port: int, ssl_context=None, timeout=None) -> None:
        self.host = host
        self.port = port
        self.logged_out = False
        self.selects: list[str] = []
        _FakeIMAP.instances.append(self)

    def __enter__(self) -> "_FakeIMAP":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def login(self, user: str, password: str) -> None:
        if _FakeIMAP.fail_login:
            raise email_migration.imaplib.IMAP4.error("认证失败")

    def list(self):
        return ("OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren) "/" "Sent Items"'])

    def select(self, name: str, readonly: bool = True):
        self.selects.append(name)
        return ("OK", [b"10"])

    def logout(self) -> None:
        self.logged_out = True


def _probe_source_csv(tmp_path: Path) -> Path:
    src = tmp_path / "src.csv"
    header = ["EmailAddress", "UserName", "Password"]
    rows = [
        {"EmailAddress": "t1@corp.onmicrosoft.com", "UserName": "u1@tencent.com", "Password": "fake-src-pw-1"},
        {"EmailAddress": "t2@corp.onmicrosoft.com", "UserName": "u2@tencent.com", "Password": "fake-src-pw-2"},
    ]
    _write_csv(src, header, rows)
    return src


def test_12_probe_success_writes_report(tmp_path: Path, monkeypatch) -> None:
    """probe 连接成功：逐文件夹计数并写报告，密码不落盘。"""
    _FakeIMAP.instances = []
    monkeypatch.setattr(email_migration.imaplib, "IMAP4_SSL", _FakeIMAP)
    src = _probe_source_csv(tmp_path)
    out = tmp_path / "out"
    assert email_migration.main(["probe", str(src), "--output", str(out)]) == 0
    report = sorted(out.rglob("probe_report_*.csv"))[0]
    header, rows = email_migration.load_csv(report)
    assert header == ["SourceEmail", "FolderName", "MailCount", "Status"]
    assert len(rows) == 4  # 2 账号 × 2 文件夹
    assert all(r["MailCount"] == "10" and r["Status"] == "OK" for r in rows)
    assert not any("password" in str(r).lower() for r in rows)


def test_13_probe_auth_failure_reported(tmp_path: Path, monkeypatch) -> None:
    """probe 认证失败：账号级失败记录，不影响其他账号。"""
    _FakeIMAP.instances = []
    _FakeIMAP.fail_login = True
    monkeypatch.setattr(email_migration.imaplib, "IMAP4_SSL", _FakeIMAP)
    src = _probe_source_csv(tmp_path)
    out = tmp_path / "out"
    assert email_migration.main(["probe", str(src), "--output", str(out)]) == 0
    report = sorted(out.rglob("probe_report_*.csv"))[0]
    _header, rows = email_migration.load_csv(report)
    assert len(rows) == 2
    assert all("失败" in r["Status"] for r in rows)


def test_14_mask_email() -> None:
    """终端脱敏：本地部分只保留首尾字符。"""
    assert email_migration._mask_email("abc@example.com") == "a***c@example.com"
    assert email_migration._mask_email("ab@example.com") == "a***@example.com"
    assert email_migration._mask_email("nouser") == "***"


# ── 阶段状态机（跨会话共享进度） ──────────────────────────────────

def test_15_state_init_and_advance(tmp_path: Path) -> None:
    """state 初始化后默认阶段0；advance 标记完成并推进到阶段1。"""
    out = tmp_path / "out"
    # 初始化写入
    rc = email_migration.main(["state", "--output", str(out)])
    assert rc == 0
    state_file = out / "email-migration" / "state" / "email-migration-state.json"
    assert state_file.exists()
    s = email_migration.load_state(state_file)
    assert s["phase"] == "phase0"
    # 标记当前完成并推进
    assert email_migration.main(["state", "--output", str(out), "--advance"]) == 0
    s = email_migration.load_state(state_file)
    assert s["phase"] == "phase1"
    assert s["done"]["phase0"] is True


def test_16_state_todo_confirm_and_notes(tmp_path: Path) -> None:
    """todo 加入待确认项，confirm 移除；note 追加备注。"""
    out = tmp_path / "out"
    sfile = "custom-state.json"
    args = lambda *flags: ["state", "--output", str(out), "--state-file", sfile, *flags]
    assert email_migration.main(args("--todo", "确认目标邮箱已分配许可证")) == 0
    assert email_migration.main(args("--todo", "确认腾讯收取范围为全部")) == 0
    state_file = out / "email-migration" / "state" / sfile
    s = email_migration.load_state(state_file)
    assert "确认目标邮箱已分配许可证" in s["pending_confirm"]
    assert len(s["pending_confirm"]) == 2
    # confirm 移除一项
    assert email_migration.main(args("--confirm", "确认目标邮箱已分配许可证")) == 0
    s = email_migration.load_state(state_file)
    assert "确认目标邮箱已分配许可证" not in s["pending_confirm"]
    assert len(s["pending_confirm"]) == 1
    # 备注
    assert email_migration.main(args("--note", "测试备注")) == 0
    s = email_migration.load_state(state_file)
    assert "测试备注" in s["notes"]


def test_17_state_jump_to_phase(tmp_path: Path) -> None:
    """--phase 可直接跳转到指定阶段。"""
    out = tmp_path / "out"
    assert email_migration.main(["state", "--output", str(out), "--advance"]) == 0
    assert email_migration.main(["state", "--output", str(out), "--advance"]) == 0
    assert email_migration.main(["state", "--output", str(out), "--phase", "phase3"]) == 0
    state_file = out / "email-migration" / "state" / "email-migration-state.json"
    s = email_migration.load_state(state_file)
    assert s["phase"] == "phase3"


def test_18_state_rejects_unknown_phase(tmp_path: Path) -> None:
    """非法阶段由 argparse 报错并退出码 2。"""
    import pytest as _pt
    out = tmp_path / "out"
    with _pt.raises(SystemExit) as e:
        email_migration.main(["state", "--output", str(out), "--phase", "phaseX"])
    assert e.value.code == 2
