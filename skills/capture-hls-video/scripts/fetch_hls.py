#!/usr/bin/env python3
"""把 capture.json 描述的分片下载、解密、拼成 MP4。

用法：
    python3 fetch_hls.py --capture capture.json --out-dir ./out --title "课程名"

分三步，每步都可单独跳过（--skip-download / --keep-enc / --no-remux），
便于大文件重跑时不用从头再来。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

DEFAULT_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")


# ─── 下载 ────────────────────────────────────────────────

def download_with_aria2(urls, names, enc_dir, jobs, headers):
    """用 aria2c 并发下载；返回 True 表示全部成功。"""
    list_path = os.path.join(enc_dir, "urls.txt")
    lines = []
    for url, name in zip(urls, names):
        lines.append(url)
        lines.append(f"  out={name}")
    with open(list_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    cmd = ["aria2c", "-i", list_path, "-d", enc_dir, "-j", str(jobs),
           "-x", "4", "-s", "16", "--file-allocation=none",
           "--auto-file-renaming=false", "--allow-overwrite=true",
           "--console-log-level=warn", "--summary-interval=30"]
    # aria2c 1.37 起只认 --header=，写 -H 会直接报 invalid option
    for key, value in headers.items():
        cmd.append(f"--header={key}: {value}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout[-2000:], file=sys.stderr)
        print(proc.stderr[-2000:], file=sys.stderr)
        return False
    return True


def download_with_threads(urls, names, enc_dir, jobs, headers):
    """aria2c 不可用时的纯 Python 兜底。"""
    def fetch(item):
        url, name = item
        dest = os.path.join(enc_dir, name)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            return None
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as fh:
                shutil.copyfileobj(resp, fh)
        except Exception as exc:  # 交给上层汇总
            return f"{name}: {exc}"
        return None

    failed = []
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        for i, err in enumerate(pool.map(fetch, zip(urls, names)), 1):
            if err:
                failed.append(err)
            if i % 200 == 0:
                print(f"    下载进度 {i}/{len(urls)}", flush=True)
    for err in failed[:10]:
        print("   ", err, file=sys.stderr)
    return not failed


def download(urls, names, enc_dir, jobs, headers, force=False):
    missing = [i for i, n in enumerate(names)
               if force or not os.path.exists(os.path.join(enc_dir, n))
               or os.path.getsize(os.path.join(enc_dir, n)) == 0]
    if not missing:
        print(f"  已存在全部 {len(names)} 个分片，跳过下载")
        return True
    print(f"  待下载 {len(missing)}/{len(names)} 个分片，并发 {jobs}")
    sub_urls = [urls[i] for i in missing]
    sub_names = [names[i] for i in missing]
    if shutil.which("aria2c"):
        return download_with_aria2(sub_urls, sub_names, enc_dir, jobs, headers)
    print("  未找到 aria2c，回退到 Python 线程池下载（较慢）")
    return download_with_threads(sub_urls, sub_names, enc_dir, jobs, headers)


# ─── 解密 ────────────────────────────────────────────────

def decrypt_bytes(cipher_text: bytes, key: bytes, iv: bytes) -> bytes:
    """整段 AES-CBC 解密并去掉 PKCS7 填充。"""
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError:  # 没装 cryptography 时退回 openssl 命令行
        proc = subprocess.run(
            ["openssl", "enc", "-d", "-aes-128-cbc", "-nopad",
             "-K", key.hex(), "-iv", iv.hex()],
            input=cipher_text, capture_output=True)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode("utf-8", "replace"))
        plain = proc.stdout
    else:
        plain = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor().update(cipher_text)

    if not plain:
        return plain
    pad = plain[-1]
    if 1 <= pad <= 16 and plain.endswith(bytes([pad]) * pad):
        plain = plain[:-pad]
    return plain


# ── 容器校验钩子：按探测到的 container 分发（新增容器在此登记实现）────
def _validate_ts(plain: bytes):
    """MPEG-TS：188 字节对齐 + 每包 0x47 同步头。返回错误串或 None。"""
    if len(plain) % 188 or plain[0] != 0x47:
        return "不是合法 TS（长度或同步头不符）"
    good = sum(1 for off in range(0, len(plain), 188) if plain[off] == 0x47)
    if good != len(plain) // 188:
        return f"TS 同步头损坏（{good}/{len(plain) // 188}）"
    return None


CONTAINER_VALIDATORS = {
    "ts": _validate_ts,
    # "fmp4": _validate_fmp4,  # TODO-2：见 references/extending.md
}


def _decrypt_job(job):
    """子进程任务：按 (encryption, container) 能力解密单个分片并校验。"""
    name, src, dst, key_hex, iv_hex, seq, encryption, container = job
    with open(src, "rb") as fh:
        raw = fh.read()
    if encryption == "none":
        plain = raw
    elif encryption == "aes-128-cbc":
        key = bytes.fromhex(key_hex)
        iv = bytes.fromhex(iv_hex) if iv_hex else seq.to_bytes(16, "big")
        if len(raw) % 16:
            return name, "密文长度不是 16 的整数倍", 0
        try:
            plain = decrypt_bytes(raw, key, iv)
        except Exception as exc:
            return name, f"解密失败：{exc}", 0
    else:
        return name, f"未支持的加密方案：{encryption}", 0
    validator = CONTAINER_VALIDATORS.get(container)
    if validator:
        err = validator(plain)
        if err:
            return name, err, 0
    with open(dst, "wb") as fh:
        fh.write(plain)
    return name, None, len(plain)


def decrypt_all(names, enc_dir, dec_dir, key_hex, iv_hex, workers=16,
                encryption="aes-128-cbc", container="ts"):
    """并发解密全部切片，返回 (明文总字节数, 失败列表)。"""
    jobs = []
    for seq, name in enumerate(names):
        jobs.append((name, os.path.join(enc_dir, name),
                     os.path.join(dec_dir, name), key_hex, iv_hex, seq,
                     encryption, container))
    failed, total = [], 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i, (name, err, size) in enumerate(pool.map(_decrypt_job, jobs, chunksize=8), 1):
            if err:
                failed.append((name, err))
            else:
                total += size
            if i % 200 == 0:
                print(f"    解密进度 {i}/{len(names)}，失败 {len(failed)}", flush=True)
    return total, failed


# ─── 拼接与转封装 ────────────────────────────────────────

def concat(names, dec_dir, combined_path):
    with open(combined_path, "wb") as out:
        for name in names:
            with open(os.path.join(dec_dir, name), "rb") as fh:
                shutil.copyfileobj(fh, out, length=1 << 20)
    return os.path.getsize(combined_path)


def remux(combined_path, out_path):
    """TS → MP4，纯复制不重编码；+faststart 让文件可边下边播。"""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
           "-i", combined_path, "-c", "copy", "-bsf:a", "aac_adtstoasc",
           "-movflags", "+faststart", out_path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 转封装失败：{proc.stderr[-1500:]}")
    return os.path.getsize(out_path)


# ─── 入口 ────────────────────────────────────────────────

def safe_name(text: str) -> str:
    """把标题清洗成安全的文件名。"""
    cleaned = "".join("_" if ch in '/\\:*?"<>|' else ch for ch in text).strip()
    return cleaned or "video"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="下载并解密 capture.json 里的 HLS 视频")
    ap.add_argument("--capture", required=True, help="capture_stream.py 产出的 JSON")
    ap.add_argument("--out-dir", required=True, help="输出目录（分片与成片都放这里）")
    ap.add_argument("--title", help="输出文件名（默认用 VOD 名称或 captured 时间）")
    ap.add_argument("--jobs", type=int, default=16, help="并发数")
    ap.add_argument("--referer", help="下载分片时携带的 Referer，默认取页面源站")
    ap.add_argument("--key", help="覆盖 capture.json 里的 key（hex）")
    ap.add_argument("--iv", help="覆盖 capture.json 里的 iv（hex）")
    ap.add_argument("--keep-enc", action="store_true", help="保留加密分片，便于重跑")
    ap.add_argument("--no-remux", action="store_true", help="只产出合并后的 TS")
    args = ap.parse_args(argv)

    with open(args.capture, encoding="utf-8") as fh:
        cap = json.load(fh)

    fmt = cap.get("format") or {}
    # 能力闸门：capture 探测到的管线若不在已实现范围，明确拒绝而非硬跑产坏文件。
    # 兼容旧 capture.json（无 format）：默认按 TS + AES-128-CBC 处理。
    container = fmt.get("container", "ts")
    encryption = fmt.get("encryption", "aes-128-cbc")
    if fmt and not fmt.get("supported", True):
        print(f"[不支持] {fmt.get('reason', '当前能力组合尚未实现')}\n"
              f"          manifest={fmt.get('manifest')} container={container} "
              f"encryption={encryption}；详见 references/extending.md",
              file=sys.stderr)
        return 2
    if encryption not in ("aes-128-cbc", "none"):
        print(f"[不支持] 加密方案 {encryption} 尚无处理器（extending.md）", file=sys.stderr)
        return 2

    key = args.key or (cap.get("key") or {}).get("hex")
    iv = args.iv or (cap.get("key") or {}).get("iv") or cap.get("playlist_iv")
    if encryption == "aes-128-cbc" and not key:
        print("[失败] 需要解密但没拿到 key。请确认 capture 阶段页面确实在播放——"
              "许可证接口返回的字节不等于播放器实际使用的 key，必须以钩子抓到的为准。",
              file=sys.stderr)
        return 1
    names = cap.get("segments") or []
    if not names:
        print("[失败] capture.json 里没有分片清单", file=sys.stderr)
        return 1

    enc_dir = os.path.join(args.out_dir, "enc")
    dec_dir = os.path.join(args.out_dir, "dec")
    os.makedirs(enc_dir, exist_ok=True)
    os.makedirs(dec_dir, exist_ok=True)

    ext = container
    local_names = [f"{i:05d}.{ext}" for i in range(len(names))]
    urls = [f"{cap['segment_base']}/{name}" for name in names]
    headers = {"User-Agent": DEFAULT_UA}
    referer = args.referer
    if not referer and cap.get("page_url"):
        referer = "https://" + cap["page_url"].split("//", 1)[-1].split("/", 1)[0] + "/"
    if referer:
        headers["Referer"] = referer

    started = time.time()
    print(f"[1/4] 下载 {len(urls)} 个分片 → {enc_dir}")
    if not download(urls, local_names, enc_dir, args.jobs, headers):
        print("[失败] 分片下载未全部成功", file=sys.stderr)
        return 1

    if encryption == "none":
        print("[2/4] 明文分片（无加密），仅做容器校验")
    else:
        print(f"[2/4] 解密 {encryption}（key={key} iv={iv or '按序号推导'}）")
    total, failed = decrypt_all(local_names, enc_dir, dec_dir, key, iv, args.jobs,
                                encryption=encryption, container=container)
    if failed:
        print(f"[失败] {len(failed)} 个分片解密校验不通过：{failed[:5]}", file=sys.stderr)
        return 1
    print(f"      解密成功 {len(local_names)} 个，明文 {total / 1024 / 1024:.1f} MiB")

    combined = os.path.join(args.out_dir, f"combined.{ext}")
    print(f"[3/4] 按序拼接 → {combined}")
    size = concat(local_names, dec_dir, combined)
    print(f"      {size / 1024 / 1024:.1f} MiB")

    title = args.title or (cap.get("vod_info") or {}).get("name") or \
        time.strftime("video-%Y%m%d-%H%M%S")
    if args.no_remux:
        print(f"[4/4] 已跳过转封装，成片：{combined}")
    else:
        out_path = os.path.join(args.out_dir, f"{safe_name(title)}.mp4")
        print(f"[4/4] 转封装 → {out_path}")
        print(f"      {remux(combined, out_path) / 1024 / 1024:.1f} MiB")

    if not args.keep_enc:
        shutil.rmtree(enc_dir, ignore_errors=True)
        print("      已清理加密分片目录（--keep-enc 可保留）")
    print(f"完成，用时 {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
