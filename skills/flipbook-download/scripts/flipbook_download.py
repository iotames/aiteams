#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""flipbook-download：通用网页翻页画册（flipbook）完整下载。

流程：启动浏览器（带代理）→ 打开画册 URL → 平台识别 → 定位源文件
      → 下载（curl 断点续传）→ 完整性校验 → 输出中文报告

用法示例：
  python flipbook_download.py "https://joma-sport.hflip.co/b59e072427.html" \
      --output "<保存目录>" --proxy "http://127.0.0.1:7897"
  python flipbook_download.py "<URL>" --format images --pages 1-50
  python flipbook_download.py "<URL>" --proxy ""            # 不走代理

退出码：0 = 成功；1 = 部分成功/校验失败；2 = 失败。
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

# chromedp 前置技能库查找：
# 1) 直接 import（调用方已配置 sys.path 时）
# 2) 环境变量 CHROMEDP_PATH 显式指定其 scripts 目录
# 3) 与前置技能同库的相对布局回溯（<技能库>/chromedp/scripts）
CHROMEDP_ENV = "CHROMEDP_PATH"
CHROMEDP_CANDIDATES = [
    os.environ.get(CHROMEDP_ENV, ""),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "chromedp", "scripts"),
]
DEFAULT_PROXY = "http://127.0.0.1:7897"
HEYZINE_CDN = "https://cdnm.heyzine.com/files/uploaded/"
IMAGE_RE = re.compile(r"(\d{1,4})\.(?:jpg|jpeg|png|webp|gif|avif)(?:\?|$)", re.I)
PAGE_PATH_RE = re.compile(r"(?i)(?:page|mobile|files|img|images?|assets?)[^\d]{0,6}(\d{1,4})")


def find_chromedp():
    """定位前置技能 chromedp。

    返回可 import 的目录路径；返回 "" 表示已可通过 sys.path 直接 import；
    返回 None 表示未找到。不依赖任何绝对路径。
    """
    try:
        import chromedp  # noqa: F401
        return ""
    except ImportError:
        pass
    for p in CHROMEDP_CANDIDATES:
        if p and os.path.isfile(os.path.join(p, "chromedp.py")):
            return p
    return None


def curl_cmd(proxy, extra=None):
    """构造 curl 命令基础段；proxy 为空串则不走代理。"""
    base = [shutil.which("curl") or "curl", "-sS", "--retry", "5", "--retry-delay", "3", "-C", "-"]
    if proxy:
        base += ["-x", proxy]
    if extra:
        base += extra
    return base


