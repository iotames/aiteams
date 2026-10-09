#!/usr/bin/env python3
"""能力探测 + 处理器注册表（本技能的主轴）。

管线**不看平台、只看从页面实际探测到的四维能力**：

    manifest   : 播放清单协议  —— hls(.m3u8) | dash(.mpd) | unknown
    container  : 分片封装       —— ts | fmp4(init.mp4+.m4s) | unknown
    encryption : 加密方案       —— aes-128-cbc | sample-aes | none | drm | unknown
    key_source : key 从哪来     —— runtime(播放器钩子) | m3u8(EXT-X-KEY URI) | license | unknown

这样：同一平台换了协议、不同平台共用协议，都自动落到正确的管线，无需改平台提示。

新增/扩展能力 = 在 SUPPORTED_* 里登记 + 在 fetch_hls.py 实现对应处理器；
未实现的能力保持 supported=False，明确拒绝而非产出损坏文件。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass


# ── 已实现的能力（处理器存在于 fetch_hls.py）────────────────────
SUPPORTED_MANIFEST = {"hls"}
SUPPORTED_CONTAINER = {"ts"}
SUPPORTED_ENCRYPTION = {"aes-128-cbc", "none"}

# 未支持能力 → 一句话指引（指向 references/extending.md 的 roadmap 编号）
UNSUPPORTED_WHY = {
    "manifest:dash":  "DASH(.mpd) 尚未支持：需新增 mpd 解析器（见 extending.md TODO-1）",
    "container:fmp4": "fMP4(EXT-X-MAP/.m4s) 尚未支持：合并/校验/转封装需按 init+moof 走（TODO-2）",
    "encryption:sample-aes": "SAMPLE-AES 尚未支持：需按 NAL/样本级解密（TODO-3）",
    "encryption:drm":  "Widevine/PlayReady/FairPlay 强 DRM：本技能**不做**，请走平台正规离线方式",
    "encryption:unknown": "无法判定加密方案：请确认已抓到运行时 key，或补平台提示/参考文档",
}


@dataclass
class Capabilities:
    manifest: str = "unknown"
    container: str = "unknown"
    encryption: str = "unknown"
    key_source: str = "unknown"
    supported: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ── 探测 ──────────────────────────────────────────────────
_SEG_FMP4 = re.compile(r"\.(m4s|mp4)(\?|$)")
_EXT_X_MAP = re.compile(r"#EXT-X-MAP:")
_EXT_X_KEY = re.compile(r"#EXT-X-KEY:([^\n]*)")


def _detect_manifest(media_text: str, seg_urls) -> str:
    head = (media_text or "")[:200].lstrip()
    if head.startswith("#EXTM3U"):
        return "hls"
    if "<MPD" in (media_text or ""):
        return "dash"
    joined = " ".join(seg_urls or [])
    if ".mpd" in joined:
        return "dash"
    if ".m3u8" in joined or ".ts" in joined:
        return "hls"
    return "unknown"


def _detect_container(manifest: str, media_text: str, seg_urls) -> str:
    if manifest == "hls":
        if _EXT_X_MAP.search(media_text or "") or any(_SEG_FMP4.search(u) for u in (seg_urls or [])):
            return "fmp4"
        return "ts"  # HLS 默认 TS 分片
    if manifest == "dash":
        return "fmp4"  # DASH 几乎总是 fMP4；未跑通，归 fmp4 以便 supported=False 明确拒绝
    return "unknown"


def _detect_encryption(media_text: str, drm_type) -> str:
    if drm_type:  # 平台元信息给出的强 DRM 优先（非 SimpleAES/none 即判 drm）
        dt = str(drm_type).lower()
        if dt not in ("simpleaes", "aes-128", "none", ""):
            return "drm"
    methods = set()
    for m in _EXT_X_KEY.finditer(media_text or ""):
        mm = re.search(r"METHOD=([A-Z0-9\-]+)", m.group(1))
        if mm:
            methods.add(mm.group(1))
    if "SAMPLE-AES" in methods or "SAMPLE-AES-CTR" in methods:
        return "sample-aes"
    if "AES-128" in methods:
        return "aes-128-cbc"
    if methods and methods <= {"NONE"}:
        return "none"
    return "unknown"  # 无 EXT-X-KEY：交给上层结合运行时 key 再判


def _detect_key_source(key_record, key_uri, has_license) -> str:
    if key_record and key_record.get("hex"):
        return "runtime"
    if key_uri:
        return "m3u8"
    if has_license:
        return "license"
    return "unknown"


def detect_capabilities(media_text, seg_urls, key_record, key_uri,
                        has_license, drm_type) -> Capabilities:
    manifest = _detect_manifest(media_text, seg_urls)
    container = _detect_container(manifest, media_text, seg_urls)

    encryption = _detect_encryption(media_text, drm_type)
    has_runtime_key = bool(key_record and key_record.get("hex"))
    if encryption == "unknown":
        # HLS 播放列表常不带 EXT-X-KEY（由 hls.js 注入 decryptdata）：抓到运行时 key 即视为 AES-128-CBC
        if has_runtime_key:
            encryption = "aes-128-cbc"
        elif manifest == "hls":
            encryption = "none"

    key_source = _detect_key_source(key_record, key_uri, has_license)

    caps = Capabilities(manifest=manifest, container=container,
                        encryption=encryption, key_source=key_source)
    problems = []
    if manifest not in SUPPORTED_MANIFEST:
        problems.append(UNSUPPORTED_WHY.get(f"manifest:{manifest}", f"manifest={manifest} 未支持"))
    if container not in SUPPORTED_CONTAINER:
        problems.append(UNSUPPORTED_WHY.get(f"container:{container}", f"container={container} 未支持"))
    if encryption not in SUPPORTED_ENCRYPTION:
        problems.append(UNSUPPORTED_WHY.get(f"encryption:{encryption}", f"encryption={encryption} 未支持"))
    caps.supported = not problems
    caps.reason = "；".join(problems) if problems else "能力齐备：HLS + TS + AES-128-CBC/明文"
    return caps
