"""批量下载测试 driver（探索用，不进 app/）。

只调 app.service.fetcher.fetch_xiaohongshu 测"能不能把单篇抓下来"：
不转录、不烧 ASR/VLM API、不写知识库。纯测 IP 风控敏感度 + 慢速 vs 并发。

代理：靠环境变量 HTTPS_PROXY / HTTP_PROXY / ALL_PROXY，requests 自动走。
本脚本不碰任何代理凭证（不写进代码，不落盘）。

用法（在仓库根目录）：
  # 1. 先确认出口 IP（验证代理真生效，别以为走代理其实还是自己 IP）
  HTTPS_PROXY='http://user:pass@host:port' uv run python _sandbox/batch-download-test/run.py --check-ip

  # 2. 慢速：5 条，每条间隔 8 秒
  HTTPS_PROXY='...' uv run python _sandbox/batch-download-test/run.py \
      --json ~/path/to/xhs-notes-326.json --limit 5 --mode slow --delay 8

  # 3. 并发：5 条，3 并发
  HTTPS_PROXY='...' uv run python _sandbox/batch-download-test/run.py \
      --json ~/path/to/xhs-notes-326.json --limit 5 --mode concurrent --workers 3
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from app.service import fetcher


def egress_ip() -> tuple[str, str, str]:
    """打印当前出口 IP + 归属地，确认代理是否真生效。"""
    try:
        ip = requests.get("https://api.ipify.org?format=json", timeout=15).json().get("ip", "?")
    except Exception as e:  # noqa: BLE001
        return f"(查询失败: {e})", "", ""
    try:
        geo = requests.get(f"http://ip-api.com/json/{ip}?lang=zh-CN", timeout=15).json()
        return ip, str(geo.get("country", "")), str(geo.get("isp", ""))
    except Exception:  # noqa: BLE001
        return ip, "(归属查询失败)", ""


def probe(url: str) -> dict:
    """抓单篇，分类结果。不抛异常。"""
    t0 = time.time()
    try:
        note = fetcher.fetch_xiaohongshu(url)
        dt = round(time.time() - t0, 1)
        ok = bool(note.get("post_id"))
        return {
            "status": "ok" if ok else "empty",
            "title": (note.get("title") or "")[:24],
            "imgs": len(note.get("image_urls") or []),
            "video": bool(note.get("video_url")),
            "sec": dt,
        }
    except Exception as e:  # noqa: BLE001
        dt = round(time.time() - t0, 1)
        msg = str(e)[:140]
        low = msg.lower()
        # 风控/验证码/抠不到 initial_state 的迹象
        risk = any(k in msg for k in ("薯队长", "验证", "captcha", "initial", "INITIAL", "block", "403"))
        return {"status": "riskctrl" if risk else "error", "title": "", "error": msg, "sec": dt}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="插件导出的 xhs-notes-*.json 路径")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--mode", choices=["slow", "concurrent"], default="slow")
    ap.add_argument("--delay", type=float, default=8.0, help="slow 模式每条间隔秒")
    ap.add_argument("--workers", type=int, default=3, help="concurrent 模式并发数")
    ap.add_argument("--check-ip", action="store_true", help="只查出口 IP 后退出")
    args = ap.parse_args()

    ip, country, isp = egress_ip()
    print(f"[出口 IP] {ip}  归属: {country} / {isp}", flush=True)
    if args.check_ip:
        return
    if not args.json:
        ap.error("需要 --json 指向插件导出的笔记列表")

    notes = json.loads(Path(args.json).expanduser().read_text("utf-8"))[: args.limit]
    urls = [n["url"] for n in notes]
    print(f"[配置] mode={args.mode} limit={len(urls)} delay={args.delay} workers={args.workers}\n", flush=True)

    results: list[dict] = []
    t0 = time.time()
    if args.mode == "slow":
        for i, u in enumerate(urls, 1):
            r = probe(u)
            results.append(r)
            print(f"{i}. [{r['status']}] {r.get('title','')} imgs={r.get('imgs','-')} video={r.get('video','-')} {r['sec']}s"
                  + (f"  err={r['error']}" if r.get("error") else ""), flush=True)
            if i < len(urls):
                time.sleep(args.delay)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            for i, r in enumerate(ex.map(probe, urls), 1):
                results.append(r)
                print(f"{i}. [{r['status']}] {r.get('title','')} imgs={r.get('imgs','-')} video={r.get('video','-')} {r['sec']}s"
                      + (f"  err={r['error']}" if r.get("error") else ""), flush=True)

    total = round(time.time() - t0, 1)
    print(f"\n[汇总] {dict(Counter(r['status'] for r in results))}  总耗时 {total}s", flush=True)


if __name__ == "__main__":
    main()
