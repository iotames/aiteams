---
name: capture-hls-video
description: >-
  抓取网页里正在播放的加密 HLS 视频并归档成 MP4：注入钩子拿真实解密 key、并发下载分片、
  AES-128 解密、转封装。当用户说"下载网页里的视频""保存课程回放""把直播回放存下来"，
  或提到 m3u8 / HLS / AES-128 加密 / blob: 视频 / hls.js / tcplayer / 腾讯云 VOD /
  getplayinfo / 播放器 blob 源时务必使用此技能。仅适用于用户有权访问且有权留存的内容，
  不适用于 Widevine/PlayReady/FairPlay 等强 DRM。
license: Apache-2.0
compatibility: >-
  需要 Python 3.10+ 与 websocket-client、cryptography；外部命令 ffmpeg 必需，
  aria2c 可选（未装则回退内置并发下载）。前置技能：chromedp（启动并接管浏览器）。
metadata:
  version: 1.0.0
---

# 网页加密 HLS 视频归档

把「能在浏览器里看、但拿不到文件」的 HLS 视频变成本地 MP4。核心思路是**借浏览器已完成
的鉴权与解密链路**：页面能播，说明 key 已经合法下发到浏览器进程，我们只是把它读出来。

## 适用范围与前提

只在满足以下条件时执行：

- 内容**归你所有**，或你已获得版权方归档授权（如自己制作的课程、自己购买且平台允许留存的内容）；
- 用户当前已能在浏览器里正常播放该内容（技能不绕过登录、付费或权限校验）。

以下情况**不做**，改为告知用户平台的正规离线方式（App 内缓存、向客服索取回看文件）：

- Widevine / PlayReady / FairPlay 等强 DRM（特征是 `drmType` 不是 `SimpleAES`，
  或播放器调用了 EME 的 `requestMediaKeySystemAccess`）；
- 用户对内容没有访问权限，需要破解登录或伪造票据。

## 流程总览

| 步骤 | 命令 | 产出 |
|---|---|---|
| 0 前置 | 用 chromedp 技能打开回放页并登录，确认画面在播 | 带调试端口的浏览器 |
| 1 侦察 | `python3 scripts/capture_stream.py --match <id> --out capture.json` | 分片清单 + 真实 key/iv |
| 2 归档 | `python3 scripts/fetch_hls.py --capture capture.json --out-dir <目录>` | MP4 |
| 3 校验 | `ffprobe` 看时长/流信息，`ffmpeg -c copy -f null -` 走全片 | 无报错即通过 |

## 第 0 步：准备浏览器

用 **chromedp 技能**启动浏览器（它负责找 Chrome、拉起调试端口、接管已有页面），
打开回放页并完成登录，然后确认**视频真的在播**——本技能的钩子靠播放动作触发，
页面停在封面上就什么都抓不到。

```python
# 示意：实际按 chromedp 技能文档调用
chromedp_launch(browser="<Chrome 可执行文件路径>", url="<回放页地址>", port=9222)
```

> deepin/麒麟的 Chrome 在 `/opt/apps/<包名>/files/google/chrome/chrome`。
> 传 `/opt/apps/<包名>` 这类包目录时 chromedp 技能会自己下探定位；仍报错就直接给完整可执行文件路径。

## 第 1 步：抓播放参数

```bash
cd <技能目录>
python3 scripts/capture_stream.py --match 917414 --port 9222 --out capture.json
```

| 参数 | 说明 |
|---|---|
| `--match` | **必填**。定位标签页的 URL 片段，用能唯一区分的那段（一般是内容 id）。同域多标签页时不填必连错页 |
| `--port` | 调试端口，默认 9222 |
| `--wait` | 最长采集秒数，默认 45；抓到 key 就提前结束 |
| `--reload` | 先重载页面再挂钩子。**默认不用**，理由见下 |
| `--out` | 输出 JSON 路径，默认 `capture.json` |
| `--verbose` | 打印播放状态等中间信息，排查时加 |

默认**不重载页面**：钩子只对「之后发生」的解密生效，而正在播放的页面会持续拉分片、
持续解密，挂上钩子几秒内就能抓到 key。反过来，CDP 触发的 `reload` 不携带用户激活，
Chrome 自动播放策略会让播放器停在 00:00，既不拉分片也不解密——越重载越抓不到。
让页面保持正在播放，是最稳的形态。

`capture.json` 里的关键字段：

- `segments` / `segment_base`：分片名列表与目录前缀
- `key.hex` / `key.iv`：**播放器真正用于解密的 key 和 IV**，`key.source` 标明抓到它的路径
- `license`：许可证接口的原始响应字节（用来做对比，见下方坑位）
- `vod_info`：平台侧元信息（名称、时长、大小），做输出文件名时可直接用
- `format`：`detect_capabilities` 探测到的能力 `{manifest,container,encryption,key_source,supported,reason}`；`fetch_hls.py` 据此选管线，`supported=false` 会被明确拒绝（见「适用范围」与 `references/extending.md`）

**没抓到 `key` 就停下**：先让页面确实播放几秒再重试，不要带着 `key: null` 往下走。

## 第 2 步：下载、解密、转封装

```bash
python3 scripts/fetch_hls.py --capture capture.json --out-dir ./out --title "课程名"
```

| 参数 | 说明 |
|---|---|
| `--out-dir` | 工作目录，内部再分 `enc/`（加密分片，默认完事即删）、`dec/`、`combined.ts` |
| `--jobs` | 并发数，默认 16。CDN 正常时整部影片通常一两分钟 |
| `--referer` | 默认按页面源站自动推导，CDN 校验来源时用它覆盖 |
| `--keep-enc` | 保留加密分片，便于失败重跑 |
| `--no-remux` | 只要合并后的 `combined.ts` |
| `--key` / `--iv` | 覆盖 `capture.json` 里的值 |

