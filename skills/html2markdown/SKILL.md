---
name: html2markdown
description: >-
  把网页转换为 Markdown 文件：支持 http/https 网址或本地 .html 文件作为输入，
  输出 .md 文件。当用户给出网址或 HTML 文件并要求"转成 Markdown"、"下载成 md"、
  "保存为 .md"、"提取网页正文"、整理在线文档为本地笔记时务必使用此技能，
  即使没有明确说出"markdown"或"md"字样（如"把这个网页存下来"）。
license: Apache-2.0
metadata:
  version: "1.0.1"
compatibility: Requires Python 3.10+（仅标准库，无第三方依赖）
---

# html2markdown

把网页（http/https 网址或本地 HTML 文件）转换为 Markdown 文件。转换保真：
标题层级、代码块（含语言标注）、表格、列表、链接、引用块、加粗/斜体/行内代码，
并自动跳过导航、脚本、按钮、图标等非正文元素。

## 使用方法

技能内置转换脚本，优先直接运行（不要手工重写转换逻辑）：

```bash
# 输入为网址（自动下载并转换）
python3 <技能目录>/scripts/convert.py "https://example.com/docs/page"

# 输入为本地 HTML 文件
python3 <技能目录>/scripts/convert.py ./page.html

# 指定输出路径
python3 <技能目录>/scripts/convert.py ./page.html -o DEEPSEEK.md

# 本地文件补全相对链接时，显式给出基准 URL
python3 <技能目录>/scripts/convert.py ./page.html --base-url "https://example.com/docs"
```

输出路径缺省规则：本地文件取同名 `.md`（`page.html` → `page.md`）；网址取
URL 路径最后一段（`.../agent_integrations/codex` → `codex.md`）。命令成功后会
打印生成的文件路径。

下载网址需要网络访问权限：在沙箱环境中若脚本报网络错误，先申请网络/命令
放行后重试，不要改成其他抓取方式。

## 输出规则

把正文整体写入 .md 文件，并遵循以下转换约定：

- 标题 `h1`–`h6` 转 `#`–`######`；`<strong>`/`<b>` 转 `**`，`<em>`/`<i>` 转 `*`，
  行内 `<code>` 转反引号，`<br>` 转换行。
- 代码块保留语言标注（`language-json` → ` ```json `），按行还原，不丢空行。
- 表格转 GFM 管道表格，单元格内 `|` 转义。
- 列表保留有序/无序标记；`<li>` 内嵌 `<p>` 时标记与内容合并为一项。
- 链接保留；相对路径（`/docs/x`、`x.html`）在给定 base-url 时补全为绝对地址，
  锚点（`#...`）与外部协议（http/https/mailto 等）保持原样。
- `<details>/<summary>` 折叠块展开为普通内容；提示框（Docusaurus admonition）
  转 `>` 引用块并加粗标题。
- 自动剔除 `<nav>`、`<svg>`、`<button>`、`<script>`、`<style>` 等非正文元素。
- 正文区域按 `article` > `main` > `body` 优先级取文本最长的候选。

转换完成后向用户确认生成的文件，不要直接修改用户已有的同名文件；若目标
文件已存在，先说明并询问是否覆盖或换名。

## 注意事项

- 页面若为空或明显缺失正文（如只有导航），先检查是否下载到了完整 HTML
  （常见原因：页面依赖 JS 渲染、被反爬拦截）。依赖 JS 渲染的页面不适合本技能，
  改用浏览器类技能先渲染再转。
- 大型页面（如内嵌完整配置 JSON 的文档）转换后体积可能很大，属正常现象，
  不要自行截断内容。
- 脚本只依赖 Python 标准库，不要在技能内引入 requests/bs4 等第三方包；
  若执行环境缺 Python，先安装 Python 3.10+ 再运行。
