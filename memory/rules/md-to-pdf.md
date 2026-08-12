## Markdown 转 PDF

**推荐用 chromedp 技能，减少外部依赖**

1. markdown 转 HTML → 用 `chromedp` 的 `print_to_pdf`（CDP + headless Chrome）打印；禁用 npm/puppeteer/weasyprint/pandoc。
2. 不装 Poppler/pymupdf/reportlab，质检仅用 pypdf，视觉确认交用户。
3. 页眉模板仅含文件名、页脚仅含页码；不用 CLI `--print-to-pdf-no-header`，统一走 CDP 自定义模板，避免默认模板混入 `file://` 路径与时间戳。
4. pypdf 剥离元数据（`writer.metadata = None`），并校验产物不含 `file://` 与时间戳。
5. 浏览器缺失用 `chromedp_find_chrome()` 探测，仍无则询问用户。
