"""exo_tasks.ps1 口径与安全守卫测试。

固化两条硬规则：
1. 目标侧邮件数只能取「邮件类文件夹的可见邮件数」（VisibleItemsInFolder），
   不得退回整邮箱项数（Get-MailboxStatistics.ItemCount）或含隐藏项的 ItemsInFolder；
2. 该脚本只读+导出，永不连接/断开 EXO 会话、不删除任何对象。

背景（实测踩坑）：
- powerich 3 封邮件被 ItemCount 算成 8、被 ItemsInFolder 算成 11（收件箱有 8 个系统隐藏项）；
- V3 cmdlet 的自建文件夹 FolderType 是 'User Created'（带空格），不去空白比对会整片漏掉，emma 少算 9,903 封；
- /日历/中国 节假日 类型也是 UserCreated，不按一级路径排除会多算 174 项。
"""

from __future__ import annotations

import re
from pathlib import Path

PS1 = Path(__file__).resolve().parents[1] / "scripts" / "exo_tasks.ps1"


def _text() -> str:
    return PS1.read_text(encoding="utf-8-sig")


def _code_lines() -> list[str]:
    """去掉块注释、行注释、字符串字面量后的代码行（用于禁止命令检查）。"""
    body = re.sub(r"<#.*?#>", "", _text(), flags=re.S)
    out: list[str] = []
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        s = re.sub(r"\s#.*$", "", s)
        s = re.sub(r"'[^']*'", "''", s)
        s = re.sub(r'"[^"]*"', '""', s)
        out.append(s)
    return out


def test_utf8_bom():
    """PS 5.1 无 BOM 会把中文注释读成乱码并报语法错。"""
    assert PS1.read_bytes().startswith(b"\xef\xbb\xbf")


def test_target_count_uses_visible_items():
    t = _text()
    assert "VisibleItemsInFolder" in t
    assert not any("Get-MailboxStatistics" in line for line in _code_lines())
    assert not any("Measure-Object -Property ItemsInFolder" in line for line in _code_lines())


def test_user_created_folder_type_whitespace_normalized():
    """V3 返回 'User Created'，经典 cmdlet 返回 'UserCreated'，比对前必须去空白。"""
    assert r"-replace '\s+', ''" in _text()


def test_non_mail_roots_excluded():
    t = _text()
    assert "$nonMailRoots" in t
    for name in ("日历", "Calendar", "联系人", "Notes"):
        assert name in t


def test_folder_size_parsed_from_string():
    """FolderSize 是字符串（无 ToBytes() 方法），只能正则取字节。"""
    t = _text()
    assert ".ToBytes()" not in t
    assert r"([\d,]+)\s+bytes\)" in t


def test_never_connect_or_disconnect_session():
    """会话生命周期归用户：脚本不得连接/断开 EXO。"""
    banned = ("Connect-ExchangeOnline", "Disconnect-ExchangeOnline")
    for line in _code_lines():
        for cmd in banned:
            assert not re.search(rf"(^|;)\s*{re.escape(cmd)}", line), line


def test_read_only_no_write_cmdlets():
    """脚本只读+导出：不得出现写操作动词开头的 EXO 命令。"""
    pattern = re.compile(r"^\s*(Remove|Set|New|Start|Stop|Move|Add|Enable|Disable)-[A-Za-z]+")
    for line in _code_lines():
        assert not pattern.match(line), line
