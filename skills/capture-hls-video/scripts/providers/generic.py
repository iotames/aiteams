#!/usr/bin/env python3
"""通用兜底平台提示：不绑定任何站点，无元信息接口。

具名平台都不匹配时，detect_platform 回退到它；能力仍由 formats 现场探测。
"""

from __future__ import annotations

from .base import PlatformHint

generic = PlatformHint(name="generic")