管线不按平台、按探测到的能力分发：`fetch_hls.py` 读 `capture.json` 的 `format`，只有 `HLS + TS + (AES-128-CBC|明文)` 会落地；DASH / fMP4 / SAMPLE-AES 等会被闸门拒绝并给出 roadmap 指引（exit 2），**不会**硬跑产出损坏文件。扩展见 `references/extending.md`。

已实现断点续跑：`enc/` 中已存在且非空的分片会被跳过，重跑不必重下。
解密后逐片校验（16 字节对齐 + PKCS7 填充 + 188 字节 TS 同步头），任何一片不达标即
报错退出并列出具体分片，避免产出静默损坏的成片。

## 第 3 步：校验成片

```bash
ffprobe -v error -show_entries format=duration,size \
  -show_entries stream=codec_name,width,height -of default=nw=1 "<成片>.mp4"
ffmpeg -v error -i "<成片>.mp4" -c copy -f null -          # 无输出即通过
ffmpeg -v error -ss 2:00:00 -t 30 -i "<成片>.mp4" -f null -   # 抽查中段能解码
```

成片时长应与页面播放器显示的一致；不一致说明有分片缺失或重复。

## 坑位速查

以下都是同类任务真实翻过车的点，按此判断，不要凭直觉走。

| 现象 | 原因与正确做法 |
|---|---|
| 许可证接口返回 16 字节，拿它当 key 解密全是乱码 | 许可证响应**不等于**播放器实际使用的 key（服务端做了变换）。必须由钩子从播放器内部读，`capture_stream.py` 已默认这样做 |
| 主线程钩 `crypto.subtle.decrypt` 抓不到任何东西 | hls.js 默认把解密丢进 transmuxer **Worker**。必须同时钩 `Worker.prototype.postMessage`，从消息里的 `decryptdata.key/iv` 取值 |
| 解密结果不是 TS（无 0x47 同步头） | 先确认 key/iv 确实来自钩子；再确认整段都用 AES-CBC（有些方案只加密前 N 字节或改用 CTR）。逐步判定流程见 `references/tencent-vod.md` |
| 缓存 `blob:` 地址没用 | `blob:` 只是 MSE 的内存句柄，不是可下载地址。真实地址在 m3u8 与 `.ts` 请求里 |
| `aria2c: invalid option -- 'H'` | aria2c 1.37+ 只认 `--header=`，脚本已按此拼参 |
| 直接把 `.ts` 拼起来 ffmpeg 报错 | 解密后每片尾部有 PKCS7 填充，必须先去掉再拼接，脚本已处理 |
| 采集脚本挂住不返回 | 别用 chromedp 技能的 `CDPClient` 做长时间事件采集——它按命令等响应，会与采集循环互相阻塞。本技能的 `cdp_capture.Page` 用裸 WebSocket 自己收发，正是为这个场景 |
| `Runtime.evaluate` 莫名超时 | 两种成因：① 用带超时的 `recv()` 读包，超时卡在一帧消息中途会让 WebSocket 错位，之后所有命令都超时——必须先 `select` 确认可读再读（`cdp_capture.Page.collect` 已这样做）；② 页面在导航中，发往旧执行上下文的 `evaluate` 会被丢弃，重试即可 |
| 页面弹出 JS 对话框导致整轮采集卡死 | 弹窗期间渲染进程被阻塞。`collect()` 收到 `Page.javascriptDialogOpening` 会自动接受掉；自写采集循环时要一并处理 |
| 重载后播放器停在 00:00、`play()` 报 NotAllowedError | CDP 触发的 reload 不带用户激活，自动播放被策略拒绝。默认别重载；确有需要时用 `Input.dispatchMouseEvent` 派发**真实点击**（JS 里 `element.click()` 不算用户激活）再 `play()`，即 `--reload` 走的路径 |
| 采不到任何 m3u8 请求 | 页面没在播、`--match` 指错标签页，或分片是 fMP4（`.m4s`，需按 fMP4 思路处理而非本技能的 TS 校验）。用 chromedp 技能的 `list_tabs()` 逐个确认 |
| 不重载时钩子装了却抓不到 key | `Page.addScriptToEvaluateOnNewDocument` **只对新文档生效**，不 reload 时对当前已加载页无效；`capture_stream.py` 默认分支已改用 `Runtime.evaluate` 把钩子立即注入当前文档。自写采集时别只注册新文档钩子 |
| 换课时或隔天重跑就失效 | 播放地址里的 token 与会话和时效绑定。换课或隔天必须重新执行第 1 步 |

## 参考文件

按需读取：

- `references/tencent-vod.md` — 腾讯云 VOD（tcplayer + SimpleAES）的完整调用链、字段含义与逐步判定方法
- `scripts/cdp_capture.py` — CDP 采集器（页面定位、钩子注入、事件收集）。其他「注入钩子观察页面」的任务可直接复用
- `references/extending.md` — **能力驱动**设计与 roadmap：四维能力矩阵（manifest/container/encryption/key_source）、如何加能力、如何加平台提示（平台只作元信息/token 提示，不决定管线）
- `scripts/formats/` — 能力探测与处理器注册表（管线主轴）；`scripts/providers/` — 平台提示注册表；技能根 `tests/test_pipeline.py` — 无需浏览器的离线回归测试
