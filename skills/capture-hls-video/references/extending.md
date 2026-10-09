# 扩展指南：能力驱动管线

## 为什么按「能力」而不是按「平台」组织

平台会变，协议会被复用。两个真实场景决定了主轴必须是能力：

- **同一平台换协议**：腾讯云 VOD 今天 HLS-TS-SimpleAES，某天改投 DASH-fMP4 或加 Widevine。
  平台名没变，管线却全错——若管线跟着平台走，这种变化会让代码悄悄产出损坏文件。
- **多平台共用协议**：腾讯/阿里/七牛 VOD、以及大量自建 hls.js 站点，都吐 HLS + AES-128。
  若按平台写解密/合并，逻辑会被复制 N 份且各自漂移。

所以本技能把「抓流程」拆成四个**正交能力维度**，管线按 `formats.detect_capabilities`
从页面**实际探测到的东西**分发；平台名不参与决策，只在 `providers/` 里作为「token 请求
URL 提示 + 元信息解析器」存在（`PlatformHint`），是锦上添花。

## 四维能力矩阵

| 维度 | 取值 | 现状 | 决定什么 |
|---|---|---|---|
| `manifest`（播放清单） | `hls`(.m3u8) | ✅ 已实现 | 如何解析出分片清单与 key 声明 |
| | `dash`(.mpd) | ⛔ TODO-1 | |
| `container`（分片封装） | `ts`(MPEG-TS) | ✅ 已实现 | 合并方式、完整性校验（188B/0x47）、remux 输入 |
| | `fmp4`(init.mp4+.m4s) | ⛔ TODO-2 | |
| `encryption`（加密方案） | `aes-128-cbc`(SimpleAES) | ✅ 已实现 | 如何解密（整段 CBC + PKCS7） |
| | `none`（明文） | ✅ 已实现 | |
| | `sample-aes` | ⛔ TODO-3（样本/NAL 级） | |
| | `drm`(Widevine/PlayReady/FairPlay) | ⛔ 不做（合法边界，见下） | |
| `key_source`（密钥来源） | `runtime`（播放器钩子，默认） | ✅ 已实现 | capture 阶段怎么拿到真正用的 key |
| | `m3u8`（EXT-X-KEY URI 直取） | 🟡 部分（TODO-4） | |
| | `license`（可解密的明文 license 接口） | 🟡 部分（TODO-4） | |

`formats.SUPPORTED_*` 三个集合是**唯一的能力真值表**：探测结果只要有一维不在对应集合内，
`Capabilities.supported` 即为 `False`，`fetch_hls.py` 明确拒绝（exit code 2）而非硬跑。

## 新增一项「能力」（让所有平台自动受益）

以支持 fMP4（TODO-2）为例：
1. 在 `fetch_hls.py` 实现 `CONTAINER_VALIDATORS["fmp4"] = _validate_fmp4`（查 ftyp/moof/mdat）；
2. 合并改为按 init 段 + moof 时间线拼接（或 ffmpeg concat demuxer），`remux` 输入格式随之调整；
3. 在 `formats.SUPPORTED_CONTAINER` 加入 `"fmp4"`；
4. 在 `tests/test_pipeline.py` 补：探测到 `.m4s`/`EXT-X-MAP` → supported=True 且往返正确。
   **不补测试不算完成。**

## 新增一个「平台」（不动管线）

1. `providers/<platform>.py` 定义 `PlatformHint`：填 `host_hints` / `url_hints`
   （定位取元信息的请求）/ `extra_playlist_hints`（非 .m3u8 但带播放 token 的 URL 片段）/
   `meta`（把某条响应解析成 `{name,size,duration,drm_type?}`）；
2. `providers/__init__.py` 的 `REGISTRY` 里 import 并追加（具名平台在前，`generic` 永远最后）。
   平台**不需要**声明容器/加密——那由 `formats` 现场探测。

## Roadmap（TODO 口子）

> 每加一项都按上面「能力」流程落地并补回归测试；DRM 一项明确不做。

- **TODO-1 DASH(.mpd)**：YouTube、大量点播/直播走 MPEG-DASH。需要 `manifest=dash` 的清单
  解析器（`AdaptationSet/Representation/SegmentTemplate`）产出分片清单 + KID→key 映射。
  与 HLS 共用后续 container/encryption 处理器（多数是 fMP4，依赖 TODO-2）。
- **TODO-2 fMP4 容器**：HLS 的 `EXT-X-MAP` 与 DASH 的分片形态。合并/校验/remux 需按
  `init.mp4 + moof/mdat` 处理，不再用 188B TS 同步头校验。
- **TODO-3 SAMPLE-AES**：Apple 在 fMP4 上的加密（NAL 样本级）。仅当能合法拿到运行时
  key 时才适用；若伴随 FairPlay 则落到「不做」。
- **TODO-4 key 直取路径**：`EXT-X-KEY:URI` 指向的 key 端点、或明文 license 接口，可在
  带 cookie/referer 的前提下直接 GET，省去注入钩子（部分站点的降级路径）。
- **TODO-5 FLV 直连**：旧点播与部分直播仍吐 `.flv`。需要 flv 分片拼接 + 时间戳/头修复的
  container 实现（`container="flv"`）。
- **TODO-6 多音轨 / 字幕轨**：HLS `EXT-X-MEDIA`（renditions/subtitles）、DASH
  `AdaptationSet`。分别抓取后用 ffmpeg 合并；字幕 webvtt→srt 提取。
- **TODO-7 分片级密钥轮换**：播放列表出现多条 `#EXT-X-KEY`（METHOD/URI/IV 随序列切换）、
  或每分片 `IV = media-sequence`。现假设全局单 key/iv，需要按 KEY 段/序号切换。
- **TODO-8 稳健性**：大文件流式解密（降低内存峰值）、CDN 限流自适应退避、断点校验增强。
- **TODO-9 扩展落地后同步更名（`capture-hls-video` 是刻意保守的当前能力名）**：
  - **触发条件**：只有当 `formats.SUPPORTED_*` 真正扩展到 **DASH 或 fMP4 已跑通并补了回归测试**、「非 HLS 也能下」成为**事实**时，才更名。命名要跟着**已实现能力**走、不跟着 roadmap 走——提前用泛名会造成"名大实小"（用户以为任意网页视频都能下，结果被闸门拒绝），违背工程诚实。
  - **触发匹配靠 `description` 关键词，不靠 `name`**：所以在更名前，名字里留 `hls` 不会损失「用户说"下载网页视频"时命中」的能力，无需为此提前改名。
  - **更名要同步改这几处（`name` 必须等于目录名，skill 约定）**：
    1. 技能目录 `skills/capture-hls-video/` → 新名；
    2. `SKILL.md` frontmatter 的 `name:`；
    3. `skills/README.md` 表格行 + 依赖树两处引用；
    4. 全局软链 `~/.agents/skills/capture-hls-video` 需按新名重建；
    5. `description` 泛化（去掉只提 HLS 的措辞，如实列出已支持的协议/容器）。
  - **候选名**：`capture-web-video`（最贴合"网页视频归档"定位）或 `web-video-archiver`。

## 合法边界（硬约束，不随迭代放开）

只处理「浏览器已能合法播放、且用户有权留存」的内容，借浏览器已完成的下发/解密链路。
**Widevine / PlayReady / FairPlay（L1/L3）等强 DRM 明确不做**：探测到 `drm_type` 非
SimpleAES、或播放器调用 EME `requestMediaKeySystemAccess` 时，`encryption=drm` →
`supported=False`，改为告知用户走平台正规离线方式（App 内缓存 / 向客服索取）。
