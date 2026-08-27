#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""网页/HTML → Markdown 转换器（Python 标准库实现，无第三方依赖）。

用法：
    python3 convert.py <输入> [--output 输出.md] [--base-url <URL>]

<输入> 可以是 http(s):// 网址或本地 .html 文件路径。
--base-url 用于补全页面内的相对链接；输入为网址时默认取该网址。
--output 指定输出 .md 路径；缺省时：本地文件取同名 .md，网址取路径最后一段。

转换保真：
    - 标题层级、段落、加粗/斜体/行内代码、列表、表格、引用块
    - 代码块（保留语法高亮语言名，按行还原）
    - 相对链接补全为绝对地址（给定 base-url 时）
    - <details>/<summary> 折叠块展开为普通内容
    - 提示框（Docusaurus admonition）转 Markdown 引用块
    - 自动跳过导航、脚本、按钮、图标等非正文元素
"""

import argparse
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# 成对出现、需要整块跳过的标签
SKIP_TAGS = {"svg", "path", "button", "script", "style", "meta", "nav", "iframe", "img"}
# HTML 空元素（无结束标签），不参与跳过计数，否则计数会泄漏
VOID_NOOP = {
    "meta", "img", "link", "input", "source", "wbr",
    "col", "area", "base", "embed", "track", "param", "br",
}


def fetch_html(source: str) -> str:
    """读取网页或本地 HTML 文件的文本内容。"""
    if source.startswith(("http://", "https://")):
        req = urllib.request.Request(source, headers={"User-Agent": DEFAULT_UA})
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            charset = resp.headers.get_content_charset()
    else:
        raw = Path(source).read_bytes()
        charset = None
    for enc in (charset, "utf-8", "gb18030"):
        if not enc:
            continue
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def extract_main(html: str) -> str:
    """移除页面级噪音后，按优先级选出正文区域（article > main > body）。"""
    # 移除分页导航与移动端目录按钮等噪音块
    html = re.sub(
        r'<nav[^>]*class="[^"]*pagination-nav[^"]*".*?</nav>', "", html, flags=re.S
    )
    html = re.sub(
        r'<div[^>]*class="[^"]*tocCollapsible[^"]*"[^>]*>.*?</div>',
        "", html, flags=re.S,
    )

    for tag in ("article", "main", "body"):
        matches = [
            m.group(1)
            for m in re.finditer(rf"<{tag}[^>]*>(.*?)</{tag}>", html, re.S)
        ]
        if matches:
            return max(matches, key=lambda s: len(re.sub(r"<[^>]+>", "", s)))
    return html


def page_title(html: str):
    """提取 <title> 文本，供默认输出文件名参考。"""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S)
    if m:
        title = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if title:
            return title
    return None


def default_output(input_arg: str) -> Path:
    """根据输入自动生成默认 .md 输出路径。"""
    if not input_arg.startswith(("http://", "https://")):
        return Path(input_arg).with_suffix(".md")
    parsed = urllib.parse.urlparse(input_arg)
    parts = [p for p in parsed.path.split("/") if p]
    slug = parts[-1] if parts else parsed.netloc
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", slug).strip("-")
    return Path(slug + ".md") if slug else Path(parsed.netloc + ".md")


class MD(HTMLParser):
    """Docusaurus/通用 HTML → Markdown 转换器。

    实现要点（都是实战踩过的坑）：
    - 跳过计数（skip）只对成对标签生效，空元素提前返回，避免计数泄漏；
    - Prism 代码块按 token-line 分组还原，行内 span 只取文本；
    - li 内的 <p> 开始时不冲掉孤立的列表标记；
    - 链接相对路径用 base_url 补全。
    """

    def __init__(self, base_url=None):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.out = []            # [(kind, payload)]
        self.cur = []            # 行内 token：str 或 ('LINKSTART', href) / ('LINKEND', None)
        self.skip = 0
        self.pre = False
        self.pre_lang = ""
        self.pre_lines = []
        self.pre_line = None
        self._span_stack = []
        self._div_stack = []
        self.table = None
        self.row = None
        self.cell = None
        self.list_stack = []
        self.admon_level = 0
        self.admon_title = None
        self.admon_paras = []
        self.quote_level = 0
        self.quote_paras = []

    # ---------- 工具 ----------
    def push(self, tok):
        if self.cell is not None:
            self.cell.append(tok)
        else:
            self.cur.append(tok)

    def flush(self):
        if not self.cur:
            return
        if self.admon_level:
            self.admon_paras.append(self.cur)
        elif self.quote_level:
            self.quote_paras.append(self.cur)
        else:
            self.out.append(("p", self.cur))
        self.cur = []

    def marker_only(self):
        """cur 是否仅含列表标记（如 '-' 或 '1.'）。"""
        if not self.cur:
            return False
        return all(isinstance(t, str) for t in self.cur) and bool(
            re.fullmatch(r"[\-\d.]+", "".join(self.cur).strip())
        )

    def emit(self, kind, payload):
        self.out.append((kind, payload))

    # ---------- 解析 ----------
    def handle_starttag(self, tag, attrs):
        if tag in VOID_NOOP:
            if self.skip == 0:
                if tag == "br":
                    if self.pre:
                        # Prism 行内 <br> 只作分隔（忽略）；普通 <pre> 手写换行保留
                        if not self.seen_token_line and self.pre_line is not None:
                            self.pre_line.append("\n")
                    else:
                        self.push("\n")
                elif tag == "hr":
                    self.flush()
                    self.emit("hr", None)
            return
        if self.skip:
            self.skip += 1
            return
        attrs = dict(attrs)
        cls = attrs.get("class", "")
        if tag == "span":
            self._span_stack.append(cls)
        elif tag == "div":
            self._div_stack.append(cls)

        if tag in SKIP_TAGS:
            self.skip = 1
            return
        if tag == "pre":
            self.flush()
            self.pre = True
            self.pre_lines = []
            m = re.search(r"language-([A-Za-z0-9_-]+)", cls)
            self.pre_lang = m.group(1) if m else ""
            self.pre_line = []
            self.seen_token_line = False
            return
        if self.pre:
            if tag == "code" and not self.pre_lang:
                # 通用 HTML 的 language-* 常写在 <code> 而非 <pre> 上
                m = re.search(r"language-([A-Za-z0-9_-]+)", cls)
                self.pre_lang = m.group(1) if m else ""
            if tag == "span" and "token-line" in cls.split():
                self.seen_token_line = True
                self.pre_line = []
            return

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.flush()
            self.cur.append("#" * int(tag[1]) + " ")
        elif tag == "p":
            if not self.marker_only():
                self.flush()
        elif tag == "a":
            if "hash-link" in cls:
                self.skip = 1
            else:
                self.push(("LINKSTART", attrs.get("href", "")))
        elif tag == "code":
            self.push("`")
        elif tag in ("strong", "b"):
            self.push("**")
        elif tag in ("em", "i"):
            self.push("*")
        elif tag == "del":
            self.push("~~")
        elif tag == "ul":
            self.flush()
            self.list_stack.append(("ul", None))
        elif tag == "ol":
            self.flush()
            self.list_stack.append(("ol", 0))
        elif tag == "li":
            self.flush()
            indent = "    " * (len(self.list_stack) - 1)
            if self.list_stack and self.list_stack[-1][0] == "ol":
                self.list_stack[-1] = ("ol", self.list_stack[-1][1] + 1)
                self.cur.append(f"{indent}{self.list_stack[-1][1]}. ")
            else:
                self.cur.append(f"{indent}- ")
        elif tag == "table":
            self.flush()
            self.table = []
            self.row = None
        elif tag == "tr":
            self.row = []
        elif tag in ("th", "td"):
            self.cell = []
        elif tag == "blockquote":
            self.flush()
            self.quote_level += 1
        elif tag == "summary":
            self.flush()
            self.cur.append("**")
        elif tag == "div":
            if "theme-admonition" in cls:
                self.flush()
                self.admon_level += 1
                self.admon_title = None
                self.admon_paras = []
            elif "admonitionHeading" in cls and self.admon_level:
                self.flush()
            else:
                self.flush()

    def handle_endtag(self, tag):
        if self.skip:
            self.skip -= 1
            return
        if tag in VOID_NOOP:
            return
        if self.pre:
            if tag == "span" and self._span_stack:
                popped = self._span_stack.pop()
                if "token-line" in popped.split():
                    self.pre_lines.append("".join(self.pre_line or []))
                    self.pre_line = None
            if tag == "pre":
                self.pre = False
                if self.pre_line is not None:
                    self.pre_lines.append("".join(self.pre_line))
                    self.pre_line = None
                self.emit("code", (self.pre_lang, self.pre_lines))
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p"):
            self.flush()
        elif tag == "a":
            self.push(("LINKEND", None))
        elif tag == "code":
            self.push("`")
        elif tag in ("strong", "b"):
            self.push("**")
        elif tag in ("em", "i"):
            self.push("*")
        elif tag == "del":
            self.push("~~")
        elif tag == "li":
            self.flush()
        elif tag in ("ul", "ol"):
            self.flush()
            if self.list_stack:
                self.list_stack.pop()
            self.emit("blank", None)
        elif tag == "tr":
            if self.table is not None and self.row is not None:
                self.table.append(self.row)
            self.row = None
        elif tag in ("th", "td"):
            if self.row is not None and self.cell is not None:
                self.row.append(self.cell)
            self.cell = None
        elif tag == "table":
            self.flush()
            self.emit("table", self.table)
            self.table = None
        elif tag == "blockquote":
            self.flush()
            self.quote_level -= 1
            self.emit("quote", (None, self.quote_paras))
            self.quote_paras = []
        elif tag == "summary":
            self.cur.append("**")
            self.flush()
        elif tag == "div":
            if self.admon_level and self._div_stack:
                cls = self._div_stack.pop()
                if "admonitionHeading" in cls:
                    self.admon_title = self.cur
                    self.cur = []
                elif "theme-admonition" in cls:
                    self.admon_level -= 1
                    self.flush()
                    self.emit("quote", (self.admon_title, self.admon_paras))
                else:
                    self.flush()
            else:
                self.flush()

    def handle_data(self, data):
        if self.skip:
            return
        if self.pre:
            if self.pre_line is not None:
                self.pre_line.append(data)
            return
        if self.cell is not None:
            if data.strip() or self.cell:
                self.cell.append(data)
            return
        if data.strip():
            self.cur.append(data)
        elif (
            self.cur
            and not self.marker_only()
            and any(isinstance(t, str) and t.strip() for t in self.cur)
        ):
            self.cur.append(data)

    # ---------- 渲染 ----------
    def resolve(self, href):
        if not href or href.startswith(
            ("#", "http://", "https://", "mailto:", "tel:", "data:", "javascript:")
        ):
            return href
        if self.base_url:
            return urllib.parse.urljoin(self.base_url, href)
        return href

    def render_inline(self, toks):
        out = []
        i = 0
        while i < len(toks):
            t = toks[i]
            if isinstance(t, str):
                out.append(t)
                i += 1
                continue
            if t[0] == "LINKSTART":
                href = t[1]
                j = i + 1
                depth = 1
                label = []
                while j < len(toks):
                    u = toks[j]
                    if isinstance(u, tuple):
                        if u[0] == "LINKSTART":
                            depth += 1
                        elif u[0] == "LINKEND":
                            depth -= 1
                            if depth == 0:
                                break
                    label.append(u)
                    j += 1
                text = self.render_inline(label)
                out.append(f"[{text}]({self.resolve(href)})")
                i = j + 1
            else:
                i += 1
        return "".join(out).strip()

    def finish(self):
        self.flush()
        lines = []

        def blank():
            """块之间至多保留一个空行（不压缩代码块内部空行）。"""
            if lines and lines[-1] != "":
                lines.append("")

        for kind, payload in self.out:
            if kind == "p":
                # render_inline 会 strip 行首空白，列表项的嵌套缩进在此恢复
                leading = (
                    len(payload[0]) - len(payload[0].lstrip(" "))
                    if payload and isinstance(payload[0], str)
                    else 0
                )
                t = self.render_inline(payload)
                if t:
                    blank()
                    lines.append(" " * leading + t)
            elif kind == "code":
                lang, code_lines = payload
                blank()
                lines.append(f"```{lang}")
                lines.extend(code_lines)  # 原样保留行与空行
                lines.append("```")
            elif kind == "table":
                if not payload:
                    continue

                def fmt(c):
                    return self.render_inline(c).replace("|", "\\|")

                header = [fmt(c) for c in payload[0]]
                blank()
                lines.append("| " + " | ".join(header) + " |")
                lines.append("| " + " | ".join("---" for _ in header) + " |")
                for r in payload[1:]:
                    lines.append("| " + " | ".join(fmt(c) for c in r) + " |")
            elif kind == "quote":
                title, paras = payload
                if title or any(self.render_inline(p) for p in paras):
                    blank()
                    if title:
                        lines.append("> **" + self.render_inline(title) + "**")
                    for p in paras:
                        t = self.render_inline(p)
                        if t:
                            lines.append("> " + t)
            elif kind == "blank":
                blank()
            elif kind == "hr":
                blank()
                lines.append("---")
        text = "\n".join(lines).rstrip() + "\n"
        text = text.replace("\u200b", "")
        return text


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="html2markdown",
        description="把网页（网址或本地 HTML 文件）转换为 Markdown 文件",
    )
    parser.add_argument("input", help="http(s):// 网址或本地 .html 文件路径")
    parser.add_argument("--output", "-o", help="输出 .md 文件路径（缺省自动生成）")
    parser.add_argument(
        "--base-url",
        help="补全相对链接用的基准 URL（输入为网址时默认取该网址）",
    )
    args = parser.parse_args(argv)

    html = fetch_html(args.input)
    is_url = args.input.startswith(("http://", "https://"))
    base = args.base_url or (args.input if is_url else None)
    body = extract_main(html)
    md = MD(base_url=base)
    md.feed(body)
    md.close()
    text = md.finish()

    out = Path(args.output) if args.output else default_output(args.input)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
