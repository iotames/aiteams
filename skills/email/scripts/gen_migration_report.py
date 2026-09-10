# -*- coding: utf-8 -*-
"""生成邮箱迁移数据汇总报告（全流程单一份：进行中=进度汇报，完成后=验收结果）。

用法：
  python scripts/gen_migration_report.py \
      --user-stats <Get-MigrationUserStatistics 导出 CSV> \
      --target-stats <Get-MailboxStatistics 导出 CSV> \
      --baseline <源邮箱 probe 基线 CSV> \
      --out <输出 xlsx> [--batch <批次名>] [--note <说明>]
      [--last-sync <最近同步时间，Syncing 期间 PowerShell 取不到时省略>]

Sheet：1.迁移概要  2.迁移数据汇总
完成后追加：3.文件夹对账  4.跳过明细
密码等凭据禁止进入任何输入输出。
"""
import argparse
import csv
import re
from datetime import datetime, timedelta

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

HDR_FILL = PatternFill('solid', fgColor='4472C4')
HDR_FONT = Font(color='FFFFFF', bold=True)
TITLE_FONT = Font(bold=True, size=14)
GREEN = PatternFill('solid', fgColor='C6EFCE')
YELLOW = PatternFill('solid', fgColor='FFEB9C')
RED = PatternFill('solid', fgColor='FFC7CE')
THIN = Side(style='thin', color='D9D9D9')
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
BYTES_RE = re.compile(r'\(([\d,]+)\s+bytes\)')

STATUS_CN = {
    'Synced': '已完成', 'Completed': '已完成', 'CompletedWithErrors': '已完成(有错误)',
    'Syncing': '同步中', 'Failed': '失败', 'Stopped': '已停止',
}
STATUS_FILL = {'已完成': GREEN, '已完成(有错误)': YELLOW, '同步中': YELLOW, '失败': RED, '已停止': RED}
SORT_ORDER = {'同步中': 0, '失败': 1, '已完成(有错误)': 2, '已完成': 3, '已停止': 4}


def disp_len(text):
    """终端显示宽度：CJK 按 2 计。"""
    return sum(2 if ord(ch) > 127 else 1 for ch in str(text))


def parse_bytes(text):
    m = BYTES_RE.search(text or '')
    return int(m.group(1).replace(',', '')) if m else 0


def fmt_mb(nbytes):
    return '%.1f MB' % (nbytes / 1048576)


def fmt_dt(value):
    """EXO 时间为 UTC，转本地；空值原样返回。"""
    if not value:
        return ''
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if dt.tzinfo:
            dt = dt.astimezone()
        return dt.strftime('%Y/%m/%d %H:%M')
    except Exception:
        return str(value)


