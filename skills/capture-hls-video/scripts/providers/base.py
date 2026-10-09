#!/usr/bin/env python3
"""PlatformHint：平台侧的「取地址 / 取元信息」辅助提示，不参与管线决策。

重要边界（能力驱动 vs 平台驱动）：
  - 管线由 formats.detect_capabilities 从页面**实际探测到的技术能力**
    （manifest 协议 / 分片容器 / 加密方案 / key 来源）决定；
  - 同一平台今天 HLS-TS-AES128、明天 DASH-fMP4-DRM 很常见；多个平台共用 HLS
    SimpleAES 也很常见。所以**绝不允许**在本类里声明"本平台支持什么容器/加密"——
    那会让"平台没变但协议变了"时整条管线判错。本类只提供两件与协议无关的事实：
      1) 哪些请求 URL 承载播放列表 / 播放 token（帮内核多认几条候选）；
      2) 平台元信息接口在哪、响应怎么解析成 {name,size,duration,drm_type}。

新增平台 = 在本目录加一个 PlatformHint 并在 __init__.py 注册，不动内核与 formats。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

ReadBody = Callable[[str], bytes]          # req_id -> bytes
MetaFn = Callable[[bytes], Optional[dict]]  # 命中请求体 -> 元信息（含可选 drm_type）


@dataclass(frozen=True)
class PlatformHint:
    name: str
    host_hints: tuple = ()            # 页面/请求 URL 命中其一即认为属于本平台
    url_hints: tuple = ()             # 请求 URL 片段：①识别平台 ②定位取元信息的请求
    extra_playlist_hints: tuple = ()  # 非 .m3u8 但承载播放列表/token 的请求 URL 片段
    meta: Optional[MetaFn] = None     # 可选元信息解析器

    def matches(self, page_url: str, request_urls) -> bool:
        hay = f"{page_url} " + " ".join(request_urls)
        return any(h in hay for h in (*self.host_hints, *self.url_hints))

    def find_meta_request(self, requests: dict) -> Optional[str]:
        for rid, url in requests.items():
            if any(h in url for h in self.url_hints):
                return rid
        return None
