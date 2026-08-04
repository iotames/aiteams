---
name: flipbook-download
description: >-
  下载网页版翻页画册 / 电子画册 / 产品目录（flipbook）。
  当用户想要"下载 / 保存 / 抓取某个画册、flipbook、翻页电子书、产品目录（catalogue）、产品手册"时务必使用本技能，
  即使网页上没有下载按钮。支持 Heyzine（hflip.co / heyzine.com）、FlipHTML5、FlipBuilder 等主流 flipbook 平台，
  自动识别平台并定位源文件（优先 PDF 直链，其次分页图片，最后 canvas 截屏兜底），
  经本地代理 + 断点续传完整下载，并校验文件完整性。
metadata:
  version: 1.0.0
---

# flipbook-download — 网页画册完整下载

## 设计原则

- **源文件优先**：绝大多数 flipbook 本质是 PDF（如 Heyzine `mode:"PDF"`），先找 PDF 直链，质量最高、最完整，无需逐页拼接
- **平台识别驱动**：通过 CDP 读取页面全局变量识别平台，再按平台特征定位源文件，避免盲猜
- **确定性交给脚本**：探测 → 识别 → 定位 → 下载 → 校验是重复性任务，由 `scripts/flipbook_download.py` 完成，AI 只负责解读结果与处理异常
- **下载走代理 + 断点续传**：`curl -C - --retry`，大文件（几十上百 MB）中途失败可续传

## 环境要求

依赖树（前置技能需先安装）：

```
flipbook-download
└── chromedp（前置技能，提供 CDP 浏览器控制）
    └── Python 3.7+ / websocket-client
```

- Python 3.7+
- 前置技能 **chromedp**：脚本运行时自动查找其库目录（先尝试直接 `import`，再按与前置技能同库的相对布局回溯）；找不到时可用环境变量 `CHROMEDP_PATH` 显式指向其 `scripts` 目录
- `websocket-client`（chromedp 的依赖，`pip install websocket-client`；中国大陆环境优先国内镜像 `-i https://pypi.tuna.tsinghua.edu.cn/simple`）
- `curl`（命令行下载）
- 可选：`pypdf`（用于 PDF 页数校验，缺省时跳过页数核对，不影响下载）

## 快速使用

```bash
python <flipbook-download 技能目录>/scripts/flipbook_download.py \
  "<画册URL>" \
  --output "<保存目录>" \
  --proxy "http://127.0.0.1:7897"
```

示例（本机代理为 127.0.0.1:7897，按实际环境调整）：

参数说明：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `URL`（位置参数） | 必填 | 画册网页地址 |
| `--output DIR` | 当前目录 | 保存目录 |
| `--proxy URL` | `http://127.0.0.1:7897` | 本地代理；不需要可传 `--proxy ""` |
| `--format` | `auto` | `auto`=优先 PDF，无则分页图片；`pdf`=只要 PDF；`images`=只要图片 |
| `--pages N-M` | 全部 | 分页图片模式下限定页号范围（如 `1-332`） |
| `--headless` | 有头 | 强制无头模式（服务器环境） |
| `--port N` | 9222 | CDP 调试端口 |

输出：保存文件 + 校验报告（大小 / 文件头 / 页数 / 是否完整）。

## 平台支持

| 平台 | 识别特征 | 源文件定位 | 验证状态 |
|---|---|---|---|
| Heyzine（hflip.co / heyzine.com） | `window.flipbookcfg` 且 `mode:"PDF"` | `cdnm.heyzine.com/files/uploaded/<hash>.pdf` | ✅ 已实测（332 页 / 85MB） |
| FlipHTML5（fliphtml5.com） | `window.fliphtml5` / `fliphtml5book` 等全局变量 | 分页图片 URL 模式（启发式） | ⚠️ 启发式，待真实站点验证 |
| FlipBuilder（flipbuilder.com） | `window.FlipBuilder` / `flipPage` | 分页图片 URL 模式（启发式） | ⚠️ 启发式，待真实站点验证 |
| 通用兜底 | 从 `performance.getEntriesByType('resource')` 找 `.pdf`；图片 URL 正则（`page{N}` / `mobile/{N}` / `files/{N}.jpg`） | PDF 直链 或 批量分页图片 | ✅ 机制通用 |

脚本输出识别到的平台与源文件类型；若启发式平台识别失败，改用下方手动流程排查。

## 手动流程（脚本失效时的排查步骤）

1. **打开页面**：CDP 启动浏览器（带代理 `--proxy-server`），导航到画册 URL，等待画册初始化
2. **平台识别**：`evaluate` 枚举 `Object.keys(window)`，找 `flipbookcfg`（Heyzine）、`fliphtml5`、`FlipBuilder` 等特征变量；输出其 JSON 摘要
3. **找 PDF 直链**：`performance.getEntriesByType('resource')` 过滤 `.pdf`；或读 `flipbookcfg.name`（Heyzine 为 `<hash>.pdf`，拼上 `https://cdnm.heyzine.com/files/uploaded/`）
4. **找分页图片**：正则匹配已加载图片 URL，推断页号模式（如 `.../files/mobile/{n}.jpg`），首尾页确认起止页号
5. **下载**：`curl -x <proxy> -C - --retry 5 -o <file> <URL>`；分页图片用循环批量下载
6. **校验**：大小与服务器 `content-length` 一致、头部 `%PDF`、尾部 `%%EOF`、页数用 pypdf 核对
7. **兜底 canvas 截屏**：逐页翻页 + `Page.captureScreenshot`（仅当无 PDF 且图片 URL 无法枚举时；质量受视口限制）

## 注意事项

- **下载按钮隐藏 ≠ 文件不可访问**：Heyzine 等平台常设 `show_download:0` 隐藏下载按钮，但源 PDF 在 CDN 上公开可访问且支持 `Range` 断点续传，直链下载完全可行
- **防盗链**：个别 CDN 校验 `Referer`/`Cookie`，此时用浏览器 context 内 `fetch`（`evaluate_async`）或带浏览器 Cookie 的 curl 下载
- **大文件续传**：务必 `-C -`，中途失败 `--retry` 自动续传；校验最终大小
- **代理**：目标站点需代理时，浏览器启动参数与 curl 都要带同一代理
- **页数巨大**：332 页画册约 85MB PDF 属正常；分页图片方案一次拉全量可能上千张，先用 `--pages` 抽样确认 URL 模式
- **启发式平台**：FlipHTML5 / FlipBuilder 分支未经真实站点验证，识别失败时按"手动流程"排查，并把新的平台特征补进脚本