def download_file(url, out_path, proxy):
    """下载文件：curl 断点续传 + 重试。返回 (ok, size, elapsed)。"""
    t0 = time.time()
    cmd = curl_cmd(proxy) + ["-o", out_path, url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if r.returncode != 0:
            # 重试耗尽后若文件已存在且非空，可能是此前续传成功但最终 416/curl 报错，交给校验兜底
            if os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
                return True, os.path.getsize(out_path), time.time() - t0
            sys.stderr.write("curl 失败: %s\n" % r.stderr[-500:])
            return False, -1, time.time() - t0
    except subprocess.TimeoutExpired:
        sys.stderr.write("curl 超时（1800s）\n")
        return False, -1, time.time() - t0
    size = os.path.getsize(out_path) if os.path.isfile(out_path) else -1
    return r.returncode == 0, size, time.time() - t0


def verify_pdf(path, expect_pages=None):
    """校验 PDF：文件头 %PDF、文件尾 %%EOF、可选 pypdf 页数核对。返回 (ok, details)。"""
    details = []
    ok = True
    try:
        with open(path, "rb") as f:
            head = f.read(5)
            f.seek(-1024, 2)
            tail = f.read()
    except OSError as e:
        return False, ["无法读取: %s" % e]
    ok_head = head == b"%PDF-"
    ok_tail = b"%%EOF" in tail
    details.append("文件头 %%PDF: %s" % ("✓" if ok_head else "✗"))
    details.append("文件尾 %%EOF: %s" % ("✓" if ok_tail else "✗"))
    ok = ok and ok_head and ok_tail

    if expect_pages:
        try:
            from pypdf import PdfReader
        except ImportError:
            try:
                from PyPDF2 import PdfReader
            except ImportError:
                PdfReader = None
        if PdfReader:
            try:
                n = len(PdfReader(path).pages)
                same = "✓" if n == expect_pages else ("✗ 实际 %d" % n)
                details.append("页数 %d/%d: %s" % (n, expect_pages, same))
                ok = ok and (n == expect_pages)
            except Exception as e:
                details.append("页数解析失败: %s" % e)
        else:
            details.append("页数核对跳过（未安装 pypdf）")
    return ok, details


def detect_platform(client):
    """识别 flipbook 平台，返回 (platform, info_dict)。"""
    info = client.evaluate("""
        (() => {
            const g = {};
            if (window.flipbookcfg) {
                g.platform = 'Heyzine';
                g.flipbookcfg = {
                    mode: window.flipbookcfg.mode,
                    name: window.flipbookcfg.name,
                    num_pages: window.flipbookcfg.num_pages,
                    domain: window.flipbookcfg.domain,
                };
            } else if (window.fliphtml5 || window.fliphtml5book || window.FLIPHTML5) {
                g.platform = 'FlipHTML5';
            } else if (window.FlipBuilder || window.flipPage || window.flipbuilder) {
                g.platform = 'FlipBuilder';
            } else {
                g.platform = 'unknown';
            }
            const res = performance.getEntriesByType('resource').map(e => e.name);
            g.pdfs = res.filter(u => /\\.pdf(\\?|$)/i.test(u));
            g.imgs = res.filter(u => /\\.(jpg|jpeg|png|webp|gif|avif)(\\?|$)/i.test(u));
            return JSON.stringify(g);
        })()
    """)
    try:
        return json.loads(info or "{}")
    except json.JSONDecodeError:
        return {"platform": "unknown"}


def locate_pdf(plat):
    """根据平台特征定位 PDF 直链。返回 URL 或 None。"""
    if plat.get("platform") == "Heyzine":
        cfg = plat.get("flipbookcfg") or {}
        name = cfg.get("name") or ""
        if name.lower().endswith(".pdf"):
            return HEYZINE_CDN + name
    for u in plat.get("pdfs") or []:
        return u  # 通用兜底：取第一个 PDF
    return None


def locate_page_images(plat):
    """从已加载图片 URL 推断分页图片模式。

    返回 (url_template, start, end, ext) 或 None。
    url_template 含 {n} 占位符，如 https://.../files/mobile/{n}.jpg
    """
    urls = plat.get("imgs") or []
    if not urls:
        return None
    # 收集含页号的图片 URL
    numbered = []
    for u in urls:
        m = PAGE_PATH_RE.search(u)
        if m:
            numbered.append((u, int(m.group(1)), m.group(0)))
    if not numbered:
        return None
    # 以出现次数最多的前缀作为模板（numbered 第三元素为匹配到的页号串）
    from collections import Counter
    pref = Counter(u[: u.rfind(pat)] for u, _, pat in numbered)
    base, _ = pref.most_common(1)[0]
    nums = sorted(n for u, n, _ in numbered if u.startswith(base))
    if not nums:
        return None
    # 由第一个 URL 的扩展名确定
    ext = "jpg"
    first = [u for u, n, _ in numbered if n == nums[0]]
    if first:
        ext = first[0].rsplit(".", 1)[-1].split("?")[0]
    return base + "{n}." + ext, nums[0], nums[-1], ext


def download_images(url_template, start, end, ext, out_dir, proxy, prefix="page"):
    """批量下载分页图片。返回 (ok_count, fail_list)。"""
    ok_n, fails = 0, []
    for n in range(start, end + 1):
        u = url_template.format(n=n)
        out = os.path.join(out_dir, "%s_%04d.%s" % (prefix, n, ext))
        cmd = curl_cmd(proxy, ["--fail"]) + ["-o", out, u]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=120)
            if r.returncode == 0 and os.path.isfile(out) and os.path.getsize(out) > 0:
                ok_n += 1
            else:
                fails.append(n)
                if os.path.isfile(out):
                    os.remove(out)
        except subprocess.TimeoutExpired:
            fails.append(n)
    return ok_n, fails


