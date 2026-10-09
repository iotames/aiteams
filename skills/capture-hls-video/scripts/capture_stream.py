#!/usr/bin/env python3
"""在已播放的回放页里抓取 HLS 播放参数，产出 capture.json。

前置：浏览器已由 chromedp 技能启动（带 --remote-debugging-port），页面已登录
并处于播放状态，本技能只负责「读」，不改动业务数据。

用法：
    python3 capture_stream.py --match 917414 --port 9222 --out capture.json

钩子注入策略：默认不重载——直接对正在播放的当前文档运行钩子脚本即可抓到 key
（``Page.addScriptToEvaluateOnNewDocument`` 只对**新文档**生效，不 reload 时对当前页无效，
所以必须配合 ``Runtime.evaluate`` 立即注入当前文档）。仅在页面停在封面/未解码、需要重走
一遍取 key 流程时才用 ``--reload``；注意 CDP reload 不带用户激活，会被自动播放策略拦停。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time

from cdp_capture import CaptureError, Page, split_events
from providers import collect_meta, detect_platform, extra_playlist_hints
from formats import detect_capabilities

# 注入钩子：三路并抓。
# 1) 主线程 WebCrypto —— 部分播放器（或 hls.js 的 enableSoftwareAES=false 分支）在主线程解密。
# 2) Worker.postMessage —— hls.js 默认把分片和 decryptdata 发给 transmuxer worker 解密，
#    主线程的 crypto.subtle 钩子抓不到这条路径，必须钩跨线程消息。
# 3) 许可证 XHR 响应原文 —— 用于对比「许可证返回的字节」与「播放器真正使用的 key」。
#    实测腾讯云 VOD SimpleAES 两者并不相等，直接拿许可证响应当 key 会解密失败。
HOOK_SOURCE = r"""
(() => {
  if (window.__hlsCap) return; // 幂等：已注入就跳过，避免二次包装
  const hex = (b) => Array.from(new Uint8Array(b))
    .map(x => x.toString(16).padStart(2, '0')).join('');
  const cap = window.__hlsCap = { keys: [], webcrypto: [], license: [] };

  const origDecrypt = crypto.subtle.decrypt.bind(crypto.subtle);
  crypto.subtle.decrypt = async function (alg, key, data) {
    try {
      const raw = await crypto.subtle.exportKey('raw', key);
      cap.webcrypto.push({
        key: hex(raw),
        iv: alg && alg.iv ? hex(alg.iv) : null,
        alg: alg && alg.name ? alg.name : null,
        ctLen: data ? data.byteLength : null,
      });
      if (cap.webcrypto.length > 6) cap.webcrypto.shift();
    } catch (e) { /* 不可导出的 key 直接忽略 */ }
    return origDecrypt(alg, key, data);
  };

  const origPost = Worker.prototype.postMessage;
  Worker.prototype.postMessage = function (msg, ...rest) {
    try {
      const dd = msg && msg.decryptdata;
      if (dd && dd.key) {
        const rec = {
          key: hex(dd.key),
          iv: dd.iv ? hex(dd.iv) : null,
          method: dd.method || null,
          uri: dd._uri ? String(dd._uri).slice(0, 300) : null,
          sn: msg.chunkMeta ? msg.chunkMeta.sn : null,
        };
        if (!cap.keys.some(k => k.key === rec.key && k.iv === rec.iv)) cap.keys.push(rec);
        if (cap.keys.length > 6) cap.keys.shift();
      }
    } catch (e) { /* 消息结构不符就跳过，不影响播放 */ }
    return origPost.call(this, msg, ...rest);
  };

  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.__capUrl = String(url);
    return origOpen.call(this, method, url, ...rest);
  };
  XMLHttpRequest.prototype.send = function (...args) {
    this.addEventListener('load', () => {
      try {
        if (!/getlicense/i.test(this.__capUrl || '')) return;
        const buf = this.responseType === 'arraybuffer' ? this.response : null;
        cap.license.push({
          url: String(this.__capUrl).slice(0, 300),
          len: buf ? buf.byteLength : null,
          raw: buf ? hex(buf) : null,
        });
        if (cap.license.length > 4) cap.license.shift();
      } catch (e) { /* 忽略 */ }
    });
    return origSend.apply(this, args);
  };
})();
"""

PLAYLIST_MEDIA = re.compile(r"#EXT-X-(TARGETDURATION|MEDIA-SEQUENCE)")
PLAYLIST_MASTER = re.compile(r"#EXT-X-STREAM-INF")

# 兜底驱动：重载后播放器有时停在原地不继续拉分片（暂停、缓冲够了、交互被中断），
# 此时既不请求分片也不解密，钩子自然什么都抓不到。主动播放并前跳一段，
# 逼它重新走一遍「取分片 → 取 key → 解密」的流程。
NUDGE_SOURCE = r"""
(() => {
  const v = document.querySelector('video');
  if (!v) return 'no-video';
  try { if (v.paused) v.play(); } catch (e) {}
  try {
    const dur = isFinite(v.duration) && v.duration > 0 ? v.duration : 0;
    const from = v.currentTime || 0;
    v.currentTime = Math.min(from + 240, Math.max(30, dur - 30));
  } catch (e) {}
  return 'nudged';
})()
"""

# 重载后播放器停在 00:00，video 元素尺寸为 0，直接按 video 坐标点击点不到任何东西。
# 这里按候选选择器找「看得见的播放区域」，没有 video 就退到播放器容器/播放按钮。
PLAYER_RECT = r"""
(() => {
  const selectors = ['video', '.vjs-big-play-button', '.prism-player', '.video-player',
                     '[class*="player"]', '.play-btn', '[class*="play"]'];
  for (const sel of selectors) {
    let el = null;
    try { el = document.querySelector(sel); } catch (e) { continue; }
    if (!el) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 10 || r.height < 10) continue;
    if (r.bottom < 0 || r.top > innerHeight) continue;
    return JSON.stringify({x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2)});
  }
  return null;
})()
"""

# 尝试播放并回报真实状态；duration 为 0 说明播放器还没装载媒体，不能算成功。
PLAY_SOURCE = r"""
(async () => {
  const v = document.querySelector('video');
  if (!v) return 'no-video';
  try { await v.play(); } catch (e) { /* 被策略拒绝时下面按状态判断 */ }
  return 'paused=' + v.paused + ' duration=' + Math.round(v.duration || 0) +
         ' ready=' + v.readyState;
})()
"""


def activate_and_play(page, timeout: float = 15.0) -> str:
    """取得用户激活并让视频真正播放，返回最终状态字符串。

    脚本触发的 `Page.reload` 不携带用户激活，Chrome 自动播放策略会拒绝 `play()`
    （NotAllowedError）。此时播放器停在 readyState=0，既不请求分片也不解密，
    钩子什么都抓不到。派发一次真实点击取得激活后再调用 `play()` 即可。

    重载刚返回时播放器停在 00:00、video 元素尺寸为 0，所以判定成功的标准是
    「duration > 0 且未暂停」，而不是「调用过 play()」；找不到可点区域、
    evaluate 撞上导航，都属于还没就绪，必须继续重试。
    """
    last = "timeout"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            rect = page.evaluate(PLAYER_RECT)
        except CaptureError:
            # 导航中发出的 evaluate 会被丢弃，等下一轮即可
            time.sleep(1)
            continue
        if rect:
            coords = json.loads(rect)
            page.click(coords["x"], coords["y"])
            try:
                state = page.evaluate(PLAY_SOURCE)
            except CaptureError:
                time.sleep(1)
                continue
            text = str(state or "")
            last = text
            if text.startswith("paused=false") and "duration=0" not in text:
                return "playing"
        time.sleep(1)
    return last


def classify(body: str) -> str:
    """把响应体归类为 master / media 播放列表或其它。"""
    if not body.lstrip().startswith("#EXTM3U"):
        return "other"
    if PLAYLIST_MASTER.search(body) and not PLAYLIST_MEDIA.search(body):
        return "master"
    if PLAYLIST_MEDIA.search(body):
        return "media"
    return "other"


def parse_media_playlist(url: str, text: str) -> dict:
    """从 media 播放列表里抽出分片清单、目录前缀和 IV。"""
    segments = [ln.strip() for ln in text.splitlines()
                if ln.strip() and not ln.startswith("#")]
    key_line = next((ln for ln in text.splitlines()
                     if ln.startswith("#EXT-X-KEY")), "")
    iv_match = re.search(r"IV=0x([0-9a-fA-F]+)", key_line)
    uri_match = re.search(r'URI="([^"]+)"', key_line)
    return {
        "segment_base": url.rsplit("/", 1)[0],
        "segments": segments,
        "segment_count": len(segments),
        "playlist_iv": iv_match.group(1).lower() if iv_match else None,
        "key_uri": uri_match.group(1) if uri_match else None,
    }


def capture(args) -> dict:
    page = Page(port=args.port, host=args.host, match=args.match, timeout=20)
    result: dict = {"page_url": page.url, "captured_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        page.send("Page.enable")
        page.send("Network.enable", {
            "maxTotalBufferSize": 500 * 1024 * 1024,
            "maxResourceBufferSize": 500 * 1024 * 1024,
        })
        page.install_hook(HOOK_SOURCE)
        # 默认不重载：CDP 触发的 reload 不带用户激活，Chrome 自动播放策略会让播放器
        # 停在 00:00，既不拉分片也不解密，钩子必然抓空。让页面保持正在播放最稳。
        if not args.reload:
            # addScriptToEvaluateOnNewDocument 只对「之后新创建」的文档生效，
            # 对当前已加载页面无效；这里立即把钩子注入当前文档，
            # 播放器持续拉分片/解密，几秒内即可从钩子读到真实 key。
            page.evaluate(HOOK_SOURCE)
        if args.reload:
            page.reload()
            # 导航期间发出的 Runtime.evaluate 会被丢弃，先让导航走一会儿
            page.collect(2.5)
            status = activate_and_play(page)
            result["play_state"] = status
            if args.verbose:
                print(f"    播放状态：{status}", flush=True)

        events: list[dict] = []
        deadline = time.time() + args.wait
        nudges = 0
        while time.time() < deadline:
            events.extend(page.collect(min(3, max(0.5, deadline - time.time()))))
            state = page.evaluate("window.__hlsCap ? "
                                  "{k: window.__hlsCap.keys.length, w: window.__hlsCap.webcrypto.length} "
                                  ": null")
            if state and (state.get("k") or state.get("w")):
                break
            # 采集超过 10 秒还没抓到解密参数，就驱动一次播放，最多 2 次
            elapsed = args.wait - (deadline - time.time())
            if not args.no_nudge and elapsed > 10 and nudges < 2:
                nudges += 1
                print(f"    未捕获解密参数，第 {nudges} 次驱动播放…", flush=True)
                activate_and_play(page, timeout=5)
                page.evaluate(NUDGE_SOURCE)

        indexed = split_events(events)
        requests = indexed["requests"]

        playlist_hints = extra_playlist_hints()  # 各 provider 声明的非 .m3u8 播放列表/token 片段
        playlists: dict[str, dict] = {}
        for req_id, url in requests.items():
            if ".m3u8" not in url and not any(h in url for h in playlist_hints):
                continue
            try:
                raw, _ = page.response_body(req_id)
            except CaptureError:
                continue
            text = raw.decode("utf-8", "replace")
            kind = classify(text)
            if kind != "other" and kind not in playlists:
                playlists[kind] = {"url": url, "text": text}

        if "media" not in playlists:
            raise CaptureError(
                "没有抓到 media 播放列表。请确认页面上的视频确实在播放（停在 00:00 的"
                "播放器既不拉分片也不解密），并确认 --match 指对了标签页；必要时增大 --wait。"
            )

        media = playlists["media"]
        result["media_playlist"] = media
        result["master_playlist"] = playlists.get("master")
        result.update(parse_media_playlist(media["url"], media["text"]))

        caps = page.evaluate("window.__hlsCap ? JSON.stringify(window.__hlsCap) : null")
        caps = json.loads(caps) if caps else {"keys": [], "webcrypto": [], "license": []}
        result["license"] = caps.get("license") or []
        if caps.get("keys"):
            result["key"] = {"hex": caps["keys"][-1]["key"], "iv": caps["keys"][-1]["iv"],
                             "source": "worker.postMessage"}
        elif caps.get("webcrypto"):
            entry = caps["webcrypto"][-1]
            result["key"] = {"hex": entry["key"], "iv": entry["iv"], "source": "crypto.subtle"}
        else:
            result["key"] = None

        # 平台提示：只用于「记录平台名 + 取元信息」，不参与管线决策。
        # 管线由下方 detect_capabilities 依据实际探测到的能力决定（同一平台换协议、
        # 多平台共用协议都能自动落对，见 formats/__init__.py）。
        result["platform"] = detect_platform(page.url, list(requests.values()))
        _pname, _meta = collect_meta(lambda rid: page.response_body(rid)[0], requests)
        if _meta:
            result["vod_info"] = _meta

        # 能力探测：从实际抓到的清单文本/分片/key/平台元信息推断四维能力
        caps = detect_capabilities(
            media_text=media["text"],
            seg_urls=result.get("segments") or [],
            key_record=result.get("key"),
            key_uri=result.get("key_uri"),
            has_license=bool(result.get("license")),
            drm_type=(_meta or {}).get("drm_type"),
        )
        result["format"] = caps.to_dict()
    finally:
        page.close()
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="抓取网页里正在播放的 HLS 流参数")
    ap.add_argument("--match", required=True,
                    help="定位标签页的 URL 片段（同域多标签页时必须唯一，如内容 id）")
    ap.add_argument("--port", type=int, default=9222, help="Chrome 远程调试端口")
    ap.add_argument("--host", default="127.0.0.1", help="调试端口所在主机")
    ap.add_argument("--out", default="capture.json", help="输出 JSON 路径")
    ap.add_argument("--wait", type=float, default=45.0, help="最长采集秒数")
    ap.add_argument("--reload", action="store_true",
                    help="先重载页面再挂钩子（会打断播放，且重载后播放器常被自动播放策略卡住，"
                         "非必要不要用）")
    ap.add_argument("--no-nudge", action="store_true",
                    help="不主动驱动播放（默认会在抓不到 key 时播放并前跳 4 分钟）")
    ap.add_argument("--verbose", action="store_true", help="打印逐步状态，便于排查")
    args = ap.parse_args(argv)

    try:
        result = capture(args)
    except CaptureError as exc:
        print(f"[失败] {exc}", file=sys.stderr)
        return 1

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)

    key = result.get("key") or {}
    print(f"[OK] 已写出 {args.out}")
    print(f"     页面：{result['page_url'][:110]}")
    print(f"     分片：{result.get('segment_count')} 个  目录：{result.get('segment_base')}")
    print(f"     key：{key.get('hex')}  iv：{key.get('iv')}  来源：{key.get('source')}")
    if result.get("vod_info"):
        print(f"     元信息[{result.get('platform')}]：{result['vod_info']}")
    fmt = result.get("format") or {}
    print(f"     能力：manifest={fmt.get('manifest')} container={fmt.get('container')} "
          f"encryption={fmt.get('encryption')} key源={fmt.get('key_source')} "
          f"→ {'支持' if fmt.get('supported') else '暂不支持'}")
    if not fmt.get("supported"):
        print(f"     ⚠ {fmt.get('reason')}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
