#!/usr/bin/env python3
"""能力驱动管线的离线回归测试（不需要浏览器）。

固化两件事，防止再次踩坑：
  1) 管线由「实际探测到的能力」决定，而非平台名——同一平台换协议、不同平台共用协议都要对；
  2) 未实现的能力一律 supported=False 明确拒绝，绝不硬跑产出损坏文件。
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from formats import detect_capabilities  # noqa: E402


def _w(path, data):
    with open(path, "wb") as fh:
        fh.write(data)


def _r(path):
    with open(path, "rb") as fh:
        return fh.read()
import providers  # noqa: E402


def caps(media_text="", seg_urls=None, key=None, key_uri=None,
         has_license=False, drm_type=None):
    return detect_capabilities(media_text, seg_urls or [], key, key_uri,
                               has_license, drm_type)


class DetectCapabilities(unittest.TestCase):
    HLS_TS_AES = "#EXTM3U\n#EXT-X-TARGETDURATION:10\n" + "\n".join(f"seg{i}.ts" for i in range(3))

    def test_hls_ts_runtime_key_is_supported(self):
        # 腾讯云式：播放列表不带 EXT-X-KEY，靠运行时钩子抓 key → 应判为 HLS/TS/AES-128 且支持
        c = caps(self.HLS_TS_AES, ["seg0.ts"], key={"hex": "ab" * 16, "source": "worker.postMessage"})
        self.assertEqual((c.manifest, c.container, c.encryption), ("hls", "ts", "aes-128-cbc"))
        self.assertTrue(c.supported, c.reason)

    def test_hls_ts_extxkey_aes128(self):
        text = "#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI=\"https://k/1\",IV=0x" + "00" * 16 + "\nseg0.ts\n"
        c = caps(text, ["seg0.ts"], key_uri="https://k/1")
        self.assertEqual((c.manifest, c.container, c.encryption), ("hls", "ts", "aes-128-cbc"))
        self.assertTrue(c.supported)

    def test_plain_hls_ts_no_key(self):
        c = caps(self.HLS_TS_AES, ["seg0.ts"], key=None)
        self.assertEqual(c.encryption, "none")
        self.assertTrue(c.supported, c.reason)

    def test_fmp4_is_rejected(self):
        text = "#EXTM3U\n#EXT-X-MAP:URI=\"init.mp4\"\nseg0.m4s\n"
        c = caps(text, ["seg0.m4s"], key={"hex": "ab" * 16})
        self.assertEqual(c.container, "fmp4")
        self.assertFalse(c.supported)
        self.assertIn("fMP4", c.reason)

    def test_dash_is_rejected(self):
        text = '<?xml version="1.0"?><MPD xmlns="urn:mpeg:dash"><Period/></MPD>'
        c = caps(text, ["video-1.mpd", "init.mp4", "seg.m4s"])
        self.assertEqual(c.manifest, "dash")
        self.assertFalse(c.supported)

    def test_strong_drm_rejected(self):
        # 平台元信息给出非 SimpleAES 的 drmType → 强 DRM，拒绝
        c = caps(self.HLS_TS_AES, ["seg0.ts"], key={"hex": "ab" * 16}, drm_type="DRM(标准加密)")
        self.assertEqual(c.encryption, "drm")
        self.assertFalse(c.supported)
        self.assertIn("DRM", c.reason)

    def test_simpleaes_drm_type_is_fine(self):
        c = caps(self.HLS_TS_AES, ["seg0.ts"], key={"hex": "ab" * 16}, drm_type="SimpleAES")
        self.assertEqual(c.encryption, "aes-128-cbc")
        self.assertTrue(c.supported)


class PlatformHintDegrade(unittest.TestCase):
    """平台层只认 token 提示 + 元信息，不决定管线。"""

    def test_extra_playlist_hints_include_voddrm_token(self):
        self.assertIn("voddrm.token", providers.extra_playlist_hints())

    def test_detect_platform_tencent_vs_generic(self):
        self.assertEqual(
            providers.detect_platform("https://x/vodplay", ["https://a/getplayinfo?r=1"]),
            "tencent_vod")
        self.assertEqual(providers.detect_platform("https://whatever.example", ["seg0.ts"]),
                         "generic")

    def test_collect_meta_parses_getplayinfo(self):
        body = b'{"media":{"basicInfo":{"name":"\xe8\xaf\xbe\xe7\xa8\x8b","duration":120,' \
               b'"audioVideoType":"AAC-64"},"drm":{"drmType":"SimpleAES"}}}'
        requests = {"r1": "https://a/getplayinfo?r=1"}
        name, info = providers.collect_meta(lambda rid: body, requests)
        self.assertEqual(name, "tencent_vod")
        self.assertEqual(info["name"], "课程")
        self.assertEqual(info["drm_type"], "SimpleAES")


class DecryptHandler(unittest.TestCase):
    """按能力分发的解密/校验处理器：TS+AES128 与明文两条路径都要往返正确。"""

    @staticmethod
    def _valid_ts(n=4):
        return b"".join(b"\x47" + bytes([i % 256]) + bytes(186) for i in range(n))

    def test_plain_ts_roundtrip(self):
        import fetch_hls as f
        payload = self._valid_ts()
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "e.ts"); dst = os.path.join(d, "o.ts")
            _w(src, payload)
            job = ("e.ts", src, dst, None, None, 0, "none", "ts")
            name, err, size = f._decrypt_job(job)
            self.assertIsNone(err)
            self.assertEqual(_r(dst), payload)

    def test_aes128_ts_roundtrip(self):
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        import fetch_hls as f
        payload = self._valid_ts(8)
        padlen = 16 - (len(payload) % 16)
        padded = payload + bytes([padlen]) * padlen
        key = bytes(range(16)); iv = bytes([7] * 16)
        ct = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor().update(padded)
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "e.ts"); dst = os.path.join(d, "o.ts")
            _w(src, ct)
            job = ("e.ts", src, dst, key.hex(), iv.hex(), 0, "aes-128-cbc", "ts")
            name, err, size = f._decrypt_job(job)
            self.assertIsNone(err, err)
            self.assertEqual(_r(dst), payload)

    def test_bad_encryption_rejected(self):
        import fetch_hls as f
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "e.ts"); dst = os.path.join(d, "o.ts")
            _w(src, b"\x00" * 16)
            _, err, _ = f._decrypt_job(("e.ts", src, dst, None, None, 0, "sample-aes", "ts"))
            self.assertIsNotNone(err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
