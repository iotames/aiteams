#!/usr/bin/env python3
"""平台提示注册表。新增平台 = import + 追加进 REGISTRY（越靠前越优先，generic 永远最后）。"""

from __future__ import annotations

from .base import PlatformHint, ReadBody, MetaFn
from .generic import generic
from .tencent_vod import tencent_vod

REGISTRY: list[PlatformHint] = [tencent_vod, generic]


def extra_playlist_hints() -> tuple:
    out: set = set()
    for p in REGISTRY:
        out.update(p.extra_playlist_hints)
    return tuple(out)


def detect_platform(page_url: str, request_urls) -> str:
    for p in REGISTRY:
        if p.matches(page_url, request_urls):
            return p.name
    return generic.name


def collect_meta(read_body: ReadBody, requests: dict) -> tuple[str | None, dict | None]:
    for p in REGISTRY:
        if not p.meta:
            continue
        rid = p.find_meta_request(requests)
        if not rid:
            continue
        try:
            raw = read_body(rid)
        except Exception:
            continue
        info = p.meta(raw)
        if info:
            return p.name, info
    return None, None
