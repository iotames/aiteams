# 腾讯云 VOD + tcplayer（SimpleAES）调用链

适用平台特征：页面加载 `tcplayer.v4.x.min.js` 与 `hls.min.x.js`，播放器挂在
`blob:` 源上，媒体域名形如 `vod.<厂商域名>`，许可证域名 `drm.vodplayvideo.net`。
（拿云课堂 / 变化课堂 / tenclass 系站点的实测形态。）

## 一、调用链

按顺序发生的请求，定位问题时按此顺序看：

| # | 请求 | 作用 |
|---|---|---|
| 1 | `<业务 API>/live/content/playback?content_id=<id>` | 取回放元信息（封面、雪碧图等） |
| 2 | `<业务 API>/vod/play/signature?biz_label=...&file_id=...` | 取业务签名，返回 `app_id` + `psign`（JWT） |
| 3 | `playvideo.qcloud.com/getplayinfo/v4/<app_id>/<file_id>?psign=...` | 取播放信息：`media.basicInfo`（名称、时长、大小）、各清晰度 URL |
| 4 | `vod.<域名>/<hash>/.../voddrm.token.<JWT>` | master 播放列表（`#EXT-X-STREAM-INF`） |
| 5 | 同上，另一条 `voddrm.token.<JWT>` | media 播放列表：`#EXT-X-KEY:METHOD=AES-128,URI="...getlicense...",IV=0x...` + 分片清单 |
| 6 | `drm.vodplayvideo.net/getlicense/v1?tsrc=EODrmLicense&drmType=SimpleAES&token=<JWT>` | 许可证，返回 **16 字节** |
| 7 | `vod.<域名>/.../<n>_<level>_<i>.ts?encdomain=cmv1` | 加密分片，10 秒一个 |

## 二、关键结论

### 1. 许可证返回的 16 字节不是解密 key

- 步骤 6 的响应是 16 字节，看起来就是 AES key，但**直接拿它解密会得到乱码**。
- 播放器内部会把许可证响应再变换一次，真正用于解密的 key 只在传往 transmuxer
  Worker 的 `decryptdata.key` 里出现。
- 因此唯一可靠做法是钩 `Worker.prototype.postMessage` 取 `msg.decryptdata`。
  `capture_stream.py` 同时钩主线程 `crypto.subtle.decrypt` 作为兜底（播放器版本不同
  时可能走主线程解密）。

### 2. 分片是整段 AES-128-CBC + PKCS7

- 明文是标准 MPEG-TS（188 字节包），密文长度是 16 的整数倍。
- 判定式：`密文长度 - PKCS7 填充 = 188 × 整数`。实测某片 461360 字节 →
  去 8 字节填充 = 461352 = 188 × 2454，完全吻合。
- 去掉填充后，每个字节都应是 `0x47` 同步头（`plain[i] % 188 == 0`）。校验不通过
  说明 key/iv 不对，而不是分片坏了。

### 3. IV 在播放列表里固定给出

- media 播放列表的 `#EXT-X-KEY` 带 `IV=0x...`，**整片所有分片共用**这一个 IV。
- 若换平台遇到 `#EXT-X-KEY` 不带 `IV=`，按 HLS 规范用该分片的 media sequence number
  作 16 字节大端 IV（`fetch_hls.py` 在 `iv` 为空时即按此处理）。

### 4. key / iv 对整个文件通用

- 实测首片、末片（第 1358 片）用同一组 key/iv 均可正确解密，所以只需抓一次。
- 但**播放地址里的 token 与会话和时效绑定**，换课或隔天必须重新抓。

## 三、判定流程（解密失败时逐步排除）

1. 确认 key 来自 `worker.postMessage` 而非许可证响应 → 看 `capture.json` 的
   `key.source` 字段，应为 `worker.postMessage` 或 `crypto.subtle`。
2. 用同一组 key/iv 解第一个和最后一个分片：
   - 两片都失败 → key/iv 组合错，回到第 1 步重抓；
   - 只有部分失败 → 分片下载不完整（对比密文长度是否为 16 的整数倍）。
3. 解密出来是字节数对齐但同步头不对 → 试着换模式：AES-CBC（`-iv` 用播放列表值）、
   AES-CBC（IV 全零）、AES-CTR。三种都失败说明不是标准 HLS AES-128，
   可能是私有加密方案，需要进一步分析播放器代码，不要硬套本技能。
4. 播放器加载 EME（`requestMediaKeySystemAccess`）或 `drmType` 不是 `SimpleAES`
   → 属于强 DRM，超出本技能范围，停止并说明。

## 四、实测参考数据（3 小时 46 分回放）

| 指标 | 值 |
|---|---|
| 分片数 | 1359（10 秒/片） |
| 密文总体积 | 951 MiB |
| 明文总体积 | 947 MiB |
| 成片 | 868 MiB，1920×1080 H.264 + AAC 44.1kHz，536 kbps |
| 下载耗时 | aria2c 16 并发 20.7s |
| 解密耗时 | 16 进程 0.4s |
| 转封装耗时 | `-c copy` 3.8s |

网络侦察时把 `Network.enable` 的 `maxTotalBufferSize` / `maxResourceBufferSize`
调大（脚本已设为 500MB），否则长回放的后半段响应体会被淘汰，取不到播放列表正文。
