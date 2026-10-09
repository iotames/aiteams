#!/usr/bin/env python3
"""腾讯云 VOD 平台提示（tcplayer）。只贡献 token 请求指纹 + getplayinfo 元信息。

注意：本文件**不声明**容器/加密——能力一律由 formats.detect_capabilities 现场探测。
drm_type 从 getplayinfo 响应里顺带取出，作为能力检测的辅助信号（SimpleAES vs 强 DRM）。
"""

from __future__ import annotations

import json

from .base import PlatformHint


def summarize_getplayinfo(raw: bytes) -> dict | None:
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return None
    media = (data or {}).get("media") or {}
    basic = media.get("basicInfo") or {}
    trans = media.get("transcodeInfo") or {}
    drm = media.get("drm") or {}
    out = {
        "name": basic.get("name"),
        "size": basic.get("size"),
        "duration": basic.get("duration"),
        "audio_video_type": basic.get("audioVideoType")
        or (trans.get("transcodeList") or [{}])[0].get("audioVideoType"),
        "drm_type": drm.get("drmType"),  # 例：SimpleAES / DRM(标准) —— 供能力检测判定是否强 DRM
    }
    return {k: v for k, v in out.items() if v is not None} or None


tencent_vod = PlatformHint(
    name="tencent_vod",
    host_hints=(".myqcloud.com", "qcloudcdn", "vod-qcloud", "tcplayer"),
    url_hints=("getplayinfo",),
    extra_playlist_hints=("voddrm.token",),
    meta=summarize_getplayinfo,
)