def set_widths(ws, rows, headers):
    """列宽 = max(表头显示宽, 内容显示宽) + 4，保证不小于字段名长度。"""
    for j, h in enumerate(headers, 1):
        m = disp_len(h)
        for row in rows:
            if j <= len(row):
                m = max(m, disp_len(row[j - 1]))
        ws.column_dimensions[get_column_letter(j)].width = m + 4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user-stats', required=True)
    ap.add_argument('--target-stats', required=True)
    ap.add_argument('--baseline', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--batch', default='')
    ap.add_argument('--note', default='')
    ap.add_argument('--last-sync', default='')
    args = ap.parse_args()

    baseline = {}
    for r in csv.DictReader(open(args.baseline, encoding='utf-8-sig')):
        local = (r.get('email') or '').split('@')[0]
        if local:
            baseline[local] = {
                'count': int(r['total_count'] or 0),
                'mb': float(r['size_text(MB)'] or 0),
            }

    users = []
    for r in csv.DictReader(open(args.user_stats, encoding='utf-8-sig')):
        users.append({
            'email': r['EmailAddress'],
            'user': r['EmailAddress'].split('@')[0],
            'status': STATUS_CN.get(r['Status'], r['Status']),
            'synced': int(r['SyncedItemCount'] or 0),
            'skipped': int(r['SkippedItemCount'] or 0),
            'last': fmt_dt(r.get('LastSyncedDateTime', '')),
        })
    users.sort(key=lambda x: (SORT_ORDER.get(x['status'], 9), x['user']))

    targets_all = {}
    for r in csv.DictReader(open(args.target_stats, encoding='utf-8-sig')):
        targets_all[r['EmailAddress']] = {
            'count': int(r['ItemCount'] or 0),
            'bytes': parse_bytes(r['TotalItemSize']),
        }
    # 只统计批次内账号（导出文件可能混入非批次系统邮箱）
    targets = {k: v for k, v in targets_all.items() if k in {u['email'] for u in users}}

    rows = []
    for u in users:
        b = baseline.get(u['user'], {'count': 0, 'mb': 0.0})
        t = targets.get(u['email'], {'count': 0, 'bytes': 0})
        pct_count = ('%.1f%%' % (t['count'] / b['count'] * 100)) if b['count'] else '—'
        pct_size = ('%.1f%%' % (t['bytes'] / (b['mb'] * 1048576) * 100)) if b['mb'] else '—'
        rows.append([
            u['user'], u['status'],
            b['count'], fmt_mb(b['mb'] * 1048576),
            t['count'], fmt_mb(t['bytes']),
            pct_count, pct_size,
            u['synced'], u['skipped'],
            u['last'] or ('首轮同步进行中' if u['status'] == '同步中' else '—'),
        ])

    total_src_count = sum(r[2] for r in rows)
    total_src_bytes = sum(int(b['mb'] * 1048576) for b in baseline.values() if b)
    total_tgt_count = sum(t['count'] for t in targets.values())
    total_tgt_bytes = sum(t['bytes'] for t in targets.values())
    done = [u for u in users if u['status'] == '已完成']
    doing = [u for u in users if u['status'] == '同步中']
    failed = [u for u in users if u['status'] in ('失败', '已停止')]
    total_skip = sum(u['skipped'] for u in users)

    last_sync_disp = args.last_sync or (
        '；'.join(u['last'] for u in users if u['last']) or '同步进行中（完成后显示）')

    wb = Workbook(); wb.remove(wb.active)

    # ---------- Sheet1 迁移概要 ----------
    ws = wb.create_sheet('迁移概要')
    ws.merge_cells('A1:C1')
    ws['A1'] = '邮箱迁移工作进度报告'
    ws['A1'].font = TITLE_FONT

    r = 3
    summary = [
        ('账号总数', '%d 个' % len(rows)),
        ('已完成', '%d 个' % len(done)),
        ('同步中', '%d 个' % len(doing)),
        ('失败/停止', '%d 个' % len(failed)),
        ('原邮箱邮件总数', '%d 封' % total_src_count),
        ('原邮箱空间合计', fmt_mb(total_src_bytes)),
        ('目标邮箱邮件总数', '%d 封' % total_tgt_count),
        ('目标邮箱空间合计', fmt_mb(total_tgt_bytes)),
        ('完成度（按邮件总数计）', '%.1f%%' % (total_tgt_count / total_src_count * 100) if total_src_count else '—'),
        ('完成度（按空间占用计）', '%.1f%%' % (total_tgt_bytes / total_src_bytes * 100) if total_src_bytes else '—'),
        ('跳过邮件合计', '%d 封' % total_skip),
        ('最近同步时间', last_sync_disp),
        ('更新时间', datetime.now().strftime('%Y/%m/%d %H:%M')),
    ]
    if args.batch:
        summary.insert(0, ('迁移批次', args.batch))
    for k, v in summary:
        ws.cell(r, 1, k).font = Font(bold=True)
        ws.cell(r, 2, v)
        ws.cell(r, 1).border = BORDER
        ws.cell(r, 2).border = BORDER
        r += 1

    r += 1
    note = args.note or ('跳过邮件明细见管理员邮箱错误报告附件；'
                         '部分账号原邮箱基线为收取范围变更前数据，验收前将逐账号重新校准。')
    ws.cell(r, 1, '备注').font = Font(bold=True)
    ws.cell(r, 2, note)
    ws.merge_cells(start_row=r, start_column=2, end_row=r + 2, end_column=3)
    ws.cell(r, 2).alignment = Alignment(wrap_text=True, vertical='top')
    ws.column_dimensions['A'].width = disp_len('完成度（按空间占用计）') + 4
    ws.column_dimensions['B'].width = 34
    ws.column_dimensions['C'].width = 20

    # ---------- Sheet2 迁移数据汇总 ----------
    ws2 = wb.create_sheet('迁移数据汇总')
    headers = ['用户名', '迁移状态', '原邮箱邮件总数', '原邮箱空间占用',
               '目标邮箱邮件总数', '目标邮箱空间占用',
               '完成度（按邮件总数计）', '完成度（按空间占用计）',
               '本批次已同步', '跳过邮件数', '最近同步时间']
    for j, h in enumerate(headers, 1):
        cell = ws2.cell(1, j, h)
        cell.fill, cell.font, cell.border = HDR_FILL, HDR_FONT, BORDER
        cell.alignment = Alignment(horizontal='center', wrap_text=True)
    for i, row in enumerate(rows, 2):
        for j, v in enumerate(row, 1):
            cell = ws2.cell(i, j, v)
            cell.border = BORDER
            if 3 <= j <= 10:
                cell.alignment = Alignment(horizontal='right')
        ws2.cell(i, 2).fill = STATUS_FILL.get(row[1], YELLOW)
    set_widths(ws2, rows, headers)
    ws2.freeze_panes = 'A2'
    ws2.auto_filter.ref = ws2.dimensions

    wb.save(args.out)
    print('saved:', args.out)


if __name__ == '__main__':
    main()