def main():
    ap = argparse.ArgumentParser(description="通用网页翻页画册（flipbook）完整下载")
    ap.add_argument("url", help="画册网页地址")
    ap.add_argument("--output", default=".", help="保存目录（默认当前目录）")
    ap.add_argument("--proxy", default=DEFAULT_PROXY, help="本地代理，默认 %s；传空串禁用" % DEFAULT_PROXY)
    ap.add_argument("--format", choices=["auto", "pdf", "images"], default="auto",
                    help="auto=优先 PDF，无则分页图片；pdf=只要 PDF；images=只要图片")
    ap.add_argument("--pages", default=None, help="分页图片页号范围，如 1-332（默认全部）")
    ap.add_argument("--headless", action="store_true", help="无头模式")
    ap.add_argument("--port", type=int, default=9225, help="CDP 调试端口（默认 9225）")
    ap.add_argument("--wait", type=float, default=10, help="打开页面后的等待秒数（默认 10）")
    args = ap.parse_args()

    out_dir = os.path.abspath(args.output)
    os.makedirs(out_dir, exist_ok=True)

    # 1. 环境检查（依赖树：flipbook-download → chromedp）
    cd_dir = find_chromedp()
    if cd_dir is None:
        print("[错误] 未找到前置技能 chromedp（依赖：flipbook-download → chromedp）。")
        print("      请先安装 chromedp 技能，或设置环境变量 %s 指向其 scripts 目录。" % CHROMEDP_ENV)
        return 2
    if not shutil.which("curl"):
        print("[错误] 未找到 curl，无法下载。")
        return 2
    if cd_dir:
        sys.path.insert(0, cd_dir)
    from chromedp import chromedp_launch, CDPClient  # 延迟导入

    # 2. 启动浏览器并打开画册
    print("== 启动浏览器（端口 %d，代理: %s）==" % (args.port, args.proxy or "无"))
    extra = ["--proxy-server=%s" % args.proxy] if args.proxy else None
    proc = chromedp_launch(url="about:blank", port=args.port, timeout=10,
                           extra_flags=extra, headless=args.headless)
    try:
        time.sleep(4)
        client = CDPClient(port=args.port, url_filter="about:blank", timeout=10)
        print("== 打开画册: %s ==" % args.url)
        client.navigate(args.url)
        # 等待画册配置或资源出现（最长 wait 秒）
        deadline = time.time() + args.wait
        while time.time() < deadline:
            if client.evaluate(
                "typeof window.flipbookcfg !== 'undefined' || "
                "performance.getEntriesByType('resource').length > 20"
            ):
                break
            time.sleep(1)
        time.sleep(2)

        # 3. 平台识别
        plat = detect_platform(client)
        print("== 平台识别 ==")
        print("平台: %s" % plat.get("platform", "unknown"))
        if plat.get("flipbookcfg"):
            c = plat["flipbookcfg"]
            print("  模式: %s | 页数: %s | 源文件名: %s" % (c.get("mode"), c.get("num_pages"), c.get("name")))
        if plat.get("pdfs"):
            print("  发现 PDF 直链 %d 个" % len(plat["pdfs"]))
        if plat.get("imgs"):
            print("  发现图片资源 %d 个" % len(plat["imgs"]))

        # 4. 定位源文件
        pdf_url = locate_pdf(plat)
        img_pat = locate_page_images(plat)
        want_pdf = args.format in ("auto", "pdf")
        want_img = args.format in ("auto", "images") and pdf_url is None

        if want_pdf and pdf_url:
            name = pdf_url.rsplit("/", 1)[-1].split("?")[0]
            out_path = os.path.join(out_dir, name)
            print("== 下载 PDF ==")
            print("源: %s" % pdf_url)
            ok, size, el = download_file(pdf_url, out_path, args.proxy)
            if ok and size > 0:
                print("下载完成: %s（%d 字节，%.1fs）" % (out_path, size, el))
                expect = (plat.get("flipbookcfg") or {}).get("num_pages")
                vok, vd = verify_pdf(out_path, expect_pages=expect)
                print("== 校验 ==")
                for line in vd:
                    print("  " + line)
                client.close()
                print("== 完成: 平台 %s，输出 %s ==" % (plat.get("platform"), out_path))
                return 0 if vok else 1
            print("[警告] PDF 下载失败，尝试分页图片方案…" if want_img else "[错误] PDF 下载失败")
            if not want_img:
                client.close()
                return 1

        if want_img and img_pat:
            tpl, s, e, ext = img_pat
            if args.pages:
                try:
                    a, b = args.pages.split("-")
                    s, e = max(s, int(a)), min(e, int(b))
                except ValueError:
                    print("[警告] --pages 格式应为 N-M，忽略")
            print("== 下载分页图片（%s → %s，模板: %s）==" % (s, e, tpl))
            ok_n, fails = download_images(tpl, s, e, ext, out_dir, args.proxy)
            print("成功 %d 张，失败 %d 张（%s）" % (ok_n, len(fails), fails[:20]))
            client.close()
            return 0 if not fails else 1

        client.close()
        print("[错误] 未定位到源文件。请参考 SKILL.md「手动流程」排查："
              "可能平台不受支持或页面需要更长加载时间（--wait 增大）。")
        return 2
    finally:
        if os.name == "nt":
            try:
                proc.terminate()
            except Exception:
                pass
        else:
            import signal
            try:
                os.kill(proc.pid, signal.SIGTERM)
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
